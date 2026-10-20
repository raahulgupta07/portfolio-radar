import { env } from '$env/dynamic/private';
import type { Actions, PageServerLoad } from './$types';
import { act, adminCall, loadOrError, str, type Any } from '$lib/server/admin';

export const load: PageServerLoad = async ({ locals, url }) =>
	loadOrError(async () => ({
		i: await adminCall(locals.token!, 'get_integrations'),
		// What to enter as the Azure Bot's messaging endpoint.
		teamsEndpoint: `${env.ORIGIN || url.origin}/api/teams/messages`,
		// Sign-in itself happens in the web app; these stay settings of the web container.
		web: {
			provider: env.OIDC_ISSUER ? 'keycloak' : env.ENTRA_TENANT_ID ? 'entra' : '',
			issuer: env.OIDC_ISSUER ?? '',
			client_id: env.OIDC_CLIENT_ID || env.ENTRA_CLIENT_ID || '',
			secret_set: !!(env.OIDC_CLIENT_SECRET || env.ENTRA_CLIENT_SECRET),
			scope: env.OIDC_SCOPE || env.ENTRA_API_SCOPE || '',
			dev_login: env.DEV_LOGIN === 'true'
		}
	}));

/** Save a pasted secret first (if any), then the settings that point to it. */
async function saveWithSecret(token: string, name: string, config: Any, secret: { field: string; value: string; fallback: string }) {
	if (secret.value) {
		config[secret.field] ||= secret.fallback;
		await adminCall(token, 'set_secret', { ref: config[secret.field], value: secret.value });
	}
	await adminCall(token, 'save_integration', { name, config });
}

const lines = (v: string) => v.split(/[\n,;]+/).map((x) => x.trim()).filter(Boolean);

export const actions: Actions = {
	saveSso: async ({ locals, request }) => {
		const f = await request.formData();
		const ids = f.getAll('group_id').map(String);
		const names = f.getAll('group_name').map(String);
		const roles = f.getAll('group_role').map(String);
		const groups = ids
			.map((id, i) => ({ group_id: id.trim(), name: names[i]?.trim() ?? '', roles: roles[i] ? [roles[i]] : [] }))
			.filter((g) => g.group_id);
		const provider = str(f, 'provider') === 'keycloak' ? 'keycloak' : 'entra';
		const userApps = str(f, 'user_apps').split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
		return act(async () => {
			await adminCall(locals.token!, 'save_integration', {
				name: 'sso',
				config: {
					provider,
					tenant_id: provider === 'entra' ? str(f, 'tenant_id') : '',
					issuer: provider === 'keycloak' ? str(f, 'issuer') : '',
					internal_url: provider === 'keycloak' ? str(f, 'internal_url') : '',
					audience: str(f, 'audience'),
					default_roles: f.get('default_viewer') === 'on' ? ['viewer'] : [],
					groups,
					user_apps: userApps
				}
			});
			return 'City SSO saved. The gateway uses it at once.';
		});
	},
	saveLlm: async ({ locals, request }) => {
		const f = await request.formData();
		const rulesOnly = f.get('rules_only') === 'true';
		const config = rulesOnly
			? { provider: str(f, 'provider') || 'citygpt', base_url: '', model: '', api_key_ref: '' }
			: { provider: str(f, 'provider'), base_url: str(f, 'base_url'), model: str(f, 'model'), api_key_ref: str(f, 'api_key_ref') };
		return act(async () => {
			await saveWithSecret(locals.token!, 'llm', config, { field: 'api_key_ref', value: String(f.get('api_key') ?? ''), fallback: 'kv://llm-api-key' });
			return rulesOnly ? 'Radar now answers from rules only.' : 'LLM saved. Radar uses it within a minute.';
		});
	},
	saveTeams: async ({ locals, request }) => {
		const f = await request.formData();
		const config: Any = {
			webhook_ref: str(f, 'webhook_ref'),
			channel: str(f, 'channel'),
			bot_app_id: str(f, 'bot_app_id'),
			bot_password_ref: str(f, 'bot_password_ref')
		};
		const botSecret = String(f.get('bot_password') ?? '');
		return act(async () => {
			// Both secrets go straight to the secret store; only their names are saved.
			if (botSecret) {
				config.bot_password_ref ||= 'kv://teams-bot-password';
				await adminCall(locals.token!, 'set_secret', { ref: config.bot_password_ref, value: botSecret });
			}
			await saveWithSecret(locals.token!, 'teams', config, { field: 'webhook_ref', value: String(f.get('webhook') ?? ''), fallback: 'kv://teams-webhook' });
			return 'Teams saved.';
		});
	},
	saveEmail: async ({ locals, request }) => {
		const f = await request.formData();
		const config = {
			smtp_host: str(f, 'smtp_host'),
			smtp_port: Number(f.get('smtp_port') || 587),
			username: str(f, 'username'),
			password_ref: str(f, 'password_ref'),
			sender: str(f, 'sender'),
			recipients: lines(str(f, 'recipients'))
		};
		return act(async () => {
			await saveWithSecret(locals.token!, 'email', config, { field: 'password_ref', value: String(f.get('password') ?? ''), fallback: 'kv://smtp-password' });
			return 'Email saved.';
		});
	},
	test: async ({ locals, request }) => {
		const name = str(await request.formData(), 'name');
		return act(async () => {
			const r = await adminCall(locals.token!, 'test_integration', { name });
			return { ok: r.ok, message: `${r.ok ? 'Test passed' : 'Test failed'}: ${r.detail}`, tested: name };
		});
	}
};
