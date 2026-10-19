import type { RequestHandler } from './$types';
import { callTool } from '$lib/server/mcp';
import type { ProjectRow } from '$lib/types';

const COLS: [string, (r: ProjectRow) => unknown][] = [
	['Code', (r) => r.code],
	['Name', (r) => r.name],
	['Health', (r) => r.health_label],
	['Team', (r) => r.team],
	['Owner', (r) => r.owner],
	['Source', (r) => r.source_name],
	['Stale', (r) => (r.stale ? 'yes' : 'no')],
	['Status', (r) => r.status],
	['% done', (r) => r.percent_done],
	['Next milestone', (r) => r.next_milestone],
	['Due', (r) => r.next_milestone_due],
	['Start', (r) => r.start_date],
	['End', (r) => r.end_date],
	['Strategy', (r) => r.strategy],
	['Updated in source', (r) => r.updated],
	['Synced', (r) => r.synced_at],
	['Edit in source', (r) => r.source_url]
];

function cell(v: unknown): string {
	const s = v == null ? '' : String(v);
	// Quote, and stop spreadsheet formulas from running.
	const safe = /^[=+\-@\t\r]/.test(s) ? `'${s}` : s;
	return `"${safe.replace(/"/g, '""')}"`;
}

export const GET: RequestHandler = async ({ locals }) => {
	const data = await callTool<{ projects: ProjectRow[] }>(locals.token!, 'portfolio', 'list_projects', {});
	const lines = [COLS.map(([h]) => cell(h)).join(','), ...data.projects.map((r) => COLS.map(([, f]) => cell(f(r))).join(','))];
	return new Response('﻿' + lines.join('\r\n'), {
		headers: {
			'content-type': 'text/csv; charset=utf-8',
			'content-disposition': `attachment; filename="portfolio-${new Date().toISOString().slice(0, 10)}.csv"`
		}
	});
};
