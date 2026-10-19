import { error, redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { OIDC_COOKIE, SESSION_COOKIE, USER_COOKIE, finishSso } from '$lib/server/auth';
import { callTool } from '$lib/server/mcp';

export const GET: RequestHandler = async ({ url, cookies }) => {
	const saved = cookies.get(OIDC_COOKIE);
	cookies.delete(OIDC_COOKIE, { path: '/' });
	const code = url.searchParams.get('code');
	if (!saved || !code) error(400, 'Sign-in was not started here. Try again.');
	const { state, verifier } = JSON.parse(saved);
	if (url.searchParams.get('state') !== state) error(400, 'Sign-in check failed. Try again.');

	const { accessToken, name } = await finishSso(url.origin, code, verifier);
	// The gateway checks the token and works out roles from Entra ID groups.
	const who = await callTool<{ kind: 'human'; id: string; roles: string[] }>(accessToken, 'system', 'whoami', {}, { cache: false });
	const opts = { path: '/', httpOnly: true, sameSite: 'lax' as const, secure: url.protocol === 'https:', maxAge: 60 * 55 };
	cookies.set(SESSION_COOKIE, accessToken, opts);
	cookies.set(USER_COOKIE, JSON.stringify({ id: who.id, name, kind: who.kind, roles: who.roles }), opts);
	redirect(303, '/');
};
