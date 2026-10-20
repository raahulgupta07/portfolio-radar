import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { callTool, McpToolError } from '$lib/server/mcp';

export const load: PageServerLoad = async ({ locals }) => {
	try {
		return { v: await callTool<Record<string, any>>(locals.token!, 'portfolio', 'get_programs') };
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'The portfolio service is not reachable right now.');
	}
};
