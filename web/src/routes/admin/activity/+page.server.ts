import type { PageServerLoad } from './$types';
import { adminCall, loadOrError } from '$lib/server/admin';

export const load: PageServerLoad = async ({ locals, url }) => {
	const outcome = url.searchParams.get('outcome');
	const caller = url.searchParams.get('caller')?.trim();
	return loadOrError(async () => {
		const r = await adminCall(locals.token!, 'get_audit', {
			limit: 200,
			...(outcome === 'denied' || outcome === 'error' ? { outcome } : {}),
			...(caller ? { caller_id: caller } : {})
		});
		return { calls: r.calls, outcome: outcome ?? 'all', caller: caller ?? '' };
	});
};
