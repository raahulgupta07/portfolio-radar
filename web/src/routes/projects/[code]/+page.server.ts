import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { callTool, McpToolError } from '$lib/server/mcp';

export const load: PageServerLoad = async ({ locals, params }) => {
	try {
		return { p: await callTool<Record<string, any>>(locals.token!, 'portfolio', 'get_project', { code: params.code }) };
	} catch (e) {
		if (e instanceof McpToolError) error(e.message.startsWith('No project') ? 404 : 403, e.message);
		error(503, 'The portfolio service is not reachable right now. Try again in a minute.');
	}
};
