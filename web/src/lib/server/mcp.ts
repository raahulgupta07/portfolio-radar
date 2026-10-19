// The web app's only way to data: MCP calls to the City MCP Gateway, made on
// the server with the signed-in user's token. The browser never talks to the
// gateway or the database.
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { createHash } from 'node:crypto';
import { env } from '$env/dynamic/private';

const GATEWAY_URL = () => (env.GATEWAY_URL || 'http://localhost:8000').replace(/\/$/, '');
const CACHE_MS = Number(env.MCP_CACHE_SECONDS ?? '60') * 1000;

export class McpToolError extends Error {
	constructor(
		message: string,
		public server: string,
		public tool: string
	) {
		super(message);
	}
}

type Entry = { at: number; value: unknown };
const MAX_ENTRIES = 500;
export const tokenKey = (token: string) => createHash('sha256').update(token).digest('base64url');
const cache = new Map<string, Entry>();

async function connect(token: string, server: string): Promise<Client> {
	const transport = new StreamableHTTPClientTransport(new URL(`${GATEWAY_URL()}/${server}/mcp`), {
		requestInit: { headers: { Authorization: `Bearer ${token}` } }
	});
	const client = new Client({ name: 'portfolio-radar-web', version: '0.1.0' });
	await client.connect(transport);
	return client;
}

/** Call one tool. Read results are cached briefly per user; data changes once a day. */
export async function callTool<T = Record<string, unknown>>(
	token: string,
	server: string,
	tool: string,
	args: Record<string, unknown> = {},
	opts: { cache?: boolean } = {}
): Promise<T> {
	const useCache = opts.cache ?? true;
	const key = `${tokenKey(token)}|${server}|${tool}|${JSON.stringify(args)}`;
	const hit = cache.get(key);
	if (useCache && hit && Date.now() - hit.at < CACHE_MS) return hit.value as T;

	const client = await connect(token, server);
	try {
		const r = await client.callTool({ name: tool, arguments: args });
		if (r.isError) {
			const text = Array.isArray(r.content) && r.content[0]?.type === 'text' ? r.content[0].text : 'Error';
			throw new McpToolError(String(text), server, tool);
		}
		const sc = (r.structuredContent ?? {}) as Record<string, unknown>;
		const value = (Object.keys(sc).length === 1 && 'result' in sc ? sc.result : sc) as T;
		if (useCache) {
			// Drop old entries so expired tokens and old results do not pile up.
			const now = Date.now();
			for (const [k, v] of cache) if (now - v.at > CACHE_MS) cache.delete(k);
			while (cache.size >= MAX_ENTRIES) cache.delete(cache.keys().next().value!);
			cache.set(key, { at: now, value });
		}
		return value;
	} finally {
		await client.close().catch(() => {});
	}
}

/** After an action changes something, drop cached reads so the next page shows it. */
export function clearCache(): void {
	cache.clear();
}
