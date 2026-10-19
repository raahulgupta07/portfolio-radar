import { error } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { act, adminCall, loadOrError, str, type Any } from '$lib/server/admin';

const SOURCES = ['jira', 'openproject', 'multica'];

export const load: PageServerLoad = async ({ locals, params }) => {
	if (!SOURCES.includes(params.source)) error(404, 'No such source.');
	return loadOrError(async () => ({ s: await adminCall(locals.token!, 'get_source', { source: params.source }) }));
};

export const actions: Actions = {
	saveConnection: async ({ locals, request, params }) => {
		const f = await request.formData();
		const t = locals.token!;
		const token = String(f.get('token') ?? '');
		let ref = str(f, 'secret_ref');
		if (token && !ref) ref = `kv://${params.source}-read-token`;
		return act(async () => {
			// The token goes straight to the secret store; only its name is saved with the source.
			if (token) await adminCall(t, 'set_secret', { ref, value: token });
			await adminCall(t, 'save_source', {
				source: params.source,
				base_url: str(f, 'base_url'),
				flavor: str(f, 'flavor'),
				auth_method: str(f, 'auth_method'),
				account: str(f, 'account'),
				secret_ref: ref,
				enabled: f.get('enabled') === 'on'
			});
			return token ? `Saved. The token is in the secret store as ${ref}.` : 'Connection saved. It is used from the next sync.';
		});
	},
	check: async ({ locals, params }) =>
		act(async () => {
			const r = await adminCall(locals.token!, 'check_source', { source: params.source });
			return { message: r.ok ? 'Check passed.' : 'Check found problems. See step 2.', check: r };
		}),
	saveMapping: async ({ locals, request, params }) => {
		const f = await request.formData();
		const statuses = f.getAll('status').map(String);
		const values = f.getAll('app_status').map(String);
		const defaults: Any = JSON.parse(String(f.get('defaults') ?? '{}'));
		const mapping: Record<string, string> = {};
		statuses.forEach((st, i) => {
			const v = values[i];
			// Keep only what differs from the default mapping; empty means "not mapped yet".
			if (st.trim() && v && defaults[st.toLowerCase()] !== v) mapping[st.trim()] = v;
		});
		const extra = str(f, 'new_status');
		const extraValue = str(f, 'new_app_status');
		if (extra && extraValue) mapping[extra] = extraValue;
		return act(async () => {
			await adminCall(locals.token!, 'save_status_mapping', { source: params.source, mapping });
			return 'Status mapping saved. It applies from the next sync.';
		});
	},
	toolStatus: async ({ locals, request, params }) => {
		const f = await request.formData();
		const tool = str(f, 'tool');
		const status = str(f, 'status');
		return act(async () => {
			await adminCall(locals.token!, 'set_tool_status', { server: params.source, tool, status });
			return `${params.source}.${tool} is now ${status}.`;
		});
	}
};
