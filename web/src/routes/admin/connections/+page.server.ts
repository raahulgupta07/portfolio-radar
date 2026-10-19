import type { Actions, PageServerLoad } from './$types';
import { act, adminCall, loadOrError, str, type Any } from '$lib/server/admin';

export const load: PageServerLoad = async ({ locals }) =>
	loadOrError(async () => ({ c: await adminCall(locals.token!, 'get_connections') }));

export const actions: Actions = {
	test: async ({ locals, request }) => {
		const source = str(await request.formData(), 'source');
		return act(async () => {
			const r = await adminCall(locals.token!, 'test_source', { source });
			return r.ok ? `${source}: connection works, ${r.projects_found} projects found.` : `${source}: ${r.error}`;
		});
	},
	testAll: async ({ locals }) =>
		act(async () => {
			const t = locals.token!;
			const out = await Promise.all(
				['jira', 'openproject', 'multica'].map((source) => adminCall<Any>(t, 'test_source', { source }))
			);
			return out.map((r) => `${r.source}: ${r.ok ? `OK, ${r.projects_found} projects` : r.error}`).join(' · ');
		}),
	sync: async ({ locals, request }) => {
		const source = str(await request.formData(), 'source');
		return act(async () => {
			const r = await adminCall(locals.token!, 'run_sync', { source });
			const s = r.sources[0];
			return s?.ok ? `${source}: synced ${s.projects} projects.` : `${source}: sync failed. ${s?.errors?.[0] ?? ''}`;
		});
	}
};
