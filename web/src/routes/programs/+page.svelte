<script lang="ts">
	import { day } from '$lib/format';

	let { data } = $props();
	const v = $derived(data.v);
	const programs = $derived<any[]>(v.programs);

	let sel = $state(''); // program id, '' = all programs
	let tab = $state<'charter' | 'projects' | 'raci'>('projects');
	let q = $state('');
	let ws = $state('');
	let status = $state('');
	let sort = $state('group');

	const prog = $derived(programs.find((p) => p.id === sel) ?? null);
	const scoped = $derived<any[]>(sel ? v.projects.filter((p: any) => p.program === sel) : v.projects);
	const kp = $derived(prog ? prog.kpis : v.kpis);
	const workstreams = $derived([...new Set(scoped.map((p: any) => p.workstream).filter(Boolean))].sort() as string[]);
	const progName = (id: string) => programs.find((p) => p.id === id)?.name ?? id;

	const TILES = [
		{ k: '', label: 'Projects', val: 'projects', note: () => (prog ? prog.name : `${programs.length} programs`) },
		{ k: 'Completed', label: 'Completed', val: 'completed', cls: 'good', note: () => (kp.projects ? `${Math.round((kp.completed / kp.projects) * 100)}% done` : '') },
		{ k: '@active', label: 'Active', val: 'active', note: () => 'In progress, UAT, dev complete' },
		{ k: 'Pending Approval', label: 'Pending approval', val: 'pending_approval', cls: 'warn', note: () => 'Needs a decision' },
		{ k: 'Planned', label: 'Planned', val: 'planned', note: () => 'Not started' },
		{ k: '@due30', label: 'Due in 30 days', val: 'due_30', note: () => 'Open, target within 30 days' },
		{ k: '@overdue', label: 'Past target', val: 'past_target', cls: 'bad', note: () => 'Open, target date passed' },
		{ k: '@noa', label: 'No accountable', val: 'no_accountable', cls: 'warn', note: () => 'Open items without exactly one A' }
	];
	const ACTIVE = ['In Progress', 'In UAT', 'Dev Complete'];
	const names = (s: string) => (s || '').split(',').map((x) => x.trim()).filter(Boolean);
	const match = (p: any, f: string) =>
		!f ||
		(f === '@active' ? ACTIVE.includes(p.status)
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
				match(p, status) &&
				(!t || [p.id, p.name, p.owner, p.next_step, p.decision, p.workstream, p.raci.R, p.raci.A, p.raci.C, p.raci.I].join(' ').toLowerCase().includes(t))
		);
		const by: Record<string, (a: any, b: any) => number> = {
			group: () => 0,
			target: (a, b) => (a.target || '9999').localeCompare(b.target || '9999'),
			status: (a, b) => v.statuses.indexOf(a.status) - v.statuses.indexOf(b.status),
			updated: (a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')
		};
		return [...out].sort(by[sort]);
	});

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
		if (!id && tab === 'charter') tab = 'projects';
		if (id) tab = 'charter';
	}
	const money = (n: number | null | undefined) => (n == null ? '—' : n.toLocaleString('en-US', { maximumFractionDigits: 0 }));
	const dt = (s: string) => (s ? day(s) : '—');
	const due = (p: any) =>
		!p.open || p.days_to_target == null ? '' : p.days_to_target < 0 ? `${-p.days_to_target}d past` : p.days_to_target === 0 ? 'due today' : `in ${p.days_to_target}d`;

	// Excel opens a CSV with a byte-order mark and UTF-8 text correctly.
	function exportCsv() {
		const head = ['ID', 'Program', 'Project', 'Workstream', 'Owner', 'Status', 'Health', '% complete', 'Start', 'Target', 'Responsible', 'Accountable', 'Consulted', 'Informed', 'Next step', 'Decision needed', 'Remarks'];
		const cell = (x: unknown) => `"${String(x ?? '').replace(/"/g, '""')}"`;
		const lines = rows.map((p: any) =>
			[p.id, progName(p.program), p.name, p.workstream, p.owner, p.status, p.health, p.pct, p.start, p.target, p.raci.R, p.raci.A, p.raci.C, p.raci.I, p.next_step, p.decision, p.remarks].map(cell).join(',')
		);
		const blob = new Blob(['﻿' + [head.map(cell).join(','), ...lines].join('\r\n')], { type: 'text/csv;charset=utf-8' });
		const a = document.createElement('a');
		a.href = URL.createObjectURL(blob);
		a.download = `programs-${prog?.id ?? 'all'}.csv`;
		a.click();
		URL.revokeObjectURL(a.href);
	}
</script>

<svelte:head><title>Programs · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div class="t"><h1>Programs</h1><span class="cnt tabular">{programs.length}</span></div>
	<div class="acts">
		<span class="sub">Program office data, read-only{v.imported_at ? ` · imported ${day(v.imported_at)}` : ''}</span>
		{#if scoped.length}<button type="button" class="btn" onclick={exportCsv}>Download for Excel</button>{/if}
	</div>
</section>

{#if !programs.length}
	<section class="card empty">
		<h2>No program office data yet</h2>
		<p>An admin loads the program office file with <code>python -m app.adapter po-import &lt;file&gt;</code>. Programs, charters, budgets, RACI and next steps then show here. This page never edits them.</p>
	</section>
{:else}
	<nav class="chips" aria-label="Programs">
		<button type="button" class:on={!sel} onclick={() => pick('')}>All programs</button>
		{#each programs as p (p.id)}
			<button type="button" class:on={sel === p.id} onclick={() => pick(p.id)}>{p.name}<span>{p.kpis.projects}</span></button>
		{/each}
	</nav>

	<section class="kpis" aria-label="Summary">
		{#each TILES as t (t.label)}
			{@const n = kp[t.val]}
			<button type="button" class="kpi {n && t.cls ? t.cls : ''}" aria-pressed={t.k !== '' && status === t.k} onclick={() => tile(t.k)}>
				<span class="kl">{t.label}</span><span class="kv tabular">{n}</span><span class="kn">{t.note()}</span>
			</button>
		{/each}
	</section>

	<div class="tabs" role="tablist">
		{#if prog}<button role="tab" aria-selected={tab === 'charter'} class:on={tab === 'charter'} onclick={() => (tab = 'charter')}>Charter</button>{/if}
		<button role="tab" aria-selected={tab === 'projects'} class:on={tab === 'projects'} onclick={() => (tab = 'projects')}>Projects<span>{scoped.length}</span></button>
		<button role="tab" aria-selected={tab === 'raci'} class:on={tab === 'raci'} onclick={() => (tab = 'raci')}>RACI</button>
	</div>

	{#if tab !== 'charter'}
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
			<select class="field" bind:value={sort} aria-label="Sort"><option value="group">Group by program</option><option value="target">Sort by target date</option><option value="status">Sort by status</option><option value="updated">Recently updated</option></select>
			<span class="sub">{rows.length} of {scoped.length}</span>
		</div>
	{/if}

	{#if tab === 'projects'}
		<section class="card flush">
			<div class="scroll">
				<table>
					<thead><tr><th>ID</th><th>Project</th><th>Workstream</th><th>Owner</th><th>Status</th><th>% done</th><th>Target</th><th>Next step</th><th>Decision needed</th></tr></thead>
					<tbody>
						{#each rows as p (p.id)}
							<tr>
								<td class="mono">{p.id}</td>
								<td><b>{p.name}</b>{#if !sel}<div class="muted">{progName(p.program)}</div>{/if}</td>
								<td>{p.workstream || '—'}</td>
								<td>{p.owner || '—'}</td>
								<td><span class="st" data-s={p.status}>{p.status}</span></td>
								<td><span class="bar"><i style="width:{p.pct}%"></i></span> <span class="tabular">{p.pct}%</span></td>
								<td>{dt(p.target)}{#if due(p)}<div class="due" class:over={p.days_to_target < 0}>{due(p)}</div>{/if}{#if p.timing_note}<div class="muted">{p.timing_note}</div>{/if}</td>
								<td>{p.next_step || '—'}</td>
								<td>{p.decision || '—'}</td>
							</tr>
						{:else}
							<tr><td colspan="9" class="none">No projects match.</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{:else if tab === 'raci'}
		<section class="card flush">
			<div class="scroll">
				<table>
					<thead><tr><th>ID</th><th>Project</th><th title="Does the work">R · Responsible</th><th title="Owns the outcome (one person)">A · Accountable</th><th title="Gives input">C · Consulted</th><th title="Kept updated">I · Informed</th></tr></thead>
					<tbody>
						{#each rows as p (p.id)}
							<tr>
								<td class="mono">{p.id}</td>
								<td><b>{p.name}</b>{#if !sel}<div class="muted">{progName(p.program)}</div>{/if}</td>
								<td>{p.raci.R || '—'}</td>
								<td class:warn={p.open && names(p.raci.A).length !== 1}>{p.raci.A || '—'}</td>
								<td>{p.raci.C || '—'}</td>
								<td>{p.raci.I || '—'}</td>
							</tr>
						{:else}
							<tr><td colspan="6" class="none">No projects match.</td></tr>
						{/each}
					</tbody>
				</table>
			</div>
		</section>
	{:else if prog}
		<section class="card">
			<div class="eyebrow">Program charter</div>
			<h2 class="big">{prog.title || prog.name}</h2>
			<div class="meta">
				<div><span class="l">Program manager</span>{prog.pm || '—'}</div>
				<div><span class="l">Sponsor</span>{prog.sponsor || '—'}</div>
				<div><span class="l">Start</span>{dt(prog.start)}</div>
				<div><span class="l">End</span>{dt(prog.end)}</div>
				<div><span class="l">Health</span>{prog.health || 'Not rated'}</div>
				<div><span class="l">Projects</span>{prog.kpis.completed} of {prog.kpis.projects} done</div>
			</div>
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
			<h3 class="pad">Financials (estimated budget){prog.currency ? ` · ${prog.currency}` : ''}</h3>
			{#if prog.budgetNote}<p class="muted pad">{prog.budgetNote}</p>{/if}
			<div class="scroll"><table>
				<thead><tr><th>Cost item</th><th class="num">Prudent</th><th class="num">Expansionary</th><th class="num">Actual / committed</th></tr></thead>
				<tbody>
					{#each prog.budget as r, i (i)}<tr><td>{r.item || '—'}</td><td class="num">{money(+r.prudent || null)}</td><td class="num">{money(+r.expansionary || null)}</td><td class="num">{money(+r.actual || null)}</td></tr>
					{:else}<tr><td colspan="4" class="none">No budget lines.</td></tr>{/each}
				</tbody>
				{#if prog.budget.length}<tfoot><tr><td>Total</td><td class="num">{money(prog.budget_totals.prudent)}</td><td class="num">{money(prog.budget_totals.expansionary)}</td><td class="num">{money(prog.budget_totals.actual)}</td></tr></tfoot>{/if}
			</table></div>
		</section>

		<section class="card flush">
			<h3 class="pad">Milestones and schedule</h3>
			<div class="scroll"><table>
				<thead><tr><th>#</th><th>Milestone</th><th>Start</th><th>End (target)</th><th>End (actual)</th><th>Status</th><th class="num">Linked projects</th></tr></thead>
				<tbody>
					{#each prog.milestones as m, i (i)}<tr><td>{i + 1}</td><td>{m.name || '—'}</td><td>{dt(m.start)}</td><td>{dt(m.target)}</td><td>{dt(m.actual)}</td><td>{m.status || '—'}</td><td class="num">{scoped.filter((p: any) => m.id && p.milestone_id === m.id).length}</td></tr>
					{:else}<tr><td colspan="7" class="none">No milestones.</td></tr>{/each}
				</tbody>
			</table></div>
		</section>

		<section class="card flush">
			<h3 class="pad">Measurables</h3>
			<div class="scroll"><table>
				<thead><tr><th>#</th><th>Metric</th><th>Base target</th><th>Stretch target</th><th>Actual achievement</th><th>Status</th></tr></thead>
				<tbody>
					{#each prog.measurables as m, i (i)}<tr><td>{i + 1}</td><td>{m.metric || '—'}</td><td>{m.base || '—'}</td><td>{m.stretch || '—'}</td><td>{m.actual || '—'}</td><td>{m.status || 'Not assessed'}</td></tr>
					{:else}<tr><td colspan="6" class="none">No measurables.</td></tr>{/each}
				</tbody>
			</table></div>
		</section>

		<div class="grid two">
			{#each [['Project team', prog.team], ['Steering committee', prog.steering]] as [h, list] (h)}
				<section class="card flush">
					<h3 class="pad">{h}</h3>
					<div class="scroll"><table>
						<thead><tr><th>Name</th><th>Role</th></tr></thead>
						<tbody>{#each list as r, i (i)}<tr><td>{r.name || '—'}</td><td>{r.role || ''}</td></tr>{:else}<tr><td colspan="2" class="none">None listed.</td></tr>{/each}</tbody>
					</table></div>
				</section>
			{/each}
		</div>
	{/if}
{/if}

<style>
	.title-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 20px; }
	.t { display: flex; align-items: center; gap: 16px; }
	h1 { margin: 0; font-size: 48px; font-weight: 700; letter-spacing: -0.035em; line-height: 1; }
	.cnt { min-width: 44px; height: 44px; border-radius: 999px; border: 1.5px solid #b9c7bd; display: inline-flex; align-items: center; justify-content: center; font-weight: 600; }
	.acts { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
	.sub { font-size: 13px; color: #3e4640; }
	.btn { min-height: 44px; padding: 0 18px; border-radius: 999px; border: 0; background: #111; color: #fff; font: 600 14px inherit; cursor: pointer; }
	.chips, .tabs { display: flex; flex-wrap: wrap; gap: 8px; }
	.chips button, .tabs button { min-height: 40px; padding: 0 16px; border-radius: 999px; border: 0; background: #fff; color: #111; font: 600 14px inherit; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; }
	.chips button.on, .tabs button.on { background: #111; color: #fff; }
	.chips span, .tabs span { font-size: 12px; opacity: 0.7; }
	.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
	.kpi { text-align: left; border: 0; border-radius: 24px; background: #fff; padding: 14px 16px; display: flex; flex-direction: column; gap: 2px; cursor: pointer; font: inherit; }
	.kpi[aria-pressed='true'] { outline: 2px solid #111; }
	.kpi.good { background: #e2f2e7; } .kpi.warn { background: #fbe6a9; } .kpi.bad { background: #f8cdd0; }
	.kl { font-size: 12px; font-weight: 700; color: #3e4640; } .kv { font-size: 30px; font-weight: 700; line-height: 1.1; } .kn { font-size: 11px; color: #3e4640; }
	.filters { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
	.filters .field { min-height: 44px; }
	.filters input[type='search'] { flex: 1 1 260px; }
	.card { background: #fff; border-radius: 28px; padding: 22px 24px; }
	.card.flush { padding: 0; overflow: hidden; }
	.card.empty { max-width: 640px; } .card.empty p { color: #3e4640; }
	.pad { padding: 18px 24px 8px; margin: 0; } p.pad { padding-top: 0; }
	h2, h3 { margin: 0 0 8px; font-size: 18px; font-weight: 700; } h2.big { font-size: 28px; letter-spacing: -0.02em; }
	.eyebrow { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; color: #5b635d; }
	.meta { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin: 14px 0; }
	.meta div { font-weight: 600; } .l { display: block; font-size: 12px; font-weight: 700; color: #5b635d; }
	.checks { display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; color: #5b635d; } .checks b { width: 100%; color: #111; } .checks .y { color: #1f5c3a; font-weight: 600; }
	p { margin: 0 0 6px; } .pre { white-space: pre-wrap; } .none { color: #7a847d; } .msg { margin-top: 8px; font-weight: 600; }
	.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
	.grid.two { grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
	.scroll { overflow-x: auto; }
	table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 640px; }
	th { text-align: left; font-size: 12px; font-weight: 700; color: #5b635d; padding: 12px 14px; background: #f4f7f5; white-space: nowrap; }
	td { padding: 12px 14px; border-top: 1px solid #eef2ef; vertical-align: top; }
	th.num, td.num { text-align: right; } tfoot td { font-weight: 700; background: #f4f7f5; }
	td.warn { background: #fbe6a9; } td.none { text-align: center; padding: 28px; }
	.mono { font-family: ui-monospace, monospace; font-size: 12px; white-space: nowrap; } .muted { color: #5b635d; font-size: 12px; }
	.st { display: inline-block; border-radius: 999px; padding: 4px 10px; font-size: 12px; font-weight: 700; background: #f1f5f2; white-space: nowrap; }
	.st[data-s='Completed'] { background: #e2f2e7; } .st[data-s='In Progress'], .st[data-s='In UAT'], .st[data-s='Dev Complete'] { background: #cfe3fb; }
	.st[data-s='Pending Approval'] { background: #fbe6a9; } .st[data-s='On Hold'], .st[data-s='Cancelled'] { background: #f8cdd0; }
	.bar { display: inline-block; width: 56px; height: 6px; border-radius: 3px; background: #e3eae5; vertical-align: middle; overflow: hidden; } .bar i { display: block; height: 100%; background: #111; }
	.due { font-size: 12px; font-weight: 600; color: #4a4128; } .due.over { color: #c23b3b; }
	@media (max-width: 767px) { h1 { font-size: 34px; } }
</style>
