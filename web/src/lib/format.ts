// Shared display helpers: health and source colours (docs/design-system.md),
// dates in Asia/Yangon, short labels.

export const TZ = 'Asia/Yangon';

export type Health = 'on_track' | 'at_risk' | 'off_track' | 'done';

export const HEALTH: Record<Health, { label: string; dot: string; bg: string; ink: string }> = {
	on_track: { label: 'On track', dot: '#2E8B57', bg: '#E2F2E7', ink: '#1F5C3A' },
	at_risk: { label: 'At risk', dot: '#B98300', bg: '#FBE6A9', ink: '#4A4128' },
	off_track: { label: 'Off track', dot: '#C23B3B', bg: '#F8CDD0', ink: '#4E2F32' },
	done: { label: 'Done', dot: '#111111', bg: '#CFE3FB', ink: '#33404F' }
};

export const SOURCE: Record<string, { label: string; short: string; bg: string; bar: string }> = {
	jira: { label: 'JIRA', short: 'JIRA', bg: '#CFE3FB', bar: '#7FB2EC' },
	openproject: { label: 'OpenProject', short: 'OP', bg: '#FBE6A9', bar: '#EAC45A' },
	multica: { label: 'Multica', short: 'MU', bg: '#F8CDD0', bar: '#EE9AA0' }
};

export const STATUS_DOT: Record<string, string> = {
	'In progress': 'background:#111111',
	Done: 'background:#2E8B57',
	'On hold': 'background:#E0662E',
	'Not started': 'background:#FFFFFF;box-shadow:inset 0 0 0 1.5px #111111'
};

export function health(h: string | null | undefined) {
	return HEALTH[(h ?? 'on_track') as Health] ?? HEALTH.on_track;
}

export function source(id: string) {
	return SOURCE[id] ?? { label: id, short: id.slice(0, 2).toUpperCase(), bg: '#F1F5F2', bar: '#C9DCCF' };
}

function d(v: string | Date): Date {
	if (v instanceof Date) return v;
	// Plain dates (YYYY-MM-DD) are calendar days, not instants.
	return /^\d{4}-\d{2}-\d{2}$/.test(v) ? new Date(`${v}T12:00:00Z`) : new Date(v);
}

const isPlain = (v: string | Date) => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v);

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

/** Calendar parts in Yangon time (or as written, for plain dates). */
function parts(v: string | Date): { y: number; m: number; d: number; hh: string; mm: string } {
	const x = d(v);
	if (isPlain(v)) return { y: x.getUTCFullYear(), m: x.getUTCMonth(), d: x.getUTCDate(), hh: '00', mm: '00' };
	const f = new Intl.DateTimeFormat('en-GB', {
		timeZone: TZ, year: 'numeric', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false
	}).formatToParts(x);
	const g = (t: string) => f.find((p) => p.type === t)?.value ?? '0';
	return { y: +g('year'), m: +g('month') - 1, d: +g('day'), hh: g('hour'), mm: g('minute') };
}

const pad = (n: number) => String(n).padStart(2, '0');

/** 19 Oct */
export function day(v: string | Date | null | undefined): string {
	if (!v) return '—';
	const p = parts(v);
	return `${pad(p.d)} ${MONTHS[p.m]}`;
}

/** 19 Oct 2026 */
export function fullDate(v: string | Date | null | undefined): string {
	if (!v) return '—';
	const p = parts(v);
	return `${pad(p.d)} ${MONTHS[p.m]} ${p.y}`;
}

/** 19 Oct, 02:00 (Yangon time) */
export function dayTime(v: string | Date | null | undefined): string {
	if (!v) return '—';
	const p = parts(v);
	return `${pad(p.d)} ${MONTHS[p.m]}, ${p.hh}:${p.mm}`;
}

export function monthDay(v: string): { month: string; day: string } {
	const p = parts(v);
	return { month: MONTHS[p.m].toUpperCase(), day: pad(p.d) };
}

export function plural(n: number, word: string): string {
	return `${n} ${word}${n === 1 ? '' : 's'}`;
}

export function ago(v: string | null | undefined, now = new Date()): string {
	if (!v) return '—';
	const days = Math.floor((now.getTime() - d(v).getTime()) / 86_400_000);
	if (days <= 0) return 'today';
	if (days === 1) return '1 day ago';
	return `${days} days ago`;
}
