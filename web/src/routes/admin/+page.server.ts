import { error, fail } from '@sveltejs/kit';
import type { Actions, PageServerLoad } from './$types';
import { callTool, clearCache, McpToolError } from '$lib/server/mcp';

type Any = Record<string, any>;

export const load: PageServerLoad = async ({ locals }) => {
	const t = locals.token!;
	const call = (tool: string, args: Any = {}) => callTool<Any>(t, 'admin', tool, args, { cache: false });
	try {
		const [sources, prefixes, settings, nonCompliant, syncLog] = await Promise.all([
			call('list_sources'),
			call('list_prefixes'),
			call('get_settings'),
			call('get_non_compliant'),
			call('get_sync_log', { limit: 12 })
		]);
		return {
			sources: sources.sources,
			prefixes: prefixes.prefixes,
			settings,
			nonCompliant: nonCompliant.projects,
			syncLog: syncLog.runs
		};
	} catch (e) {
		if (e instanceof McpToolError) error(403, e.message);
		error(503, 'The admin service is not reachable right now.');
	}
};

async function run(token: string, tool: string, args: Any, okMessage: (r: Any) => string) {
	try {
		const r = await callTool<Any>(token, 'admin', tool, args, { cache: false });
		clearCache();
		return { ok: true, message: okMessage(r) };
	} catch (e) {
		return fail(400, { ok: false, message: e instanceof McpToolError ? e.message : 'The gateway is not reachable.' });
	}
}

const num = (f: FormData, k: string) => Number(f.get(k));
const bool = (f: FormData, k: string) => f.get(k) === 'on';

export const actions: Actions = {
	syncAll: async ({ locals }) =>
		run(locals.token!, 'run_sync', {}, (r) =>
			`Sync done. ${r.sources.map((s: Any) => `${s.source}: ${s.ok ? `${s.projects} projects` : 'failed'}`).join(' · ')}`
		),


	addPrefix: async ({ locals, request }) => {
		const f = await request.formData();
		const value = String(f.get('value') ?? '').trim().toUpperCase();
		if (!value) return fail(400, { ok: false, message: 'Type a prefix first.' });
		return run(locals.token!, 'add_prefix', { value: value.endsWith('-') ? value : `${value}-`, description: '' }, () =>
			`Prefix added. Projects with it are picked up from the next sync.`
		);
	},
	togglePrefix: async ({ locals, request }) => {
		const f = await request.formData();
		const value = String(f.get('value'));
		const active = f.get('active') === 'true';
		return run(locals.token!, 'set_prefix_active', { value, active }, () => `${value} is now ${active ? 'on' : 'off'}.`);
	},
	saveSchedule: async ({ locals, request }) => {
		const f = await request.formData();
		return run(locals.token!, 'update_settings', { changes: { sync_time: String(f.get('sync_time')), timezone: String(f.get('timezone')) } }, (r) =>
			`Daily sync now runs at ${r.sync_time} (${r.timezone}).`
		);
	},
	saveRadar: async ({ locals, request }) => {
		const f = await request.formData();
		return run(
			locals.token!,
			'update_settings',
			{
				changes: {
					radar_on: bool(f, 'radar_on'),
					stale_days: num(f, 'stale_days'),
					slipping_window_days: num(f, 'slipping_window_days'),
					overdue_days: num(f, 'overdue_days'),
					behind_points: num(f, 'behind_points')
				}
			},
			() => 'Radar rules saved. They apply from the next check.'
		);
	},
	saveAlerts: async ({ locals, request }) => {
		const f = await request.formData();
		return run(
			locals.token!,
			'update_settings',
			{
				changes: {
					alerts: {
						off_track: bool(f, 'off_track'),
						milestone_overdue: bool(f, 'milestone_overdue'),
						sync_failed: bool(f, 'sync_failed'),
						digest_ready: bool(f, 'digest_ready'),
						no_update: bool(f, 'no_update')
					},
					channels: { in_app: bool(f, 'in_app'), email: bool(f, 'email'), teams: bool(f, 'teams') }
				}
			},
			() => 'Alert settings saved.'
		);
	}
};
