import { redirect, type Handle } from '@sveltejs/kit';
import { SESSION_COOKIE, USER_COOKIE } from '$lib/server/auth';
import { displayName, whoami } from '$lib/server/session';

// Exact paths only, so a new route is never public by accident. /api/teams/messages: Microsoft Teams,
// checked by the gateway against Microsoft's token.
const PUBLIC = new Set(['/login', '/healthz', '/api/teams/messages', '/auth/callback']);

export const handle: Handle = async ({ event, resolve }) => {
	const path = event.url.pathname;
	const isPublic = PUBLIC.has(path);
	const token = event.cookies.get(SESSION_COOKIE) ?? null;
	let user: App.User | null = null;
	if (token && !(isPublic && path !== '/login')) {
		try {
			// The gateway says who this token is; the cookie gives only the display name.
			const who = await whoami(token);
			if (who) user = { ...who, name: displayName(event.cookies.get(USER_COOKIE)) ?? who.id };
		} catch {
			// Gateway down: let the page load (it shows the error) with no roles at all.
			user = { id: '', name: displayName(event.cookies.get(USER_COOKIE)) ?? 'Signed in', kind: 'human', roles: [] };
		}
	}
	event.locals.token = user ? token : null;
	event.locals.user = user;

	if (!event.locals.user && !isPublic) {
		redirect(303, `/login?next=${encodeURIComponent(path + event.url.search)}`);
	}
	const response = await resolve(event);
	response.headers.set('X-Frame-Options', 'DENY');
	response.headers.set('Referrer-Policy', 'same-origin');
	response.headers.set('X-Content-Type-Options', 'nosniff');
	if (event.url.protocol === 'https:') response.headers.set('Strict-Transport-Security', 'max-age=31536000; includeSubDomains');
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
