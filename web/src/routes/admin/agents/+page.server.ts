import { env } from '$env/dynamic/private';
import type { Actions, PageServerLoad } from './$types';
import { act, adminCall, loadOrError, str } from '$lib/server/admin';

export const load: PageServerLoad = async ({ locals }) =>
	loadOrError(async () => {
		const t = locals.token!;
		const [agents, integrations] = await Promise.all([adminCall(t, 'list_agents'), adminCall(t, 'get_integrations')]);
		return {
			agents: agents.agents as any[],
			built_in: agents.built_in as any[],
			servers: agents.servers as { server: string; title: string }[],
			roles: agents.roles as Record<string, string[]>,
			audience: integrations.services.sso.config.audience as string,
			tenant: integrations.services.sso.config.tenant_id as string,
			// The address agents use. Set MCP_PUBLIC_URL when the gateway is reached by another name outside.
			publicUrl: (env.MCP_PUBLIC_URL || env.GATEWAY_URL || 'http://localhost:8000').replace(/\/$/, '')
		};
	});

export const actions: Actions = {
	save: async ({ locals, request }) => {
		const f = await request.formData();
		const id = str(f, 'id');
		const kind = str(f, 'kind') || 'agent';
		const args = {
			...(id ? { id: Number(id) } : {}),
			name: str(f, 'name'),
			kind,
			app_id: str(f, 'app_id'),
			roles: kind === 'agent' ? ['agent'] : f.getAll('roles').map(String),
			servers: f.getAll('servers').map(String),
			rate_limit: Number(f.get('rate_limit') || 120),
			enabled: true
		};
		return act(async () => {
			const r = await adminCall(locals.token!, 'save_agent', args);
			const preview = await adminCall(locals.token!, 'preview_agent', { id: r.id });
			return { message: `${args.name} saved. Its tokens work at once.`, saved: r.id, preview };
		});
	},
	enable: async ({ locals, request }) => {
		const f = await request.formData();
		const enabled = f.get('enabled') === 'true';
		return act(async () => {
			await adminCall(locals.token!, 'set_agent_enabled', { id: Number(f.get('id')), enabled });
			return enabled ? 'Agent turned on.' : 'Agent turned off. Its tokens are refused from now on.';
		});
	},
	preview: async ({ locals, request }) => {
		const id = Number((await request.formData()).get('id'));
		return act(async () => {
			const preview = await adminCall(locals.token!, 'preview_agent', { id });
			return { message: `${preview.caller_id} may use ${preview.tool_count} tools.`, saved: id, preview };
		});
	}
};
