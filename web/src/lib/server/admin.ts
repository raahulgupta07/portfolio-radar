// Admin pages: every read and change is a call to /admin/mcp with the signed-in
// admin's token. Nothing here talks to the database or to a tracker.
import { error, fail } from '@sveltejs/kit';
import { callTool, clearCache, McpToolError } from '$lib/server/mcp';

export type Any = Record<string, any>;

export function adminCall<T = Any>(token: string, tool: string, args: Any = {}): Promise<T> {
	return callTool<T>(token, 'admin', tool, args, { cache: false });
}

/** For load functions: turn a gateway problem into an error page. */
export async function loadOrError<T>(fn: () => Promise<T>): Promise<T> {
	try {
		return await fn();
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'The admin service is not reachable right now.');
	}
}

/** For actions: run one or more calls, return a message for the page. */
export async function act(fn: () => Promise<string | Any>) {
	try {
		const r = await fn();
		clearCache();
		return typeof r === 'string' ? { ok: true, message: r } : { ok: true, ...r };
	} catch (e) {
		return fail(400, { ok: false, message: e instanceof McpToolError ? e.message : 'The gateway is not reachable.' });
	}
}

export const str = (f: FormData, k: string) => String(f.get(k) ?? '').trim();
