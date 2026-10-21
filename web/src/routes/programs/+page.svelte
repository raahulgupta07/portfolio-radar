<script lang="ts">
	import { onMount } from 'svelte';
	import { day, dayTime } from '$lib/format';
	import ProjectDrawer from '$lib/components/ProjectDrawer.svelte';
	import CharterDrawer from '$lib/components/CharterDrawer.svelte';

	let { data } = $props();
	const v = $derived(data.v);
	const programs = $derived<any[]>(v.programs);

	type Tab = 'programs' | 'charter' | 'projects' | 'timeline' | 'raci' | 'activity';
	let sel = $state(''); // program id, '' = all programs
	let tab = $state<Tab>('programs');
	let q = $state('');
	let ws = $state('');
	let status = $state('');
	let health = $state('');
	let sort = $state('group');
	let raciMode = $state<'project' | 'person'>('project');
	let showMs = $state(true);

	// Admin edits. They are saved in Radar's own tables and logged in Activity with this name.
	const isAdmin = $derived(!!data.isAdmin);
	let drawer = $state<null | { kind: 'project' | 'charter'; project?: any; program?: any }>(null);
	let notice = $state('');
	let by = $state('');
	onMount(() => {
		try {
			by = localStorage.getItem('radar.by') || data.user?.name || '';
		} catch {
			by = data.user?.name ?? '';
		}
	});
	function saveName() {
		try {
			localStorage.setItem('radar.by', by);
		} catch {
			// The name is still used for this visit.
		}
	}
	const openProject = (project: any = null) => (drawer = { kind: 'project', project });
	const openCharter = (program: any = null) => (drawer = { kind: 'charter', program });
	function done(message: string) {
		drawer = null;
		notice = message;
		if (sel && !programs.some((x) => x.id === sel)) sel = '';
	}

	const prog = $derived(programs.find((p) => p.id === sel) ?? null);
	const scoped = $derived<any[]>(sel ? v.projects.filter((p: any) => p.program === sel) : v.projects);
	const workstreams = $derived([...new Set(scoped.map((p: any) => p.workstream).filter(Boolean))].sort() as string[]);
	const progName = (id: string) => programs.find((p) => p.id === id)?.name ?? id;
	const acts = $derived<any[]>(sel ? v.activity.filter((a: any) => (a.kind === 'program' ? a.ref_id === sel : v.projects.find((p: any) => p.id === a.ref_id)?.program === sel)) : v.activity);

	// Status colours: chip fill, chip text, bar.
	const ST: Record<string, [string, string, string]> = {
		Completed: ['#E2F2E7', '#1F5C3A', '#2E8B57'],
		'Dev Complete': ['#D5EFEA', '#14584F', '#3FA9A0'],
		'In UAT': ['#E4DAF5', '#3D2E6E', '#8C7BD6'],
		'In Progress': ['#CFE3FB', '#1F3F66', '#4F8FDB'],
		'Pending Approval': ['#FBE6A9', '#4A4128', '#D9A21B'],
		Planned: ['#EEF2EF', '#3E4640', '#A9B8AE'],
		'On Hold': ['#FAD9C3', '#6B3513', '#E0773A'],
		Cancelled: ['#F8CDD0', '#4E2F32', '#D2606A']
	};
	const st = (s: string) => ST[s] ?? ST.Planned;
	const ACTIVE = ['In Progress', 'In UAT', 'Dev Complete'];
	const names = (s: string) => (s || '').split(',').map((x) => x.trim()).filter(Boolean);

	const count = (f: string) => scoped.filter((p: any) => match(p, f)).length;
	const avgPct = $derived(scoped.length ? Math.round(scoped.reduce((a: number, p: any) => a + p.pct, 0) / scoped.length) : 0);
	// The eight summary tiles of the approved design. Most filter the Projects tab when pressed.
	const TILES = [
		{ k: '', label: 'Projects', bg: '#FFFFFF', n: () => scoped.length, suffix: '', note: () => (prog ? prog.name : `In ${programs.length} programs`) },
		{ k: 'Completed', label: 'Completed', bg: '#E2F2E7', n: () => count('Completed'), suffix: '', note: () => (scoped.length ? `${Math.round((count('Completed') / scoped.length) * 100)}% of all` : '') },
		{ k: '@active', label: 'In progress', bg: '#CFE3FB', n: () => count('@active'), suffix: '', note: () => 'Now active' },
		{ k: 'avg', label: 'Average progress', bg: '#FFFFFF', n: () => avgPct, suffix: '%', note: () => 'Across all projects' },
		{ k: '@red', label: 'Red health', bg: '#F8CDD0', n: () => count('@red'), suffix: '', note: () => 'Need a decision' },
		{ k: '@overdue', label: 'Overdue', bg: '#F8CDD0', n: () => count('@overdue'), suffix: '', note: () => 'Past target date' },
		{ k: '@due30', label: 'Due in 30 days', bg: '#FBE6A9', n: () => count('@due30'), suffix: '', note: () => 'Coming up' },
		{ k: 'On Hold', label: 'On hold', bg: '#E4DAF5', n: () => count('On Hold'), suffix: '', note: () => 'Paused' }
	];
	const HEALTH: Record<string, [string, string]> = { Green: ['#E2F2E7', '#1F5C3A'], Amber: ['#FBE6A9', '#4A4128'], Red: ['#F8CDD0', '#4E2F32'] };
	const hl = (h: string) => HEALTH[h] ?? ['#EEF2EF', '#3E4640'];
	// Facts for one program card: period, budget used, next open milestone.
	function pcard(p: any) {
		const bt = p.budget_totals;
		const used = bt.prudent && bt.actual != null ? Math.round((bt.actual / bt.prudent) * 100) : null;
		const next = (p.milestones || [])
			.filter((m: any) => !m.actual && m.target && m.target >= v.today)
			.sort((a: any, b: any) => a.target.localeCompare(b.target))[0];
		return {
			mine: v.projects.filter((x: any) => x.program === p.id),
			period: p.start || p.end ? `${dt(p.start)} to ${dt(p.end)}` : '—',
			budget: bt.prudent ? `${[p.currency, money(bt.prudent)].filter(Boolean).join(' ')}${used != null ? `, ${used}% used` : ''}` : '—',
			next: next ? `${next.name}, ${dt(next.target)}` : '—',
			done: p.checks.filter((c: any) => c.done).length
		};
	}
	const match = (p: any, f: string) =>
		!f ||
		(f === '@active' ? ACTIVE.includes(p.status)
		: f === '@red' ? p.health === 'Red'
		: f === '@open' ? p.open
		: f === '@due30' ? p.open && p.days_to_target != null && p.days_to_target >= 0 && p.days_to_target <= 30
		: f === '@overdue' ? p.open && p.days_to_target != null && p.days_to_target < 0
		: f === '@noa' ? p.open && names(p.raci.A).length !== 1
		: p.status === f);

	const rows = $derived.by(() => {
		const t = q.trim().toLowerCase();
		const out = scoped.filter(
			(p: any) =>
				(!ws || p.workstream === ws) &&
				(!health || p.health === health) &&
				match(p, status) &&
				(!t || [p.id, p.name, p.owner, p.next_step, p.decision, p.workstream, p.raci.R, p.raci.A, p.raci.C, p.raci.I].join(' ').toLowerCase().includes(t))
		);
		const by: Record<string, (a: any, b: any) => number> = {
			group: () => 0,
			target: (a, b) => (a.target || '9999').localeCompare(b.target || '9999'),
			name: (a, b) => a.name.localeCompare(b.name),
			progress: (a, b) => b.pct - a.pct,
			status: (a, b) => v.statuses.indexOf(a.status) - v.statuses.indexOf(b.status),
			updated: (a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')
		};
		return [...out].sort(by[sort]);
	});

	// The Projects table, with a heading row per program when grouped.
	const listed = $derived.by(() => {
		if (sort !== 'group' || sel) return rows.map((p: any) => ({ p, g: '', n: 0 }));
		const out: { p: any; g: string; n: number }[] = [];
		let last = '';
		for (const p of rows) {
			if (p.program !== last) {
				last = p.program;
				out.push({ p: null, g: progName(p.program), n: rows.filter((x: any) => x.program === p.program).length });
			}
			out.push({ p, g: '', n: 0 });
		}
		return out;
	});
	const filtered = $derived(!!(q || ws || status || health || sort !== 'group'));
	function clearFilters() {
		q = '';
		ws = '';
		status = '';
		health = '';
		sort = 'group';
	}
	const ini = (n: string) => (n || '?').split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join('') || '?';
	const raciShort = (p: any) => [p.raci.R && `R ${p.raci.R}`, p.raci.A && `A ${p.raci.A}`].filter(Boolean).join(', ') || '—';
	// Bar colours of the timeline legend.
	const BAR: Record<string, string> = { Completed: '#3A9A68', 'In Progress': '#111111', 'In UAT': '#111111', 'Dev Complete': '#111111', 'Pending Approval': '#B9C7BD', Planned: '#B9C7BD', 'On Hold': '#D27A45', Cancelled: '#D2606A' };

	function tile(k: string) {
		status = k === '' || status === k ? '' : k;
		tab = 'projects';
		if (k === '') {
			q = '';
			ws = '';
		}
	}
	function pick(id: string) {
		sel = id;
		ws = '';
		tab = id ? 'charter' : 'programs';
	}
	const money = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 0 }));
	const num = (x: unknown) => (x === '' || x == null || isNaN(+x as number) ? null : +(x as number));
	const ratio = (a: unknown, b: unknown) => (num(a) && num(b) ? `${(num(b)! / num(a)!).toFixed(1)}×` : '—');
	const dt = (s: string) => (s ? day(s) : '—');
	const due = (p: any) =>
		!p.open || p.days_to_target == null ? '' : p.days_to_target < 0 ? `${-p.days_to_target}d past` : p.days_to_target === 0 ? 'due today' : `in ${p.days_to_target}d`;
	const check = (p: any) => (!p.open ? 'Closed' : names(p.raci.A).length === 1 ? 'OK' : names(p.raci.A).length === 0 ? 'No accountable' : `${names(p.raci.A).length} accountables`);

	// Status bar for a list of projects, in status order.
	const segs = (list: any[]) =>
		v.statuses.map((s: string) => ({ s, n: list.filter((p) => p.status === s).length })).filter((x: any) => x.n);

	// RACI by person.
	const people = $derived.by(() => {
		const m = new Map<string, { name: string; R: number; A: number; C: number; I: number; ids: string[] }>();
		for (const p of rows)
			for (const k of ['R', 'A', 'C', 'I'] as const)
				for (const n of names(p.raci[k])) {
					const key = n.toLowerCase();
					const e = m.get(key) ?? { name: n, R: 0, A: 0, C: 0, I: 0, ids: [] };
					e[k]++;
					if (!e.ids.includes(p.id)) e.ids.push(p.id);
					m.set(key, e);
				}
		return [...m.values()].sort((a, b) => b.A - a.A || b.R - a.R || a.name.localeCompare(b.name));
	});

	// Timeline.
	const ms = (s: string) => (s ? Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)) : 0);
	const tl = $derived.by(() => {
		const todayMs = ms(v.today);
		const progs = sel ? programs.filter((p) => p.id === sel) : programs;
		const dated = rows.filter((p: any) => p.start || p.target);
		const undated = rows.filter((p: any) => !p.start && !p.target);
		const mrows: any[] = [];
		if (showMs) for (const pr of progs) for (const m of pr.milestones || []) if (m.start || m.target) mrows.push({ pr, m });
		let lo = todayMs;
		let hi = todayMs;
		const ext = (s: string) => {
			const t = ms(s);
			if (t) {
				lo = Math.min(lo, t);
				hi = Math.max(hi, t);
			}
		};
		for (const p of dated) {
			ext(p.start);
			ext(p.target);
		}
		for (const { m } of mrows) {
			ext(m.start);
			ext(m.target);
			ext(m.actual);
		}
		const lod = new Date(lo);
		const hid = new Date(hi);
		const start = Date.UTC(lod.getUTCFullYear(), lod.getUTCMonth(), 1);
		let end = Date.UTC(hid.getUTCFullYear(), hid.getUTCMonth() + 2, 1);
		const minEnd = new Date(start);
		const sixM = Date.UTC(minEnd.getUTCFullYear(), minEnd.getUTCMonth() + 6, 1);
		if (end < sixM) end = sixM;
		const span = end - start;
		const pos = (t: number) => Math.max(0, Math.min(100, ((t - start) / span) * 100));
		const months: { label: string; left: number; width: number }[] = [];
		for (let t = start, i = 0; t < end; i++) {
			const d = new Date(t);
			const next = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
			const label = d.toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' }) + (d.getUTCMonth() === 0 || i === 0 ? ` ${d.getUTCFullYear()}` : '');
			months.push({ label, left: pos(t), width: pos(next) - pos(t) });
			t = next;
		}
		const out: any[] = [];
		const groups = sel ? [progs[0]].filter(Boolean) : progs;
		// A charter milestone shows as a diamond on the project that links to it; one nobody links to gets its own row.
		const linked = new Set(dated.filter((p: any) => p.milestone_id).map((p: any) => `${p.program}|${p.milestone_id}`));
		for (const pr of groups) {
			out.push({ t: 'head', label: pr.name });
			for (const p of dated.filter((x: any) => x.program === pr.id)) {
				const hasS = !!p.start;
				const l = pos(ms(p.start || p.target));
				const r = pos(ms(p.target || p.start));
				const m = showMs && p.milestone_id ? (pr.milestones || []).find((x: any) => x.id === p.milestone_id) : null;
				out.push({ t: 'proj', label: `${p.id}  ${p.name}`, sub: `${p.workstream || progName(p.program)} · ${p.status} · ${p.pct}%`, left: l, width: Math.max(1.2, r - l), bar: hasS && !!p.target, pin: !!p.target, pinAt: r, color: BAR[p.status] ?? '#B9C7BD', pct: p.pct, dia: m && (m.target || m.start) ? pos(ms(m.target || m.start)) : null, diaName: m?.name ?? '' });
			}
			for (const { m } of mrows.filter((r) => r.pr.id === pr.id && !linked.has(`${r.pr.id}|${r.m.id}`))) {
				out.push({ t: 'ms', label: `Milestone: ${m.name}`, sub: `${dt(m.start)} to ${dt(m.target)}`, dia: pos(ms(m.target || m.start)), diaName: m.name, actual: m.actual ? pos(ms(m.actual)) : null });
			}
		}
		return { months, today: pos(todayMs), rows: out, undated };
	});

	// Excel opens a CSV with a byte-order mark and UTF-8 text correctly.
	function download(name: string, text: string, type: string) {
		const blob = new Blob([text], { type });
		const a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = name;
		a.click();
		URL.revokeObjectURL(a.href);
	}
	function exportCsv() {
		const head = ['ID', 'Program', 'Project', 'Workstream', 'Owner', 'Status', 'Health', '% complete', 'Start', 'Target', 'Responsible', 'Accountable', 'Consulted', 'Informed', 'Next step', 'Decision needed', 'Remarks'];
		const cell = (x: unknown) => `"${String(x ?? '').replace(/"/g, '""')}"`;
		const lines = rows.map((p: any) => [p.id, progName(p.program), p.name, p.workstream, p.owner, p.status, p.health, p.pct, p.start, p.target, p.raci.R, p.raci.A, p.raci.C, p.raci.I, p.next_step, p.decision, p.remarks].map(cell).join(','));
		download(`programs-${prog?.id ?? 'all'}.csv`, '﻿' + [head.map(cell).join(','), ...lines].join('\r\n'), 'text/csv;charset=utf-8');
	}
	const exportJson = () => download('program-office.json', JSON.stringify(v, null, 2), 'application/json');
</script>

<svelte:head><title>Programs · Portfolio Radar</title></svelte:head>

<header class="title-row">
	<div>
		<div class="t"><h1>Programs</h1><span class="cnt tabular">{programs.length}</span></div>
		<div class="sub">
			{isAdmin ? 'Edits are saved in Radar and logged in Activity. JIRA, OpenProject and Multica are never changed.' : 'Program office data, read-only.'}
			{v.imported_at ? ` Imported ${day(v.imported_at)}.` : ''} Today {day(v.today)}
		</div>
	</div>
	<div class="acts">
		{#if isAdmin}
			<label class="who">Your name<input type="text" bind:value={by} onchange={saveName} maxlength="100" autocomplete="name" /></label>
		{/if}
		<button type="button" class="pill light" onclick={exportJson}>Backup JSON</button>
		{#if scoped.length}<button type="button" class="pill light" onclick={exportCsv}>Download Excel</button>{/if}
		{#if isAdmin && programs.length}<button type="button" class="pill dark" onclick={() => openProject()}>+ Add project</button>{/if}
	</div>
</header>

{#if notice}
	<p class="notice" role="status">{notice} <button type="button" onclick={() => (notice = '')}>Dismiss</button></p>
{/if}

{#if !programs.length}
	<section class="card empty">
		<h2>No program office data yet</h2>
		<p>An admin loads the program office file with <code>python -m app.adapter po-import &lt;file&gt;</code>. Programs, charters, budgets, RACI and next steps then show here.{isAdmin ? ' Or add the first program here.' : ''}</p>
		{#if isAdmin}<button type="button" class="pill dark" onclick={() => openCharter()}>+ Add program</button>{/if}
	</section>
{:else}
	<nav class="chips" aria-label="Programs">
		<button type="button" class:on={!sel} onclick={() => pick('')}>All programs <span>{v.kpis.projects}</span></button>
		{#each programs as p (p.id)}
			<button type="button" class:on={sel === p.id} onclick={() => pick(p.id)}>{p.name} <span>{p.kpis.projects}</span></button>
		{/each}
		{#if isAdmin}<button type="button" class="addp" onclick={() => openCharter()}>+ Add program</button>{/if}
	</nav>

	<section class="kpis" aria-label="Summary">
		{#each TILES as t (t.label)}
			{@const n = t.n()}
			<button type="button" class="kpi" disabled={t.k === 'avg'} style="background:{n && t.bg !== '#FFFFFF' ? t.bg : '#FFFFFF'}" aria-pressed={t.k !== '' && t.k !== 'avg' && status === t.k} onclick={() => tile(t.k)}>
				<span class="kl">{t.label}</span><span class="kv tabular">{n}{t.suffix}</span><span class="kn">{t.note()}</span>
			</button>
		{/each}
	</section>

	<div class="tabs" role="tablist" aria-label="Views">
		{#if prog}
			<button role="tab" aria-selected={tab === 'charter'} class:on={tab === 'charter'} onclick={() => (tab = 'charter')}>Charter</button>
		{:else}
			<button role="tab" aria-selected={tab === 'programs'} class:on={tab === 'programs'} onclick={() => (tab = 'programs')}>Programs <span>{programs.length}</span></button>
		{/if}
		<button role="tab" aria-selected={tab === 'projects'} class:on={tab === 'projects'} onclick={() => (tab = 'projects')}>Projects <span>{scoped.length}</span></button>
		<button role="tab" aria-selected={tab === 'timeline'} class:on={tab === 'timeline'} onclick={() => (tab = 'timeline')}>Timeline</button>
		<button role="tab" aria-selected={tab === 'raci'} class:on={tab === 'raci'} onclick={() => (tab = 'raci')}>RACI</button>
		<button role="tab" aria-selected={tab === 'activity'} class:on={tab === 'activity'} onclick={() => (tab = 'activity')}>Activity <span>{acts.length}</span></button>
	</div>

	{#if tab === 'projects' || tab === 'timeline' || tab === 'raci'}
		<div class="filters">
			<input type="search" class="field" placeholder="Search projects, owners, next steps, RACI names" bind:value={q} aria-label="Search" />
			{#if workstreams.length}
				<select class="field" bind:value={ws} aria-label="Workstream"><option value="">All workstreams</option>{#each workstreams as w (w)}<option>{w}</option>{/each}</select>
			{/if}
			<select class="field" bind:value={status} aria-label="Status">
				<option value="">Any status</option>
				<optgroup label="Status">{#each v.statuses as s (s)}<option value={s}>{s}</option>{/each}</optgroup>
				<optgroup label="Views"><option value="@open">All open items</option><option value="@active">Active work</option><option value="@due30">Due in 30 days</option><option value="@overdue">Past target</option><option value="@noa">No accountable</option></optgroup>
			</select>
			<select class="field" bind:value={health} aria-label="Health"><option value="">All health</option><option>Green</option><option>Amber</option><option>Red</option></select>
			<select class="field" bind:value={sort} aria-label="Sort"><option value="group">Group by program</option><option value="target">Sort: Target date</option><option value="name">Sort: Name</option><option value="progress">Sort: Progress</option><option value="status">Sort: Status</option><option value="updated">Recently updated</option></select>
			{#if tab === 'timeline'}<label class="chk"><input type="checkbox" bind:checked={showMs} /> Charter milestones</label>{/if}
			<span class="sub">Showing {rows.length} of {scoped.length}</span>
			{#if filtered}<button type="button" class="clear" onclick={clearFilters}>Clear filters</button>{/if}
		</div>
	{/if}

	{#if tab === 'programs'}
		<div class="pgrid">
			{#each programs as p (p.id)}
				{@const c = pcard(p)}
				<article class="card pcard">
					<div class="phead">
						<div>
							<h2 class="ptitle">{p.name}</h2>
							<div class="sub0">{p.pm ? `${p.pm} manages` : 'No program manager yet'}{p.sponsor ? `, ${p.sponsor} sponsors` : ''}</div>
						</div>
						<span class="chip" style="background:{hl(p.health)[0]};color:{hl(p.health)[1]}">{p.health || 'Not rated'}</span>
					</div>
					<dl class="pfacts">
						<dt>Period</dt><dd>{c.period}</dd>
						<dt>Budget</dt><dd>{c.budget}</dd>
						<dt>Next milestone</dt><dd>{c.next}</dd>
					</dl>
					<div class="stbar">{#each segs(c.mine) as g (g.s)}<span style="flex:{g.n};background:{st(g.s)[2]}" title="{g.s}: {g.n}"></span>{/each}</div>
					<div class="pprog"><b>{p.kpis.completed} of {p.kpis.projects} done</b><span class="ptrack"><i style="width:{p.kpis.projects ? Math.round((p.kpis.completed / p.kpis.projects) * 100) : 0}%"></i></span><span>Charter {c.done}/{p.checks.length}</span></div>
					<div class="pmsg" class:none={!p.statusSummary}>{p.statusSummary || p.itscMessage || 'No status summary yet'}</div>
					<div class="pbtns">
						<button type="button" class="pbtn dark" onclick={() => pick(p.id)}>Open charter</button>
						<button type="button" class="pbtn" onclick={() => { pick(p.id); tab = 'projects'; }}>Projects ({p.kpis.projects})</button>
						{#if isAdmin}<button type="button" class="pbtn" onclick={() => openCharter(p)}>Edit charter</button>{/if}
					</div>
				</article>
			{/each}
		</div>
	{:else if tab === 'charter' && prog}
		<section class="card">
			{#if isAdmin}<button type="button" class="pbtn edit-r" onclick={() => openCharter(prog)}>Edit charter</button>{/if}
			<div class="eyebrow">Program charter</div>
			<h2 class="big">{prog.title || prog.name}</h2>
			{#if prog.title && prog.title !== prog.name}<div class="sub">Program: {prog.name}</div>{/if}
			<div class="meta">
				<div><span class="l">Program manager</span>{prog.pm || '—'}</div>
				<div><span class="l">Sponsor</span>{prog.sponsor || '—'}</div>
				<div><span class="l">Start</span>{dt(prog.start)}</div>
				<div><span class="l">End</span>{dt(prog.end)}</div>
				<div><span class="l">Health</span>{prog.health || 'Not rated'}</div>
				<div><span class="l">Projects</span>{prog.kpis.completed} of {prog.kpis.projects} done</div>
			</div>
			<div class="stbar">{#each segs(scoped) as g (g.s)}<span style="flex:{g.n};background:{st(g.s)[2]}" title="{g.s}: {g.n}"></span>{/each}</div>
			<div class="checks" aria-label="Charter completeness">
				<b>Charter completeness {prog.completeness}%</b>
				{#each prog.checks as c (c.label)}<span class:y={c.done}>{c.done ? '✓' : '○'} {c.label}</span>{/each}
			</div>
		</section>
		<section class="card">
			<h3>Status summary</h3>
			<p class:none={!prog.statusSummary}>{prog.statusSummary || 'No status summary yet'}</p>
			{#if prog.itscMessage}<p class="msg">ITSC key message: {prog.itscMessage}</p>{/if}
		</section>
		<div class="grid">
			{#each [['Problem statement', prog.problem], ['Goal and deliverables', prog.goal], ['Customer benefits', prog.benefits], ['Risks and issues', prog.risks], ['Assumptions and dependencies', prog.assumptions]] as [h, body] (h)}
				<section class="card"><h3>{h}</h3><p class="pre" class:none={!body}>{body || 'Not filled in'}</p></section>
			{/each}
			<section class="card"><h3>Scope</h3><p class="pre"><b>In:</b> {prog.scopeIn || '—'}</p><p class="pre"><b>Out:</b> {prog.scopeOut || '—'}</p></section>
		</div>
		<section class="card flush">
			<h3 class="pad">Financials (estimated budget)</h3>
			<p class="muted padx">{[prog.budgetNote && `Budget basis: ${prog.budgetNote}`, prog.currency].filter(Boolean).join(' · ')}</p>
			<div class="scroll"><table style="min-width:640px">
				<thead><tr><th class="first">Cost item</th><th class="r">Prudent</th><th class="r">Expansionary</th><th class="r">× Prudent</th><th class="r last">Actual / committed</th></tr></thead>
				<tbody>
					{#each prog.budget as r, i (i)}<tr><td class="first">{r.item || '—'}</td><td class="r">{money(num(r.prudent))}</td><td class="r">{money(num(r.expansionary))}</td><td class="r">{ratio(r.prudent, r.expansionary)}</td><td class="r last">{money(num(r.actual))}</td></tr>
					{:else}<tr><td colspan="5" class="none c">No budget lines.</td></tr>{/each}
				</tbody>
				{#if prog.budget.length}<tfoot><tr><td class="first">Total</td><td class="r">{money(prog.budget_totals.prudent)}</td><td class="r">{money(prog.budget_totals.expansionary)}</td><td class="r">{ratio(prog.budget_totals.prudent, prog.budget_totals.expansionary)}</td><td class="r last">{money(prog.budget_totals.actual)}</td></tr></tfoot>{/if}
			</table></div>
		</section>
		<section class="card flush">
			<h3 class="pad">Milestones (key results) and schedule</h3>
			<div class="scroll"><table style="min-width:780px">
				<thead><tr><th class="first">#</th><th>Milestone</th><th>Start</th><th>End (target)</th><th>End (actual)</th><th>Status</th><th class="r last">Linked projects</th></tr></thead>
				<tbody>
					{#each prog.milestones as m, i (i)}
						{@const s = m.actual ? 'Completed' : m.status || 'Planned'}
						<tr><td class="first muted">{i + 1}</td><td class="b">{m.name || '—'}</td><td>{dt(m.start)}</td><td>{dt(m.target)}</td><td>{dt(m.actual)}</td><td><span class="chip" style="background:{st(s)[0]};color:{st(s)[1]}">{s}</span></td><td class="r last">{scoped.filter((p: any) => m.id && p.milestone_id === m.id).length}</td></tr>
					{:else}<tr><td colspan="7" class="none c">No milestones.</td></tr>{/each}
				</tbody>
			</table></div>
		</section>
		<section class="card flush">
			<h3 class="pad">Measurables</h3>
			<div class="scroll"><table style="min-width:780px">
				<thead><tr><th class="first">#</th><th>Metric (SMART)</th><th>Base target</th><th>Stretch target</th><th>Actual achievement</th><th class="last">Status</th></tr></thead>
				<tbody>
					{#each prog.measurables as m, i (i)}<tr><td class="first muted">{i + 1}</td><td class="b">{m.metric || '—'}</td><td>{m.base || '—'}</td><td>{m.stretch || '—'}</td><td>{m.actual || '—'}</td><td class="last"><span class="chip" style="background:#EEF2EF;color:#3E4640">{m.status || 'Not assessed'}</span></td></tr>
					{:else}<tr><td colspan="6" class="none c">No measurables.</td></tr>{/each}
				</tbody>
			</table></div>
		</section>
		<div class="grid two">
			{#each [['Project team', prog.team], ['Steering committee', prog.steering]] as [h, list] (h)}
				<section class="card flush">
					<h3 class="pad">{h}</h3>
					<table>
						<thead><tr><th class="first">Name</th><th class="last">Role</th></tr></thead>
						<tbody>{#each list as r, i (i)}<tr><td class="first">{r.name || '—'}</td><td class="last">{r.role || ''}</td></tr>{:else}<tr><td colspan="2" class="none c">None listed.</td></tr>{/each}</tbody>
					</table>
				</section>
			{/each}
		</div>
		<section class="card flush">
			<h3 class="pad">Projects in this program</h3>
			<div class="scroll"><table style="min-width:720px">
				<thead><tr><th class="first">ID</th><th>Project</th><th>Workstream</th><th>Status</th><th>Target</th><th class="last">Charter milestone</th></tr></thead>
				<tbody>
					{#each scoped as p (p.id)}<tr><td class="first mono">{p.id}</td><td class="b">{p.name}</td><td>{p.workstream || '—'}</td><td><span class="chip" style="background:{st(p.status)[0]};color:{st(p.status)[1]}">{p.status}</span></td><td>{dt(p.target)}</td><td class="last">{p.milestone || '—'}</td></tr>
					{:else}<tr><td colspan="6" class="none c">No projects yet.</td></tr>{/each}
				</tbody>
			</table></div>
		</section>
	{:else if tab === 'projects'}
		<section class="card flush">
			<div class="scroll">
				<table style="min-width:1080px">
					<thead><tr><th class="first">ID</th><th>Project</th><th>Owner</th><th>Status</th><th>Health</th><th>Progress</th><th>Start</th><th>Target</th><th class="last">RACI</th></tr></thead>
					<tbody>
						{#each listed as r (r.p ? r.p.id : `g-${r.g}`)}
							{#if r.p}
								{@const p = r.p}
								<tr>
									<td class="first mono">{p.id}{#if isAdmin}<div><button type="button" class="edit" onclick={() => openProject(p)}>Edit</button></div>{/if}</td>
									<td>
										<b>{p.name}</b>
										{#if p.description}<div class="muted desc">{p.description}</div>{/if}
										{#if p.next_step}<div class="muted desc"><b>Next:</b> {p.next_step}</div>{/if}
										{#if p.decision}<div class="muted desc"><b>Decision:</b> {p.decision}</div>{/if}
										{#if sel === '' && sort !== 'group'}<div class="muted">{progName(p.program)}{p.workstream ? ` · ${p.workstream}` : ''}</div>{:else if p.workstream}<div class="muted">{p.workstream}</div>{/if}
									</td>
									<td class="nw">{p.owner || '—'}</td>
									<td><span class="chip" style="background:{st(p.status)[0]};color:{st(p.status)[1]}">{p.status}</span></td>
									<td>{#if p.health}<span class="chip" style="background:{hl(p.health)[0]};color:{hl(p.health)[1]}">{p.health}</span>{:else}<span class="muted">Not rated</span>{/if}</td>
									<td><div class="prog"><span class="ptrack"><i style="width:{p.pct}%"></i></span><b class="tabular">{p.pct}%</b></div></td>
									<td class="nw">{dt(p.start)}</td>
									<td class="nw">{dt(p.target)}{#if due(p)}<div class="due" class:over={p.days_to_target < 0}>{due(p)}</div>{/if}{#if p.timing_note}<div class="muted">{p.timing_note}</div>{/if}</td>
									<td class="last raci-s">{raciShort(p)}</td>
								</tr>
							{:else}
								<tr><td colspan="9" class="grp">{r.g} ({r.n})</td></tr>
							{/if}
						{:else}
							<tr><td colspan="9" class="none c">No projects match.</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{:else if tab === 'timeline'}
		<p class="tlnote">Every project on one calendar. The red dashed line is today, {day(v.today)}.</p>
		<section class="card tlc">
			<div class="legend">
				<span><i style="width:18px;height:8px;border-radius:4px;background:#111"></i>In progress</span>
				<span><i style="width:18px;height:8px;border-radius:4px;background:#3A9A68"></i>Completed</span>
				<span><i style="width:18px;height:8px;border-radius:4px;background:#B9C7BD"></i>Planned</span>
				<span><i style="width:18px;height:8px;border-radius:4px;background:#D27A45"></i>On hold</span>
				<span><i style="width:10px;height:10px;border-radius:2px;border:1.5px solid #111;background:#F2C14E;transform:rotate(45deg)"></i>Charter milestone</span>
				<span><i style="width:0;height:12px;border-left:2px dashed #B02A2A"></i>Today</span>
			</div>
			<div class="scroll">
				<div style="min-width:960px">
					<div class="trow"><div class="tlab"></div><div class="track axis">{#each tl.months as m (m.left)}<span class="mlab" style="left:{m.left}%;width:{m.width}%">{m.label}</span>{/each}</div></div>
					{#each tl.rows as r, i (i)}
						{#if r.t === 'head'}
							<div class="trow head"><div class="tlab"><b>{r.label}</b></div></div>
						{:else}
							<div class="trow line">
								<div class="tlab"><div class="tname" class:it={r.t === 'ms'}>{r.label}</div><div class="tsub">{r.sub}</div></div>
								<div class="track">
									{#each tl.months as m (m.left)}<span class="grid-l" style="left:{m.left}%"></span>{/each}
									<span class="today" style="left:{tl.today}%"></span>
									{#if r.t === 'proj'}
										{#if r.bar}<span class="pbar" style="left:{r.left}%;width:{r.width}%;background:{r.color};color:{r.color === '#B9C7BD' ? '#111' : '#fff'}">{r.pct}%</span>{:else if r.pin}<span class="pbar pt" style="left:calc({r.pinAt}% - 5px);background:{r.color}"></span>{/if}
									{:else if r.actual != null}<span class="act" style="left:{r.actual}%"></span>{/if}
									{#if r.dia != null}<span class="dia" style="left:calc({r.dia}% - 7px)" title="Milestone: {r.diaName}"></span>{/if}
								</div>
							</div>
						{/if}
					{:else}
						<div class="none c pad">Nothing with dates matches.</div>
					{/each}
				</div>
			</div>
		</section>
		{#if tl.undated.length}
			<section class="card">
				<h3>No dates yet <span class="muted2">({tl.undated.length})</span></h3>
				<p class="muted">These projects have neither a start nor a target date, so they cannot be drawn.</p>
				<div class="tags">{#each tl.undated as u (u.id)}<span><span class="mono">{u.id}</span> {u.name}</span>{/each}</div>
			</section>
		{/if}
	{:else if tab === 'raci'}
		<div class="subtabs">
			<div class="seg" role="group" aria-label="RACI view">
				<button type="button" class:on={raciMode === 'project'} aria-pressed={raciMode === 'project'} onclick={() => (raciMode = 'project')}>By project</button>
				<button type="button" class:on={raciMode === 'person'} aria-pressed={raciMode === 'person'} onclick={() => (raciMode = 'person')}>By person</button>
			</div>
			<span class="sub"><b>R</b> Responsible · <b>A</b> Accountable · <b>C</b> Consulted · <b>I</b> Informed</span>
		</div>
		{#if raciMode === 'project'}
			<section class="card flush">
				<div class="scroll"><table style="min-width:960px">
					<thead><tr><th class="first">ID</th><th>Project</th><th>Responsible</th><th>Accountable</th><th>Consulted</th><th>Informed</th><th class="last">Check</th></tr></thead>
					<tbody>
						{#each rows as p (p.id)}
							{@const c = check(p)}
							<tr>
								<td class="first mono">{p.id}</td>
								<td><b>{p.name}</b><div class="muted">{progName(p.program)}{p.workstream ? ` · ${p.workstream}` : ''}</div></td>
								<td>{p.raci.R || '—'}</td><td>{p.raci.A || '—'}</td><td>{p.raci.C || '—'}</td><td>{p.raci.I || '—'}</td>
								<td class="last"><span class="chip" style="background:{c === 'OK' ? '#E2F2E7' : c === 'Closed' ? '#EEF2EF' : '#FBE6A9'};color:{c === 'OK' ? '#1F5C3A' : c === 'Closed' ? '#3E4640' : '#4A4128'}">{c}</span></td>
							</tr>
						{:else}<tr><td colspan="7" class="none c">Nothing matches these filters.</td></tr>{/each}
					</tbody>
				</table></div>
			</section>
		{:else}
			<section class="card flush">
				<div class="scroll"><table style="min-width:760px">
					<thead><tr><th class="first">Person</th><th class="ctr">R</th><th class="ctr">A</th><th class="ctr">C</th><th class="ctr">I</th><th class="last">Projects</th></tr></thead>
					<tbody>
						{#each people as p (p.name)}
							<tr><td class="first b">{p.name}</td><td class="ctr">{p.R}</td><td class="ctr b">{p.A}</td><td class="ctr">{p.C}</td><td class="ctr">{p.I}</td><td class="last sub2">{p.ids.slice(0, 3).join(', ')}{p.ids.length > 3 ? ` and ${p.ids.length - 3} more` : ''}</td></tr>
						{:else}<tr><td colspan="6" class="none c">No one is assigned yet.</td></tr>{/each}
					</tbody>
				</table></div>
			</section>
		{/if}
		{#if raciMode === 'project'}
			<section class="load" aria-label="Load by person">
				{#each people as p (p.name)}
					<div class="pc">
						<div class="pn"><span class="av lg">{ini(p.name)}</span><b>{p.name}</b></div>
						<div class="rc"><span class="r">R {p.R}</span><span class="a">A {p.A}</span><span class="c">C {p.C}</span><span class="i">I {p.I}</span></div>
					</div>
				{/each}
			</section>
		{/if}
	{:else if tab === 'activity'}
		<section class="card">
			<div class="ahead"><h2>Activity <span class="muted2">({acts.length})</span></h2><span class="muted">Every add, status change, date move, RACI edit and charter edit, with who made it.</span></div>
			<ul class="alist">
				{#each acts as a (a.id)}
					<li>
						<time class="atime">{dayTime(a.at)}</time>
						<div class="awhat">
							<div><span class="alink">{a.kind === 'program' ? 'Charter · ' : `${a.ref_id} `}{a.ref_name}</span> <span class="chip" style="background:{a.type === 'created' ? '#E2F2E7' : a.type === 'deleted' ? '#F8CDD0' : '#CFE3FB'};color:{a.type === 'created' ? '#1F5C3A' : a.type === 'deleted' ? '#4E2F32' : '#1F3F66'}">{a.type === 'created' ? 'added' : a.type}</span></div>
							{#each a.changes.slice(0, 6) as c, i (i)}<div class="ch">{c.field}: {c.from === '' || c.from == null ? '(empty)' : c.from} → {c.to === '' || c.to == null ? '(empty)' : c.to}</div>{/each}
							{#if a.changes.length > 6}<div class="ch">+{a.changes.length - 6} more fields</div>{/if}
						</div>
						<span class="who"><span class="av">{ini(a.by)}</span>{a.by || 'Not recorded'}</span>
					</li>
				{:else}
					<li class="none c">No changes yet.</li>
				{/each}
			</ul>
		</section>
	{/if}
{/if}

{#if drawer?.kind === 'project'}
	<ProjectDrawer project={drawer.project} {programs} statuses={v.statuses} defaultProgram={sel || programs[0]?.id || ''} {by} onclose={() => (drawer = null)} ondone={done} />
{:else if drawer?.kind === 'charter'}
	<CharterDrawer program={drawer.program} {by} onclose={() => (drawer = null)} ondone={done} />
{/if}

<style>
	.who { display: inline-flex; align-items: center; gap: 8px; background: #fff; border-radius: 999px; min-height: 44px; padding: 0 6px 0 18px; font-size: 13px; color: #5b635d; font-weight: 600; }
	.who input { border: 0; background: #f4f7f5; border-radius: 999px; min-height: 32px; padding: 0 14px; width: 120px; font: inherit; font-size: 13px; color: #111; }
	.notice { margin: 0; background: #e2f2e7; color: #1f5c3a; border-radius: 18px; padding: 10px 18px; font-size: 14px; font-weight: 600; }
	.notice button { margin-left: 8px; border: 0; background: none; font: 700 12px inherit; text-decoration: underline; cursor: pointer; color: inherit; min-height: 32px; }
	.addp { min-height: 40px; padding: 0 16px; border-radius: 999px; border: 1.5px dashed #b9c7bd !important; background: transparent !important; color: #3e4640 !important; font: 600 13px inherit; cursor: pointer; }
	.edit { margin-top: 4px; border: 0; background: #f1f5f2; border-radius: 999px; padding: 0 12px; min-height: 32px; font: 700 12px inherit; cursor: pointer; color: #111; }
	.edit-r { float: right; }
	.title-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 16px; }
	.eyebrow { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #5b635d; text-transform: uppercase; }
	.t { display: flex; align-items: center; gap: 14px; margin-top: 4px; }
	h1 { margin: 0; font-size: 46px; font-weight: 700; letter-spacing: -0.035em; line-height: 1; }
	.cnt { min-width: 44px; height: 44px; border-radius: 999px; border: 1.5px solid #b9c7bd; display: inline-flex; align-items: center; justify-content: center; font-weight: 600; }
	.sub { font-size: 13px; color: #3e4640; margin-top: 6px; }
	.acts { display: flex; flex-wrap: wrap; gap: 10px; }
	.pill { min-height: 44px; padding: 0 20px; border-radius: 999px; border: 0; font: 600 14px inherit; cursor: pointer; }
	.pill.dark { background: #111; color: #fff; } .pill.light { background: #fff; color: #111; }
	.chips, .tabs { display: flex; flex-wrap: wrap; gap: 8px; }
	.chips button, .tabs button { min-height: 40px; padding: 0 16px; border-radius: 999px; border: 0; background: #fff; color: #111; font: 600 14px inherit; cursor: pointer; display: inline-flex; align-items: center; gap: 6px; }
	.tabs button { padding: 0 18px; }
	.chips button.on, .tabs button.on { background: #111; color: #fff; }
	.chips span, .tabs span { opacity: 0.6; font-weight: 600; }
	.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; }
	.kpi { text-align: left; border: 0; border-radius: 24px; padding: 14px 16px; display: flex; flex-direction: column; gap: 2px; cursor: pointer; font: inherit; color: #111; }
	.kpi[aria-pressed='true'] { outline: 2px solid #111; }
	.kl { font-size: 12px; font-weight: 700; color: #3e4640; } .kv { font-size: 30px; font-weight: 700; line-height: 1.1; } .kn { font-size: 11px; color: #3e4640; }
	.filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
	.filters .field { min-height: 44px; } .filters input[type='search'] { flex: 1 1 260px; }
	.chk { display: inline-flex; align-items: center; gap: 8px; background: #fff; border-radius: 999px; min-height: 44px; padding: 0 16px; font-size: 14px; font-weight: 600; }
	.card { background: #fff; border-radius: 28px; padding: 22px 28px; }
	.card.flush { padding: 0; overflow: hidden; }
	.card.empty { max-width: 640px; } .card.empty p { color: #3e4640; }
	.pad { padding: 20px 28px 10px; margin: 0; } .padx { padding: 0 28px 10px; margin: 0; }
	h2, h3 { margin: 0 0 8px; font-size: 16px; font-weight: 700; } h2.big { font-size: 30px; letter-spacing: -0.02em; margin: 4px 0 0; } h2.ptitle { font-size: 20px; margin: 4px 0 2px; }
	.card.empty h2 { font-size: 18px; }
	.meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin: 16px 0; }
	.meta div { font-size: 15px; font-weight: 700; } .l { display: block; font-size: 12px; font-weight: 700; color: #5b635d; margin-bottom: 2px; }
	.stbar { display: flex; height: 12px; border-radius: 6px; overflow: hidden; background: #e3eae5; margin: 12px 0; } .stbar span { display: block; height: 100%; }
	.checks { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 13px; color: #5b635d; } .checks b { width: 100%; color: #111; } .checks .y { color: #1f5c3a; font-weight: 600; }
	p { margin: 0 0 6px; font-size: 14px; line-height: 1.6; } .pre { white-space: pre-wrap; color: #3e4640; } .none { color: #7a847d; } .msg { margin-top: 10px; font-weight: 600; }
	.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; } .grid.two { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
	.pgrid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }
	.pcard { display: flex; flex-direction: column; gap: 14px; min-width: 0; padding: 22px 24px; }
	.phead { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; }
	.sub0 { font-size: 12px; color: #5b635d; margin-top: 2px; }
	.pfacts { display: grid; grid-template-columns: auto 1fr; gap: 6px 14px; font-size: 13px; margin: 0; }
	.pfacts dt { color: #5b635d; } .pfacts dd { margin: 0; font-weight: 600; }
	.pcard .stbar { margin: 0; background: #eef2ef; }
	.pprog { display: flex; align-items: center; gap: 10px; font-size: 12px; color: #3e4640; }
	.ptrack { flex: 1; height: 6px; border-radius: 3px; background: #e3eae5; overflow: hidden; } .ptrack i { display: block; height: 100%; background: #111; }
	.pmsg { font-size: 13px; color: #3e4640; background: #f4f7f5; border-radius: 16px; padding: 10px 14px; line-height: 1.5; }
	.pbtns { display: flex; gap: 8px; margin-top: auto; flex-wrap: wrap; }
	.pbtn { min-height: 44px; padding: 0 18px; border-radius: 999px; border: 0; background: #f1f5f2; color: #111; font: 700 13px inherit; cursor: pointer; }
	.pbtn.dark { background: #111; color: #fff; }
	.kpi:disabled { cursor: default; }
	.scroll { overflow-x: auto; }
	table { width: 100%; border-collapse: collapse; font-size: 13px; }
	th { text-align: left; font-size: 12px; font-weight: 700; color: #5b635d; padding: 12px 14px; background: #f4f7f5; white-space: nowrap; }
	td { padding: 12px 14px; border-top: 1px solid #eef2ef; vertical-align: top; }
	th.first, td.first { padding-left: 28px; } th.last, td.last { padding-right: 28px; }
	th.r, td.r { text-align: right; } th.ctr, td.ctr { text-align: center; } td.c { text-align: center; padding: 28px; }
	tfoot td { font-weight: 800; background: #f4f7f5; } td.b, .b { font-weight: 700; } td.sub2 { color: #3e4640; }
	.mono { font-family: ui-monospace, Menlo, monospace; font-size: 12px; white-space: nowrap; } .muted { color: #5b635d; font-size: 12px; } .muted2 { color: #5b635d; font-weight: 500; font-size: 13px; }
	.nw { white-space: nowrap; }
	.chip { display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 12px; font-weight: 700; white-space: nowrap; }
	.due { font-size: 12px; font-weight: 600; color: #4a4128; } .due.over { color: #b02a2a; }
	/* timeline */
	.tlc { padding: 20px 24px 26px; }
	.legend { display: flex; flex-wrap: wrap; gap: 8px 22px; font-size: 12px; color: #3e4640; margin-bottom: 16px; align-items: center; }
	.legend span { display: inline-flex; align-items: center; gap: 8px; } .legend i { display: inline-block; }
	.trow { display: flex; align-items: center; } .trow.line { border-top: 1px solid #f1f5f2; padding: 5px 0; } .trow.head { padding: 14px 0 4px; font-size: 14px; }
	.tlab { flex: 0 0 280px; padding-right: 14px; min-width: 0; }
	.tname { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } .tname.it { font-style: italic; } .tsub { font-size: 11px; color: #5b635d; margin-top: 1px; }
	.track { flex: 1; position: relative; height: 30px; } .track.axis { height: 26px; border-bottom: 1px solid #eef2ef; }
	.mlab { position: absolute; top: 0; bottom: 4px; font-size: 12px; font-weight: 700; color: #5b635d; padding-left: 6px; display: flex; align-items: flex-end; }
	.grid-l { position: absolute; top: 0; bottom: 0; border-left: 1px solid #eef2ef; }
	.today { position: absolute; top: 0; bottom: 0; width: 0; border-left: 2px dashed #b02a2a; opacity: 0.7; }
	.pbar { position: absolute; top: 10px; height: 10px; min-width: 6px; border-radius: 5px; color: #fff; font-size: 0; box-sizing: border-box; }
	.pbar.pt { width: 10px; height: 10px; border-radius: 2px; transform: rotate(45deg); }
	.dia { position: absolute; top: 8px; width: 14px; height: 14px; transform: rotate(45deg); border-radius: 3px; border: 2px solid #111; background: #f2c14e; box-sizing: border-box; }
	.act { position: absolute; top: 5px; width: 3px; height: 20px; background: #2e8b57; }
	.tlnote { margin: 0; font-size: 13px; color: #3e4640; }
	.axis { background: #f4f7f5; border-radius: 0; }
	/* projects table */
	.grp { padding: 12px 28px 8px; font-size: 15px; font-weight: 700; border-top: 1px solid #eef2ef; }
	.desc { max-width: 44ch; margin-top: 2px; }
	.prog { display: flex; align-items: center; gap: 8px; min-width: 110px; font-size: 12px; } .prog b { width: 34px; text-align: right; }
	.raci-s { font-size: 12px; color: #3e4640; line-height: 1.5; }
	.clear { background: none; border: 0; font: 700 12px inherit; min-height: 44px; cursor: pointer; text-decoration: underline; color: #111; }
	/* raci load cards */
	.load { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
	.pc { background: #fff; border-radius: 22px; padding: 14px 18px; display: flex; flex-direction: column; gap: 8px; } .pn { display: flex; align-items: center; gap: 10px; font-size: 14px; }
	.rc { display: flex; gap: 6px; } .rc span { border-radius: 999px; padding: 3px 10px; font-size: 11px; font-weight: 700; background: #eef2ef; color: #3e4640; }
	.rc .r { background: #cfe3fb; color: #1f3f66; } .rc .a { background: #e2f2e7; color: #1f5c3a; } .rc .c { background: #fbe6a9; color: #4a4128; }
	.tags { display: flex; flex-wrap: wrap; gap: 8px; } .tags > span { background: #f1f5f2; border-radius: 999px; padding: 6px 12px; font-size: 12px; font-weight: 600; }
	/* raci and activity */
	.subtabs { display: flex; flex-wrap: wrap; gap: 12px 18px; align-items: center; }
	.seg { display: inline-flex; background: #fff; border-radius: 999px; padding: 4px; }
	.seg button { min-height: 38px; padding: 0 18px; border-radius: 999px; border: 0; background: transparent; font: 600 14px inherit; cursor: pointer; color: #111; } .seg button.on { background: #111; color: #fff; }
	.ahead { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 10px; margin-bottom: 8px; } .ahead h2 { font-size: 18px; margin: 0; }
	.alist { list-style: none; margin: 0; padding: 0; } .alist li { display: grid; grid-template-columns: 130px 1fr auto; gap: 6px 16px; padding: 14px 0; border-top: 1px solid #eef2ef; align-items: center; }
	.atime { font-size: 12px; color: #5b635d; } .awhat { min-width: 0; font-size: 14px; }
	.who { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #3e4640; }
	.av { width: 28px; height: 28px; border-radius: 999px; background: #111; color: #fff; font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; justify-content: center; } .av.lg { width: 34px; height: 34px; font-size: 12px; }
	@media (max-width: 767px) { .alist li { grid-template-columns: 1fr; } }
	.alink { font-weight: 700; text-decoration: underline; } .ch { font-size: 13px; color: #3e4640; margin-top: 4px; }
	@media (max-width: 767px) { h1 { font-size: 34px; } }
</style>
