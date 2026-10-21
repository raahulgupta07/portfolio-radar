import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { callTool, clearCache, McpToolError } from '$lib/server/mcp';

type Any = Record<string, any>;

export const load: PageServerLoad = async ({ locals }) => {
	try {
		return { v: await callTool<Any>(locals.token!, 'portfolio', 'get_programs') };
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'The portfolio service is not reachable right now.');
	}
};

// Edits: Admin only. They are saved in Radar's own tables and logged in Activity.
// Nothing is ever written to JIRA, OpenProject or Multica.
async function run(locals: App.Locals, tool: string, args: Any, message: (r: Any) => string) {
	if (!locals.user?.roles.includes('admin')) return fail(403, { ok: false, message: 'Only an admin can change program data.' });
	try {
		const r = await callTool<Any>(locals.token!, 'portfolio', tool, args, { cache: false });
		clearCache();
		return { ok: true, message: message(r), id: String(r.id ?? '') };
	} catch (e) {
		return fail(400, { ok: false, message: e instanceof McpToolError ? e.message : 'The gateway is not reachable.' });
	}
}

/** The drawer sends its fields as one JSON text, plus who is saving and what version it opened. */
function saveArgs(f: FormData) {
	let data: Any = {};
	try {
		const p = JSON.parse(String(f.get('payload') ?? '{}'));
		if (p && typeof p === 'object' && !Array.isArray(p)) data = p;
	} catch {
		// An unreadable payload is sent as empty and refused by the gateway with a clear message.
	}
	const base = String(f.get('base_updated_at') ?? '');
	return { data, base_updated_at: base || undefined, by_name: String(f.get('by') ?? '').trim().slice(0, 100) || undefined };
}
const deleteArgs = (f: FormData) => ({ id: String(f.get('id') ?? ''), by_name: String(f.get('by') ?? '').trim().slice(0, 100) || undefined });

const saved = (what: string) => (r: Any) =>
	r.created ? `${what} added: ${r.id}.` : r.changes ? `${what} ${r.id} saved. ${r.changes} change${r.changes === 1 ? '' : 's'} logged in Activity.` : `Nothing to save, ${r.id} is unchanged.`;

export const actions: Actions = {
	saveProject: async ({ locals, request }) => run(locals, 'save_project', saveArgs(await request.formData()), saved('Project')),
	deleteProject: async ({ locals, request }) => run(locals, 'delete_project', deleteArgs(await request.formData()), (r) => `Project ${r.id} deleted.`),
	saveProgram: async ({ locals, request }) => run(locals, 'save_program', saveArgs(await request.formData()), saved('Program')),
	deleteProgram: async ({ locals, request }) => run(locals, 'delete_program', deleteArgs(await request.formData()), (r) => `Program ${r.id} deleted.`)
};
