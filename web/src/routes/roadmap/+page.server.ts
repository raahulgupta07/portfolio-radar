import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { callTool, McpToolError } from '$lib/server/mcp';

export const load: PageServerLoad = async ({ locals }) => {
	try {
		return { road: await callTool<Record<string, any>>(locals.token!, 'portfolio', 'get_roadmap') };
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'The portfolio service is not reachable right now.');
	}
};
