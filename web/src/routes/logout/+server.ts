import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { SESSION_COOKIE, USER_COOKIE, sso } from '$lib/server/auth';

export const POST: RequestHandler = async ({ cookies, url }) => {
	cookies.delete(SESSION_COOKIE, { path: '/' });
	cookies.delete(USER_COOKIE, { path: '/' });
	// Also end the City SSO session, so the next person on a shared PC is not signed in silently.
	const cfg = sso();
	if (cfg) redirect(303, cfg.logout(`${env.ORIGIN || url.origin}/login`));
	redirect(303, '/login');
};
