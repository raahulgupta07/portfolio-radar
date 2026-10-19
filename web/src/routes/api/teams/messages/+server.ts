// Microsoft Teams posts chat messages here (the Azure Bot's messaging endpoint). This route only
// forwards them to the gateway's /teams/messages, which checks Microsoft's token, so nothing here
// is trusted. The gateway stays private inside the network.
import type { RequestHandler } from './$types';
import { env } from '$env/dynamic/private';

const MAX_BODY = 256_000;

export const POST: RequestHandler = async ({ request }) => {
	const body = await request.text();
	if (body.length > MAX_BODY) return new Response('Too large', { status: 413 });
	const gateway = (env.GATEWAY_URL ?? 'http://localhost:8000').replace(/\/$/, '');
	try {
		const r = await fetch(`${gateway}/teams/messages`, {
			method: 'POST',
			headers: {
				'content-type': 'application/json',
				authorization: request.headers.get('authorization') ?? ''
			},
			body,
			signal: AbortSignal.timeout(14_000) // Teams waits 15 seconds
		});
		return new Response(r.status === 200 ? null : await r.text(), {
			status: r.status,
			headers: r.status === 200 ? {} : { 'content-type': 'application/json' }
		});
	} catch {
		return new Response('Gateway not reachable', { status: 502 });
	}
};
