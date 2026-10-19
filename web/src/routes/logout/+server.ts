import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';
import { SESSION_COOKIE, USER_COOKIE, ssoEnabled } from '$lib/server/auth';

export const POST: RequestHandler = async ({ cookies, url }) => {
	cookies.delete(SESSION_COOKIE, { path: '/' });
	cookies.delete(USER_COOKIE, { path: '/' });
	// Also end the City SSO session, so the next person on a shared PC is not signed in silently.
	if (ssoEnabled()) {
		const back = encodeURIComponent(`${env.ORIGIN || url.origin}/login`);
		redirect(303, `https://login.microsoftonline.com/${env.ENTRA_TENANT_ID}/oauth2/v2.0/logout?post_logout_redirect_uri=${back}`);
	}
	redirect(303, '/login');
};
