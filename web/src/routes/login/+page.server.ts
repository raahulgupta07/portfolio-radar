import { fail, redirect } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { callTool, McpToolError } from '$lib/server/mcp';
import { OIDC_COOKIE, SESSION_COOKIE, USER_COOKIE, devUsers, devLoginEnabled, ssoEnabled, startSso } from '$lib/server/auth';

type WhoAmI = { kind: 'human' | 'agent' | 'service'; id: string; roles: string[] };

function safeNext(next: string | null): string {
	return next && next.startsWith('/') && !next.startsWith('//') ? next : '/';
}

export const load: PageServerLoad = async ({ locals, url }) => {
	if (locals.user) redirect(303, safeNext(url.searchParams.get('next')));
	return {
		sso: ssoEnabled(),
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
		cookies.set(USER_COOKIE, JSON.stringify({ id: who.id, name: user.name, kind: who.kind, roles: who.roles }), opts);
		redirect(303, safeNext(url.searchParams.get('next')));
	},
	sso: async ({ cookies, url }) => {
		if (!ssoEnabled()) return fail(400, { error: 'City SSO is not set up yet.' });
		const { url: to, cookie } = startSso(url.origin);
		cookies.set(OIDC_COOKIE, cookie, { path: '/', httpOnly: true, sameSite: 'lax', secure: url.protocol === 'https:', maxAge: 600 });
		redirect(303, to);
	}
};
