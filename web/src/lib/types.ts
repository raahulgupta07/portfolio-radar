// Shapes returned by the gateway's /portfolio tools (see backend/app/portfolio/queries.py).
import type { Health } from './format';

export type ProjectRow = {
	code: string;
	short: string;
	name: string;
	health: Health;
	health_label: string;
	health_reasons: string[];
	team: string;
	owner: string | null;
	source: string;
	source_name: string;
	stale: boolean;
	status: string;
	percent_done: number | null;
	next_milestone: string | null;
	next_milestone_due: string | null;
	strategy: string | null;
	prefix: string;
	updated: string | null;
	synced_at: string | null;
	source_url: string | null;
	start_date: string | null;
	end_date: string | null;
};

export type SourceInfo = {
	id: string;
	name: string;
	team: string;
	status: string;
	last_sync_at: string | null;
	last_good_sync_at: string | null;
	error: string | null;
	stale: boolean;
	projects: number;
	avg_percent_done?: number | null;
};

export type Finding = { id: number; type: string; severity: string; text: string; project_id: number | null };

export type Overview = {
	today: string;
	last_sync_at: string | null;
	total: number;
	tiles: { health: Health; label: string; count: number; change: number | null; note: string }[];
	sources: SourceInfo[];
	trend: { date: string; avg_percent_done: number }[];
	progress: { code: string; short: string; source: string; percent_done: number | null; health: Health }[];
	next_milestones: {
		date: string;
		name: string;
		code: string;
		short: string;
		project: string;
		overdue: boolean;
		days: number;
		note: string;
		health: Health;
	}[];
	projects: ProjectRow[];
	radar: { checked_at: string | null; projects_checked: number; count: number; items: Finding[] };
};
