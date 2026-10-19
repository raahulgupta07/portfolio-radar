import type { Actions, PageServerLoad } from './$types';
import { act, adminCall, loadOrError, str, type Any } from '$lib/server/admin';

export const load: PageServerLoad = async ({ locals }) =>
	loadOrError(async () => {
		const t = locals.token!;
		const [tools, changes, audit] = await Promise.all([
			adminCall(t, 'list_tools'),
			adminCall(t, 'list_tool_changes'),
			adminCall(t, 'get_audit', { limit: 8 })
		]);
		return { tools: tools.tools, changes: changes.changes, audit: audit.calls };
	});

export const actions: Actions = {
	toolStatus: async ({ locals, request }) => {
		const f = await request.formData();
		const server = str(f, 'server');
		const tool = str(f, 'tool');
		const status = str(f, 'status');
		return act(async () => {
			await adminCall(locals.token!, 'set_tool_status', { server, tool, status });
			return `${server}.${tool} is now ${status}.`;
		});
	},
	serverStatus: async ({ locals, request }) => {
		const f = await request.formData();
		const server = str(f, 'server');
		const status = str(f, 'status');
		return act(async () => {
			const t = locals.token!;
			const tools: Any[] = (await adminCall(t, 'list_tools')).tools;
			// Tools waiting for review stay as they are: they need a decision first.
			const todo = tools.filter((x) => x.server === server && x.status !== 'review' && x.status !== status);
			for (const x of todo) await adminCall(t, 'set_tool_status', { server, tool: x.tool, status });
			return `${todo.length} ${todo.length === 1 ? 'tool' : 'tools'} on /${server}/mcp turned ${status}.`;
		});
	},
	decideChange: async ({ locals, request }) => {
		const f = await request.formData();
		const approve = f.get('approve') === 'true';
		return act(async () => {
			await adminCall(locals.token!, 'decide_tool_change', { change_id: Number(f.get('change_id')), approve });
			return approve ? 'Change approved. The tool is on.' : 'Change rejected. The tool is off.';
		});
	}
};
