import type { LayoutServerLoad } from './$types';
import { callTool } from '$lib/server/mcp';
import { initials } from '$lib/server/auth';

type Shell = { today: string; radar: { count: number }; trend: { avg_percent_done: number }[]; sources: { stale: boolean }[] };

export const load: LayoutServerLoad = async ({ locals }) => {
	if (!locals.user || !locals.token) return { user: null, shell: null, today: '' };
	let shell = { radarCount: 0, avg: null as number | null, offline: false };
	let today = new Date().toISOString().slice(0, 10);
	try {
		const o = await callTool<Shell>(locals.token, 'portfolio', 'get_overview', {
			fields: ['today', 'radar.count', 'trend', 'sources[].stale']
		});
		shell = {
			radarCount: o.radar?.count ?? 0,
			avg: o.trend?.length ? o.trend[o.trend.length - 1].avg_percent_done : null,
			offline: (o.sources ?? []).some((s) => s.stale)
		};
		today = o.today ?? today;
	} catch {
		// The shell still renders if the gateway is down; the page shows the error.
	}
	return {
		user: { ...locals.user, initials: initials(locals.user.name) },
		isAdmin: locals.user.roles.includes('admin'),
		shell,
		today
	};
};
