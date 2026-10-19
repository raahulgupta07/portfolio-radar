import { redirect } from '@sveltejs/kit';
import type { RequestHandler } from './$types';
import { SESSION_COOKIE, USER_COOKIE } from '$lib/server/auth';

export const POST: RequestHandler = async ({ cookies }) => {
	cookies.delete(SESSION_COOKIE, { path: '/' });
	cookies.delete(USER_COOKIE, { path: '/' });
	redirect(303, '/login');
};
