// Who is signed in. The pr_user cookie only carries the display name: the id and roles always come from the
// gateway (system.whoami) for the session's token, so editing the cookie gains nothing.
import { callTool, McpToolError, tokenKey } from '$lib/server/mcp';

type Who = { kind: App.User['kind']; id: string; roles: string[] };
const TTL_MS = 5 * 60_000;
const MAX = 2000;
const known = new Map<string, { at: number; who: Who | null }>();

function prune(now: number) {
	for (const [k, v] of known) if (now - v.at > TTL_MS) known.delete(k);
	while (known.size > MAX) known.delete(known.keys().next().value!);
}

/** The caller behind a token, or null if the gateway refuses it (expired, unknown). Throws if the gateway is down. */
export async function whoami(token: string, name?: string | null): Promise<Who | null> {
	const key = tokenKey(token);
	const now = Date.now();
	const hit = known.get(key);
	if (hit && now - hit.at < TTL_MS) return hit.who;
	let who: Who | null;
	try {
		// Also records the sign-in for Admin → People.
		who = await callTool<Who>(token, 'system', 'whoami', name ? { name } : {}, { cache: false });
	} catch (e) {
		if (!(e instanceof McpToolError) && !/401|403|token/i.test(String(e))) throw e;
		who = null;
	}
	prune(now);
	known.set(key, { at: now, who });
	return who;
}

/** The display name saved at sign-in; anything else in the cookie is ignored. */
export function displayName(raw: string | undefined): string | null {
	if (!raw) return null;
	try {
		const v = JSON.parse(raw);
		return v && typeof v === 'object' && typeof v.name === 'string' ? v.name.slice(0, 100) : null;
	} catch {
		return null;
	}
}
