import { redirect, type Handle } from '@sveltejs/kit';
import { SESSION_COOKIE, USER_COOKIE } from '$lib/server/auth';

const PUBLIC = ['/login', '/auth/', '/healthz'];

export const handle: Handle = async ({ event, resolve }) => {
	const token = event.cookies.get(SESSION_COOKIE) ?? null;
	let user: App.User | null = null;
	const raw = event.cookies.get(USER_COOKIE);
	if (token && raw) {
		try {
			user = JSON.parse(raw);
		} catch {
			user = null;
		}
	}
	event.locals.token = user ? token : null;
	event.locals.user = user;

	const path = event.url.pathname;
	if (!event.locals.user && !PUBLIC.some((p) => path === p || path.startsWith(p))) {
		redirect(303, `/login?next=${encodeURIComponent(path + event.url.search)}`);
	}
	const response = await resolve(event);
	response.headers.set('X-Frame-Options', 'DENY');
	response.headers.set('Referrer-Policy', 'same-origin');
	return response;
};
