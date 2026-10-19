<script lang="ts">
	// "All projects" table with health and source filters and search, as in Main.dc.html.
	import { page } from '$app/state';
	import { STATUS_DOT, day, fullDate } from '$lib/format';
	import type { ProjectRow } from '$lib/types';
	import HealthPill from './HealthPill.svelte';
	import SourceChip from './SourceChip.svelte';

	let {
		rows,
		title = 'All projects',
		query = $bindable(''),
		showSearch = false,
		autofocus = false
	}: { rows: ProjectRow[]; title?: string; query?: string; showSearch?: boolean; autofocus?: boolean } = $props();

	let healthF = $state(page.url.searchParams.get('health') ?? 'all');
	let sourceF = $state(page.url.searchParams.get('source') ?? 'all');
	const order: Record<string, number> = { off_track: 0, at_risk: 1, on_track: 2, done: 3 };

	const shown = $derived(
		rows
			.filter((r) => sourceF === 'all' || r.source === sourceF)
			.filter((r) => healthF === 'all' || r.health === healthF)
			.filter((r) => {
				const q = query.trim().toLowerCase();
				return !q || r.code.toLowerCase().includes(q) || r.name.toLowerCase().includes(q);
			})
			.sort((a, b) => (order[a.health] ?? 9) - (order[b.health] ?? 9) || a.code.localeCompare(b.code))
	);
	const healths = [
		{ id: 'all', label: 'All health' },
		{ id: 'off_track', label: 'Off track' },
		{ id: 'at_risk', label: 'At risk' },
		{ id: 'on_track', label: 'On track' }
	];
	const sources = [
		{ id: 'all', label: 'All sources' },
		{ id: 'jira', label: 'JIRA' },
		{ id: 'openproject', label: 'OpenProject' },
		{ id: 'multica', label: 'Multica' }
	];
	function due(r: ProjectRow): { text: string; overdue: boolean } {
		if (!r.next_milestone_due) return { text: r.status === 'Done' ? `Done · ${fullDate(r.end_date)}` : '—', overdue: false };
		const overdue = r.next_milestone_due < page.data.today;
		return { text: overdue ? `Overdue · ${fullDate(r.next_milestone_due)}` : fullDate(r.next_milestone_due), overdue };
	}
</script>

<section class="tbl-card">
	<div class="head">
		<div class="title">
			<h2>{title}</h2>
			<span class="count">{shown.length} of {rows.length} · sorted by health</span>
		</div>
		<div class="filters">
			{#if showSearch}
				<label class="search">
					<span class="sr-only">Search projects</span>
					<!-- svelte-ignore a11y_autofocus -->
					<input type="search" placeholder="Search code or name" bind:value={query} {autofocus} />
				</label>
			{/if}
			<div class="seg" role="group" aria-label="Filter by health">
				{#each healths as h (h.id)}
					<button type="button" aria-pressed={healthF === h.id} onclick={() => (healthF = h.id)}>{h.label}</button>
				{/each}
			</div>
			<div class="seg" role="group" aria-label="Filter by source">
				{#each sources as s (s.id)}
					<button type="button" aria-pressed={sourceF === s.id} onclick={() => (sourceF = s.id)}>{s.label}</button>
				{/each}
			</div>
		</div>
	</div>
	<div class="scroll">
		<table>
			<thead>
				<tr>
					<th scope="col">Project</th><th scope="col">Health</th><th scope="col">Team</th><th scope="col">Source</th>
					<th scope="col">Status</th><th scope="col">Progress</th><th scope="col">Next milestone</th>
					<th scope="col">Strategy</th><th scope="col">Updated</th>
				</tr>
			</thead>
			<tbody>
				{#each shown as r (r.code + r.source)}
					{@const d = due(r)}
					<tr>
						<td>
							<div class="proj">
								<a href={`/projects/${r.code}`}>{r.name}</a>
								<span>{r.code}</span>
							</div>
						</td>
						<td><HealthPill value={r.health} /></td>
						<td class="soft">{r.team}</td>
						<td><SourceChip id={r.source} stale={r.stale} /></td>
						<td><span class="status"><span class="sdot" style={STATUS_DOT[r.status] ?? ''}></span>{r.status}</span></td>
						<td>
							<div class="prog">
								<div class="track"><div class="bar" style="width:{r.percent_done ?? 0}%"></div></div>
								<span class="pct tabular">{r.percent_done ?? '—'}%</span>
							</div>
						</td>
						<td>
							<div class="ms">
								<span class="msn">{r.next_milestone ?? '—'}</span>
								<span class:overdue={d.overdue}>{d.text}</span>
							</div>
						</td>
						<td class="strategy">{r.strategy ?? '—'}</td>
						<td class="upd">{day(r.updated)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	{#if shown.length === 0}<p class="empty">No projects match this filter.</p>{/if}
</section>

<style>
	.tbl-card {
		background: #fff;
		border-radius: 32px;
		padding: 26px 14px 14px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.head {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
		padding: 0 14px;
	}
	.title {
		display: flex;
		align-items: center;
		gap: 12px;
	}
	h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 700;
	}
	.count {
		font-size: 13px;
		color: #5b635d;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	.search {
		display: flex;
		align-items: center;
		background: #f1f5f2;
		border-radius: 999px;
		padding: 0 18px;
		min-height: 48px;
		min-width: 220px;
	}
	.search input {
		border: 0;
		outline: none;
		background: transparent;
		font: 500 14px var(--font-sans);
		flex: 1;
	}
	.scroll {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 1080px;
	}
	th {
		font-size: 12px;
		font-weight: 600;
		color: #5b635d;
		text-align: left;
		padding: 10px 14px;
	}
	td {
		padding: 14px;
		font-size: 14px;
		border-top: 1px solid #eef2ef;
		vertical-align: middle;
	}
	tr:hover td {
		background: #f8fbf9;
	}
	.proj {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}
	.proj a {
		font-weight: 700;
		font-size: 15px;
		text-decoration: none;
	}
	.proj a:hover {
		text-decoration: underline;
	}
	.proj span {
		font-size: 12px;
		color: #5b635d;
		letter-spacing: 0.02em;
	}
	.soft {
		color: #3e4640;
	}
	.status {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		font-weight: 600;
		white-space: nowrap;
	}
	.sdot {
		width: 8px;
		height: 8px;
		border-radius: 99px;
	}
	.prog {
		display: flex;
		align-items: center;
		gap: 10px;
		min-width: 140px;
	}
	.track {
		flex: 1;
		height: 8px;
		background: #eef2ef;
		border-radius: 99px;
		overflow: hidden;
	}
	.bar {
		height: 8px;
		border-radius: 99px;
		background: #111;
	}
	.pct {
		font-size: 12px;
		font-weight: 700;
		background: #f1f5f2;
		border-radius: 99px;
		padding: 2px 8px;
		min-width: 32px;
		text-align: center;
	}
	.ms {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.ms span:last-child {
		font-size: 12px;
		color: #5b635d;
	}
	.msn {
		font-weight: 600;
	}
	.ms .overdue {
		color: #b4441a;
		font-weight: 700;
	}
	.strategy {
		font-size: 12px;
		color: #3e4640;
		max-width: 150px;
	}
	.upd {
		color: #5b635d;
		font-size: 13px;
		white-space: nowrap;
	}
	.empty {
		margin: 0;
		padding: 28px;
		text-align: center;
		color: #5b635d;
		font-size: 14px;
	}
</style>
