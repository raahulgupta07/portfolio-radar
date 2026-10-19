<script lang="ts">
	import Icon from '$lib/components/Icon.svelte';
	import ProjectTable from '$lib/components/ProjectTable.svelte';
	import RadarFace from '$lib/components/RadarFace.svelte';
	import { HEALTH, day, dayTime, monthDay, plural, source } from '$lib/format';

	let { data } = $props();
	const o = $derived(data.overview);
	let query = $state('');

	const sevDot: Record<string, string> = { high: '#F27E7E', medium: '#F2C14E', low: '#FFFFFF' };
	const trendMax = $derived(Math.max(1, ...o.trend.map((t) => t.avg_percent_done)));
	const trendChange = $derived(
		o.trend.length > 1 ? o.trend[o.trend.length - 1].avg_percent_done - o.trend[0].avg_percent_done : 0
	);
	const msTone = (h: string, overdue: boolean) =>
		overdue || h === 'off_track' ? HEALTH.off_track : h === 'at_risk' ? HEALTH.at_risk : null;
</script>

<svelte:head><title>Portfolio overview · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div class="title">
		<h1>Portfolio Overview</h1>
		<span class="count-ring tabular">{o.total}</span>
	</div>
	<div class="actions">
		<label class="search">
			<Icon name="search" size={16} />
			<span class="sr-only">Search projects</span>
			<input type="search" placeholder="Search code or name" bind:value={query} />
		</label>
		<a class="icon-btn" href="/export/projects.csv" aria-label="Export projects to Excel (CSV)" title="Export to Excel (CSV)"><Icon name="download" /></a>
		<a class="icon-btn" href="/export/portfolio.pdf" target="_blank" rel="noopener" data-sveltekit-reload aria-label="One-pager PDF for the Steering Committee" title="One-pager PDF"><Icon name="file" /></a>
		<span class="viewonly"><Icon name="lock" size={15} />View only · refresh 02:00 daily</span>
	</div>
</section>

<section class="radar-strip" aria-label="Radar findings">
	<div class="who">
		<span class="face"><RadarFace mood={o.radar.count ? 'alert' : o.radar.checked_at ? 'happy' : 'resting'} size={44} /></span>
		<div>
			{#if o.radar.checked_at}
				<p class="big">{o.radar.count ? `Radar: ${plural(o.radar.count, 'item')} need${o.radar.count === 1 ? 's' : ''} attention` : 'Radar: nothing needs you today'}</p>
				<p class="small">Checked {plural(o.radar.projects_checked, 'project')} at {dayTime(o.radar.checked_at)}, after the daily sync</p>
			{:else}
				<p class="big">Radar has not checked yet</p>
				<p class="small">Radar checks every project after the daily sync.</p>
			{/if}
		</div>
	</div>
	{#if o.radar.items.length}
		<ul>
			{#each o.radar.items.slice(0, 5) as f (f.id)}
				<li><span class="d" style="background:{sevDot[f.severity] ?? '#FFFFFF'}"></span>{f.text}</li>
			{/each}
		</ul>
	{/if}
	<a class="open" href="/radar">Open Radar<Icon name="arrow" size={16} stroke={2} /></a>
</section>

<section class="tiles" aria-label="Portfolio health">
	{#each o.tiles as t (t.health)}
		{@const h = HEALTH[t.health]}
		<div class="tile" style="background:{t.health === 'on_track' ? '#FFFFFF' : h.bg}">
			<span class="lbl"><span class="d" style="background:{h.dot}"></span>{t.label}</span>
			<span class="num tabular">{t.count}</span>
			<span class="note" style="color:{t.health === 'on_track' ? '#5B635D' : h.ink}">{t.note}</span>
		</div>
	{/each}
</section>

<section class="sources" aria-label="Data sources">
	{#each o.sources as s (s.id)}
		{@const si = source(s.id)}
		<div class="src">
			<span class="badge" style="background:{si.bg}">{si.short}</span>
			<div class="txt">
				<span class="name">{s.name} · {s.team}</span>
				<span class="meta">
					{plural(s.projects, 'project')}{s.avg_percent_done != null ? ` · avg ${s.avg_percent_done}%` : ''} ·
					{s.stale ? `data from ${day(s.last_good_sync_at)}` : `synced ${dayTime(s.last_sync_at)}`}
				</span>
			</div>
			{#if s.stale}
				<span class="stale" title={s.error ?? 'Last sync failed'}>Stale</span>
			{:else}
				<span class="ok" title="Synced"><Icon name="check" size={16} stroke={2.2} /></span>
			{/if}
		</div>
	{/each}
</section>

<div class="grid3">
	<section class="card col">
		<div class="hd">
			<h2>Trend, last {o.trend.length} weeks</h2>
			<span class="chip tabular">{trendChange >= 0 ? '+' : ''}{trendChange} pts</span>
		</div>
		{#if o.trend.length}
			<div class="kpis">
				<div><span class="kpi tabular">{o.trend[o.trend.length - 1].avg_percent_done}<sup>%</sup></span><span class="cap">Avg progress now</span></div>
				<div><span class="kpi tabular">{o.trend[0].avg_percent_done}<sup>%</sup></span><span class="cap">{o.trend.length} weeks ago</span></div>
			</div>
			<div class="bars" role="img" aria-label={`Average progress by week: ${o.trend.map((t) => t.avg_percent_done).join(', ')} percent`}>
				{#each o.trend as t, i (t.date)}
					<div class="bcol">
						<span class="bv tabular">{t.avg_percent_done}%</span>
						<div class="b" style="height:{Math.round((t.avg_percent_done / trendMax) * 110)}px;max-width:34px;background:{i === o.trend.length - 1 ? '#111111' : '#C9DCCF'}"></div>
					</div>
				{/each}
			</div>
			<div class="blabels">{#each o.trend as t (t.date)}<span>{day(t.date)}</span>{/each}</div>
		{:else}
			<p class="muted">No history yet. Trends appear after the first week of daily syncs.</p>
		{/if}
	</section>

	<section class="card col">
		<div class="hd">
			<h2>Progress by project</h2>
			<a href="/roadmap" aria-label="Open roadmap" class="icon-btn outline"><Icon name="arrow-up-right" size={16} stroke={2} /></a>
		</div>
		<div class="bars tall" role="img" aria-label="Progress per project, coloured by source">
			{#each o.progress as c (c.code + c.source)}
				<a class="bcol" href={`/projects/${c.code}`} title={`${c.short}: ${c.percent_done ?? 0}%`}>
					<span class="bv tabular">{c.percent_done ?? 0}</span>
					<div class="b" style="height:{Math.max(4, Math.round((c.percent_done ?? 0) * 1.4))}px;max-width:20px;background:{source(c.source).bar}"></div>
				</a>
			{/each}
		</div>
		<div class="legend">
			<span><i style="background:#7FB2EC"></i>JIRA</span>
			<span><i style="background:#EAC45A"></i>OpenProject</span>
			<span><i style="background:#EE9AA0"></i>Multica</span>
			<span class="r">% done</span>
		</div>
	</section>

	<section class="card col tight">
		<div class="hd">
			<h2>Next milestones</h2>
			<a href="/roadmap" class="lnk">Roadmap</a>
		</div>
		<ul class="ms">
			{#each o.next_milestones as m (m.code + m.name)}
				{@const tone = msTone(m.health, m.overdue)}
				{@const md = monthDay(m.date)}
				<li style="background:{tone ? tone.bg : '#F4F7F5'}">
					<span class="cal"><span class="m">{md.month}</span><span class="d2 tabular">{md.day}</span></span>
					<span class="mtxt">
						<a href={`/projects/${m.code}`} class="mn">{m.name}</a>
						<span class="mm" style="color:{tone ? tone.ink : '#5B635D'}">{m.short} · {m.overdue || m.note.includes('waits') ? m.note : m.project}</span>
					</span>
				</li>
			{:else}
				<li class="none">No upcoming milestones.</li>
			{/each}
		</ul>
	</section>
</div>

<ProjectTable rows={o.projects} bind:query />

<style>
	.title-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 20px;
	}
	.title {
		display: flex;
		align-items: center;
		gap: 16px;
		flex-wrap: wrap;
	}
	h1 {
		margin: 0;
		font-size: 48px;
		font-weight: 700;
		letter-spacing: -0.035em;
		line-height: 1;
	}
	.count-ring {
		min-width: 44px;
		height: 44px;
		border-radius: 999px;
		border: 1.5px solid #b9c7bd;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 15px;
		font-weight: 600;
	}
	.actions {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.search {
		display: flex;
		align-items: center;
		gap: 8px;
		background: #fff;
		border-radius: 999px;
		padding: 0 18px;
		min-height: 44px;
		width: 260px;
		box-sizing: border-box;
		color: #5b635d;
	}
	.search input {
		border: 0;
		outline: none;
		font: 500 14px var(--font-sans);
		flex: 1;
		min-width: 0;
		background: transparent;
		color: #111;
	}
	.viewonly {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 0 18px;
		min-height: 44px;
		font-size: 13px;
		font-weight: 600;
	}
	.radar-strip {
		background: #161616;
		color: #fff;
		border-radius: 32px;
		padding: 22px 26px;
		display: flex;
		flex-wrap: wrap;
		gap: 20px;
		align-items: center;
	}
	.who {
		display: flex;
		align-items: center;
		gap: 14px;
		flex: 1 1 320px;
	}
	.face {
		width: 52px;
		height: 52px;
		border-radius: 999px;
		background: #fff;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.big {
		margin: 0 0 3px;
		font-size: 17px;
		font-weight: 700;
	}
	.small {
		margin: 0;
		font-size: 13px;
		color: #c9cfcb;
	}
	.radar-strip ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
		flex: 3 1 560px;
	}
	.radar-strip li {
		display: flex;
		align-items: center;
		gap: 8px;
		background: #2a2a2a;
		border-radius: 999px;
		padding: 9px 14px;
		font-size: 13px;
	}
	.d {
		width: 8px;
		height: 8px;
		border-radius: 99px;
		flex-shrink: 0;
	}
	.open {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		background: #fff;
		color: #111;
		border-radius: 999px;
		padding: 0 20px;
		min-height: 44px;
		font-weight: 700;
		font-size: 14px;
		text-decoration: none;
	}
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 16px;
	}
	.tile {
		border-radius: 30px;
		padding: 22px 24px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.lbl {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		font-weight: 700;
	}
	.lbl .d {
		width: 10px;
		height: 10px;
	}
	.num {
		font-size: 40px;
		font-weight: 700;
		letter-spacing: -0.03em;
		line-height: 1;
	}
	.note {
		font-size: 12px;
	}
	.sources {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
		gap: 16px;
	}
	.src {
		background: #fff;
		border-radius: 30px;
		padding: 20px 24px;
		display: flex;
		align-items: center;
		gap: 16px;
	}
	.badge {
		width: 48px;
		height: 48px;
		border-radius: 16px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 800;
		flex-shrink: 0;
	}
	.txt {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.name {
		font-size: 16px;
		font-weight: 700;
	}
	.meta {
		font-size: 12px;
		color: #5b635d;
	}
	.ok {
		width: 36px;
		height: 36px;
		border-radius: 999px;
		background: #f1f5f2;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.stale {
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 7px 12px;
		font-size: 12px;
		font-weight: 700;
	}
	.grid3 {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(400px, 100%), 1fr));
		gap: 16px;
		align-items: stretch;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.tight {
		gap: 14px;
	}
	.hd {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 700;
	}
	.chip {
		font-size: 12px;
		font-weight: 700;
		background: #f1f5f2;
		border-radius: 99px;
		padding: 4px 10px;
	}
	.kpis {
		display: flex;
		gap: 32px;
		flex-wrap: wrap;
	}
	.kpis div {
		display: flex;
		flex-direction: column;
	}
	.kpi {
		font-size: 26px;
		font-weight: 600;
	}
	.kpi sup {
		font-size: 12px;
	}
	.cap {
		font-size: 12px;
		color: #5b635d;
	}
	.bars {
		display: flex;
		align-items: flex-end;
		gap: 12px;
		height: 150px;
		border-bottom: 1px solid #e3eae5;
	}
	.bars.tall {
		height: 190px;
		gap: 8px;
	}
	.bcol {
		flex: 1;
		height: 100%;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
		align-items: center;
		gap: 6px;
		text-decoration: none;
		color: inherit;
	}
	.bv {
		font-size: 11px;
		font-weight: 700;
	}
	.b {
		width: 100%;
		border-radius: 8px 8px 2px 2px;
	}
	.blabels {
		display: flex;
		gap: 12px;
	}
	.blabels span {
		flex: 1;
		text-align: center;
		font-size: 11px;
		color: #5b635d;
	}
	.legend {
		display: flex;
		gap: 16px;
		font-size: 12px;
		color: #3e4640;
		flex-wrap: wrap;
	}
	.legend span {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.legend i {
		width: 10px;
		height: 10px;
		border-radius: 3px;
	}
	.legend .r {
		margin-left: auto;
	}
	.outline {
		border: 1.5px solid #dde5df;
	}
	.lnk {
		font-size: 13px;
		font-weight: 700;
		text-decoration: none;
	}
	.lnk:hover {
		text-decoration: underline;
	}
	.ms {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.ms li {
		display: flex;
		align-items: center;
		gap: 12px;
		border-radius: 22px;
		padding: 10px 12px;
	}
	.cal {
		width: 46px;
		height: 46px;
		border-radius: 999px;
		background: #fff;
		display: inline-flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		line-height: 1.05;
		flex-shrink: 0;
	}
	.cal .m {
		font-size: 10px;
		font-weight: 700;
	}
	.cal .d2 {
		font-size: 15px;
		font-weight: 800;
	}
	.mtxt {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}
	.mn {
		font-size: 14px;
		font-weight: 700;
		text-decoration: none;
	}
	.mm {
		font-size: 12px;
	}
	.none,
	.muted {
		color: #5b635d;
		font-size: 14px;
	}
	@media (max-width: 767px) {
		h1 {
			font-size: 34px;
		}
		.tiles {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			gap: 10px;
		}
		.tile {
			padding: 16px 18px;
			border-radius: 24px;
		}
		.num {
			font-size: 32px;
		}
		.search {
			width: 100%;
		}
		.actions {
			width: 100%;
		}
	}
	@media print {
		.actions,
		.open {
			display: none;
		}
	}
</style>
