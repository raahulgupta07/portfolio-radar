import { fail, redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import type { Actions, PageServerLoad } from './$types';
import { callTool, McpToolError } from '$lib/server/mcp';
import { OIDC_COOKIE, SESSION_COOKIE, USER_COOKIE, devUsers, devLoginEnabled, ssoEnabled, ssoLabel, startSso } from '$lib/server/auth';

type WhoAmI = { kind: 'human' | 'agent' | 'service'; id: string; roles: string[] };

/** Only a path on this site: no other host, no backslashes or control characters (browsers read "\\" as "/"). */
function safeNext(next: string | null, origin = 'http://x.invalid'): string {
	if (!next || !next.startsWith('/') || /[\\\u0000-\u001f]/.test(next)) return '/';
	try {
		const u = new URL(next, origin);
		return u.origin === new URL(origin).origin ? u.pathname + u.search + u.hash : '/';
	} catch {
		return '/';
	}
}

const GATEWAY = () => (env.GATEWAY_URL || 'http://localhost:8000').replace(/\/$/, '');

/** Whether the gateway has a superadmin set up (SUPERADMIN_USERNAME + password hash). */
async function localEnabled(): Promise<boolean> {
	try {
		const r = await fetch(`${GATEWAY()}/auth/local`, { signal: AbortSignal.timeout(3000) });
		return r.ok && (await r.json()).enabled === true;
	} catch {
		return false;
	}
}

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.user) redirect(303, safeNext(url.searchParams.get('next'), url.origin));
	return {
		local: await localEnabled(),
		sso: ssoEnabled(),
		ssoLabel: ssoLabel(),
		dev: devLoginEnabled(),
		devUsers: devUsers().map((u) => ({ token: u.token, name: u.name, label: u.label }))
	};
};

export const actions: Actions = {
	dev: async ({ request, cookies, url }) => {
		const form = await request.formData();
		const token = String(form.get('token') ?? '');
		const user = devUsers().find((u) => u.token === token);
		if (!user) return fail(400, { error: 'Pick a sample user.' });
		let who: WhoAmI;
		try {
			who = await callTool<WhoAmI>(token, 'system', 'whoami', {}, { cache: false });
		} catch (e) {
			const msg = e instanceof McpToolError ? e.message : 'The gateway is not reachable. Is it running?';
			return fail(502, { error: msg });
		}
		const secure = url.protocol === 'https:';
		const opts = { path: '/', httpOnly: true, sameSite: 'lax' as const, secure, maxAge: 60 * 60 * 10 };
		cookies.set(SESSION_COOKIE, token, opts);
		cookies.set(USER_COOKIE, JSON.stringify({ name: user.name }), opts); // display name only; roles come from the gateway
		redirect(303, safeNext(url.searchParams.get('next'), url.origin));
	},
	local: async ({ request, cookies, url, getClientAddress }) => {
		const form = await request.formData();
		const username = String(form.get('username') ?? '').trim();
		const password = String(form.get('password') ?? '');
		if (!username || !password) return fail(400, { error: 'Enter the superadmin name and password.', local: true });
		let r: Response;
		try {
			r = await fetch(`${GATEWAY()}/auth/local`, {
				method: 'POST',
				headers: { 'content-type': 'application/json', 'x-forwarded-for': getClientAddress() },
				body: JSON.stringify({ username, password })
			});
		} catch {
			return fail(502, { error: 'The gateway is not reachable. Is it running?', local: true });
		}
		const body = await r.json().catch(() => ({}));
		if (!r.ok) return fail(r.status, { error: body.error ?? 'Sign-in failed.', local: true });
		const opts = { path: '/', httpOnly: true, sameSite: 'strict' as const, secure: url.protocol === 'https:', maxAge: Number(body.expires_in) || 3600 };
		cookies.set(SESSION_COOKIE, body.access_token, opts);
		cookies.set(USER_COOKIE, JSON.stringify({ name: `Superadmin (${username})` }), opts);
		redirect(303, safeNext(url.searchParams.get('next'), url.origin));
	},
	sso: async ({ cookies, url }) => {
		if (!ssoEnabled()) return fail(400, { error: 'City SSO is not set up yet.' });
		const { url: to, cookie } = startSso(url.origin);
		cookies.set(OIDC_COOKIE, cookie, { path: '/', httpOnly: true, sameSite: 'lax', secure: url.protocol === 'https:', maxAge: 600 });
		redirect(303, to);
	}
};
