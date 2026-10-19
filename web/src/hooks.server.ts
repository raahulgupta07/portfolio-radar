import { redirect, type Handle } from '@sveltejs/kit';
import { SESSION_COOKIE, USER_COOKIE } from '$lib/server/auth';

// /api/teams/messages: Microsoft Teams, checked by the gateway against Microsoft's token.
const PUBLIC = ['/login', '/auth/', '/healthz', '/api/teams/messages'];

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
	return compress(event.request, response);
};

// Pages for 500 projects are about 1 MB of HTML; gzip makes them about a tenth of that, which matters on
// slow office and mobile links. Built JS and CSS are already pre-compressed by adapter-node.
const COMPRESSIBLE = /^(text\/html|application\/json|text\/csv|text\/plain)/;

function compress(request: Request, response: Response): Response {
	const type = response.headers.get('content-type') ?? '';
	if (
		!response.body ||
		response.headers.has('content-encoding') ||
		!COMPRESSIBLE.test(type) ||
		!/\bgzip\b/.test(request.headers.get('accept-encoding') ?? '')
	)
		return response;
	const headers = new Headers(response.headers);
	headers.set('content-encoding', 'gzip');
	headers.delete('content-length');
	headers.append('vary', 'Accept-Encoding');
	return new Response(response.body.pipeThrough(new CompressionStream('gzip')), {
		status: response.status,
		statusText: response.statusText,
		headers
	});
}
