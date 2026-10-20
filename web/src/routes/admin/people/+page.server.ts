import type { Actions, PageServerLoad } from './$types';
import { act, adminCall, loadOrError, str } from '$lib/server/admin';

export const load: PageServerLoad = async ({ locals, url }) =>
	loadOrError(async () => {
		const q = url.searchParams.get('q') ?? '';
		const [people, integrations] = await Promise.all([
			adminCall(locals.token!, 'list_people', { q }),
			adminCall(locals.token!, 'get_integrations')
		]);
		const sso = integrations.services.sso.config;
		return {
			q,
			people: people.people as any[],
			me: locals.user!.id.toLowerCase(),
			sso: { provider: sso.provider as string, groups: sso.groups as any[], ready: integrations.services.sso.status === 'ready' }
		};
	});

export const actions: Actions = {
	save: async ({ locals, request }) => {
		const f = await request.formData();
		const id = str(f, 'id');
		const blocked = f.get('blocked') === 'on';
		const args = { id, name: str(f, 'name') || undefined, extra_roles: f.getAll('extra_roles').map(String), blocked, note: str(f, 'note') };
		return act(async () => {
			await adminCall(locals.token!, 'save_person', args);
			return blocked ? `${id} is blocked. Their next call is refused.` : `${id} saved. It applies on their next call.`;
		});
	}
};
