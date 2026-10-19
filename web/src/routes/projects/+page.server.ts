import { error } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';
import { callTool, McpToolError } from '$lib/server/mcp';
import type { ProjectRow } from '$lib/types';

export const load: PageServerLoad = async ({ locals }) => {
	try {
		const r = await callTool<{ projects: ProjectRow[] }>(locals.token!, 'portfolio', 'list_projects', {});
		return { projects: r.projects };
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'The portfolio service is not reachable right now. Try again in a minute.');
	}
};
