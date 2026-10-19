<script lang="ts">
	import { day, health, source } from '$lib/format';

	let { data } = $props();
	const r = $derived(data.road);
	const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

	// Timeline window: first of the earliest start month to the end of the latest end month.
	const win = $derived.by(() => {
		const s = new Date((r.window.start ?? r.today) + 'T00:00:00Z');
		const e = new Date((r.window.end ?? r.today) + 'T00:00:00Z');
		const start = Date.UTC(s.getUTCFullYear(), s.getUTCMonth(), 1);
		const end = Date.UTC(e.getUTCFullYear(), e.getUTCMonth() + 1, 1);
		return { start, end };
	});
	const pos = (iso: string | null) =>
		iso ? Math.max(0, Math.min(100, ((Date.parse(iso + 'T00:00:00Z') - win.start) / (win.end - win.start)) * 100)) : 0;
	const months = $derived.by(() => {
		const out = [];
		const d = new Date(win.start);
		while (d.getTime() < win.end) {
			const next = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
			out.push({
				label: `${MONTHS[d.getUTCMonth()]}${d.getUTCMonth() === 0 || out.length === 0 ? ' ' + d.getUTCFullYear() : ''}`,
				left: ((d.getTime() - win.start) / (win.end - win.start)) * 100,
				width: ((next - d.getTime()) / (win.end - win.start)) * 100
			});
			d.setTime(next);
		}
		return out;
	});
	const rangeLabel = $derived(
		months.length ? `${months[0].label.split(' ')[0]} ${new Date(win.start).getUTCFullYear()} – ${MONTHS[new Date(win.end - 1).getUTCMonth()]} ${new Date(win.end - 1).getUTCFullYear()}` : ''
	);
	const waitsFor = (code: string) => r.dependencies.filter((d: any) => d.to.code === code);
	const msStyle = (m: any) =>
		m.status === 'done' ? 'background:#111111' : m.overdue ? 'background:#C23B3B' : 'background:#FFFFFF;box-shadow:inset 0 0 0 2px #111111';
</script>

<svelte:head><title>Roadmap · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div class="t"><h1>Roadmap</h1><span class="range">{rangeLabel}</span></div>
	<div class="legend">
		<span><i class="bar" style="background:#CFE3FB"></i>JIRA</span>
		<span><i class="bar" style="background:#FBE6A9"></i>OpenProject</span>
		<span><i class="bar" style="background:#F8CDD0"></i>Multica</span>
		<span><i class="dia" style="background:#111111"></i>Done</span>
		<span><i class="dia" style="background:#FFFFFF;box-shadow:inset 0 0 0 2px #111111"></i>Planned</span>
		<span><i class="dia" style="background:#C23B3B"></i>Overdue</span>
		<span><i class="today-key"></i>Today, {day(r.today)}</span>
	</div>
</section>

<section class="timeline" aria-label="Timeline">
	<div class="inner">
		<div class="row head">
			<span class="pl">Project</span>
			<div class="track months">
				{#each months as mo (mo.left)}<span style="left:{mo.left}%;width:{mo.width}%">{mo.label}</span>{/each}
			</div>
		</div>
		{#each r.projects as p (p.code + p.source)}
			{@const h = health(p.health)}
			{@const deps = waitsFor(p.code)}
			<div class="row">
				<div class="pl proj">
					<span class="hd" style="background:{h.dot}" title={h.label}></span>
					<div class="pn">
						<a href={`/projects/${p.code}`}>{p.name}</a>
						<span>{p.short} · {h.label}{p.stale ? ' · stale' : ''}</span>
					</div>
				</div>
				<div class="track">
					<span class="today" style="left:{pos(r.today)}%"></span>
					{#if p.start_date && p.end_date}
						<span class="span" style="left:{pos(p.start_date)}%;width:{Math.max(0.5, pos(p.end_date) - pos(p.start_date))}%;background:{source(p.source).bg}" title={`${day(p.start_date)} – ${day(p.end_date)}`}></span>
					{/if}
					{#each p.milestones.filter((m: any) => m.due_date) as m (m.name)}
						<span class="ms" style="left:{pos(m.due_date)}%;{msStyle(m)}" title={`${m.name} · ${day(m.due_date)}${m.overdue ? ' · overdue' : ''}`}></span>
					{/each}
					{#if deps.length}
						<span class="dep" style="left:{Math.min(80, pos(p.start_date) + 1)}%">waits for {deps.map((d: any) => d.from.short).join(', ')}</span>
					{/if}
				</div>
			</div>
		{/each}
	</div>
</section>

<section class="deps" aria-labelledby="dep-h">
	<div class="dh"><h2 id="dep-h">Dependencies between projects</h2><span class="n">{r.dependencies.length}</span></div>
	<div class="dgrid">
		{#each r.dependencies as d, i (i)}
			<div class="dcard" style="background:{d.blocked ? '#F8CDD0' : '#E2F2E7'}">
				<span class="state">{d.blocked ? 'Blocked' : 'On track'}</span>
				<div class="chain">
					<a href={`/projects/${d.from.code}`} class="node"><strong>{d.from.short}</strong><span>{d.from.milestone ?? 'No milestone'} · {day(d.from.due)}</span></a>
					<svg width="28" height="16" viewBox="0 0 28 16" fill="none" stroke="#111111" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M2 8h22M18 2l6 6-6 6" /></svg>
					<a href={`/projects/${d.to.code}`} class="node"><strong>{d.to.short}</strong><span>{d.to.milestone ?? 'No milestone'} · {day(d.to.due)}</span></a>
				</div>
				{#if d.note}<span class="note">{d.note}</span>{/if}
			</div>
		{:else}
			<p class="muted">No links between projects.</p>
		{/each}
	</div>
	<p class="muted">Dependencies are read from issue links in the trackers (for example JIRA "blocks") and from links the PMO records.</p>
</section>

<style>
	.title-row {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 20px;
	}
	.t {
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
	.range {
		height: 44px;
		border-radius: 999px;
		border: 1.5px solid #b9c7bd;
		display: inline-flex;
		align-items: center;
		padding: 0 16px;
		font-size: 14px;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 14px;
		font-size: 12px;
		font-weight: 600;
	}
	.legend span {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.bar {
		width: 18px;
		height: 10px;
		border-radius: 99px;
	}
	.dia {
		width: 10px;
		height: 10px;
		transform: rotate(45deg);
	}
	.today-key {
		width: 2px;
		height: 14px;
		background: #111;
	}
	.timeline {
		background: #fff;
		border-radius: 32px;
		padding: 24px;
		overflow-x: auto;
	}
	.inner {
		min-width: 1040px;
		display: flex;
		flex-direction: column;
	}
	.row {
		display: grid;
		grid-template-columns: 280px 1fr;
		align-items: center;
		min-height: 58px;
		border-bottom: 1px solid #f1f5f2;
	}
	.row.head {
		align-items: end;
		min-height: 0;
		padding-bottom: 10px;
		border-bottom: 1px solid #e3eae5;
	}
	.pl {
		font-size: 12px;
		font-weight: 600;
		color: #5b635d;
	}
	.proj {
		display: flex;
		align-items: center;
		gap: 10px;
		padding-right: 12px;
		min-width: 0;
		color: inherit;
	}
	.hd {
		width: 10px;
		height: 10px;
		border-radius: 99px;
		flex-shrink: 0;
	}
	.pn {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.pn a {
		font-size: 14px;
		font-weight: 700;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		text-decoration: none;
		color: #111;
	}
	.pn span {
		font-size: 11px;
		color: #5b635d;
		font-weight: 500;
	}
	.track {
		position: relative;
		height: 58px;
	}
	.months {
		height: 22px;
	}
	.months span {
		position: absolute;
		top: 0;
		font-size: 12px;
		font-weight: 700;
		color: #3e4640;
		padding-left: 6px;
		border-left: 1px solid #e3eae5;
		box-sizing: border-box;
	}
	.today {
		position: absolute;
		top: 0;
		bottom: 0;
		width: 2px;
		background: #111;
	}
	.span {
		position: absolute;
		top: 20px;
		height: 18px;
		border-radius: 99px;
	}
	.ms {
		position: absolute;
		top: 22px;
		width: 14px;
		height: 14px;
		margin-left: -7px;
		transform: rotate(45deg);
	}
	.dep {
		position: absolute;
		top: 2px;
		font-size: 11px;
		font-weight: 700;
		background: #111;
		color: #fff;
		border-radius: 99px;
		padding: 1px 8px;
		white-space: nowrap;
	}
	.deps {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.dh {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 700;
	}
	.n {
		width: 26px;
		height: 26px;
		border-radius: 999px;
		background: #111;
		color: #fff;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 700;
	}
	.dgrid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(360px, 100%), 1fr));
		gap: 16px;
	}
	.dcard {
		border-radius: 30px;
		padding: 22px 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.state {
		align-self: flex-start;
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 5px 12px;
		font-size: 12px;
		font-weight: 700;
	}
	.chain {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.node {
		background: #fff;
		border-radius: 18px;
		padding: 10px 14px;
		display: flex;
		flex-direction: column;
		text-decoration: none;
		color: #111;
	}
	.node strong {
		font-size: 14px;
	}
	.node span,
	.note {
		font-size: 12px;
	}
	.note {
		font-size: 13px;
		line-height: 1.5;
	}
	.muted {
		margin: 0;
		font-size: 13px;
		color: #5b635d;
	}
	@media (max-width: 767px) {
		h1 {
			font-size: 34px;
		}
	}
</style>
