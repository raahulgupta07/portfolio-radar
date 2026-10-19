<script lang="ts">
	import { day } from '$lib/format';

	let { data } = $props();
	const r = $derived(data.r);
	const LEVELS = ['High', 'Medium', 'Low'];
	const IMPACTS = ['Low', 'Medium', 'High'];
	const score: Record<string, number> = { Low: 1, Medium: 2, High: 3 };
	const cellBg = (li: string, im: string) => {
		const s = score[li] * score[im];
		return s >= 9 ? '#F2A9AE' : s >= 6 ? '#F8CDD0' : s >= 3 ? '#FBE6A9' : '#F4F7F5';
	};
	const BAR = ['#CFE3FB', '#FBE6A9', '#F8CDD0', '#E2F2E7', '#F1F5F2'];
</script>

<svelte:head><title>Risks and strategy · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div class="t"><h1>Risks &amp; Strategy</h1><span class="cnt tabular">{r.count}</span></div>
	<span class="sub">Risks are read from the trackers (risk labels, blockers), the sync log and Radar's checks</span>
</section>

<div class="top">
	<section class="matrix-card" aria-labelledby="m-h">
		<h2 id="m-h">Risk matrix</h2>
		<div class="matrix">
			{#each LEVELS as li (li)}
				<span class="axis">{li}</span>
				{#each IMPACTS as im (im)}
					<div class="cell" style="background:{cellBg(li, im)}">
						{#each r.matrix[li][im] as c (c.id)}<span class="rk">{c.label}</span>{/each}
					</div>
				{/each}
			{/each}
			<span></span>
			{#each IMPACTS as im (im)}<span class="axis c">{im} impact</span>{/each}
		</div>
		<span class="hint">Rows: likelihood. Columns: impact.</span>
	</section>

	<section class="strategy" aria-labelledby="s-h">
		<div>
			<h2 id="s-h">Strategy alignment · 2030 aspirations</h2>
			<span class="sub light">Each project is tagged to one aspiration{r.strategy.filter((e: any) => e.gap).length ? `. ${r.strategy.filter((e: any) => e.gap).length} aspirations have no projects yet` : ''}.</span>
		</div>
		<ul>
			{#each r.strategy as e, i (e.tag)}
				<li>
					<span class="tag">{e.tag}</span>
					<span class="track"><span style="width:{r.max_projects ? (e.projects / r.max_projects) * 100 : 0}%;background:{BAR[i % BAR.length]}"></span></span>
					<span class="val tabular" class:gap={e.gap}>{e.gap ? '0 · gap' : `${e.projects} · avg ${e.avg_percent_done ?? 0}%`}</span>
				</li>
			{/each}
		</ul>
		<span class="sub light">Bar length = number of projects. Tags are set by the PMO in the tracker, not edited here.</span>
	</section>
</div>

<section class="register" aria-labelledby="r-h">
	<div class="rh"><h2 id="r-h">Risk register</h2><span class="sub">Sorted by score</span></div>
	<div class="scroll">
		<table>
			<thead><tr><th scope="col">ID</th><th scope="col">Risk</th><th scope="col">Project</th><th scope="col">Likelihood</th><th scope="col">Impact</th><th scope="col">Owner</th><th scope="col">Found in</th><th scope="col">Review</th></tr></thead>
			<tbody>
				{#each r.risks as k (k.id)}
					<tr>
						<td><span class="rid">{k.id}</span></td>
						<td><strong>{k.title}</strong>{#if k.detail}<br /><span class="muted">{k.detail}</span>{/if}</td>
						<td>{#if k.project}<a href={`/projects/${k.project.code}`}>{k.project.short}</a>{:else}{k.projects_label ?? '—'}{/if}</td>
						<td>{k.likelihood}</td>
						<td>{k.impact}</td>
						<td>{k.owner ?? '—'}</td>
						<td>{k.found_in}</td>
						<td>{k.review_date ? day(k.review_date) : '—'}</td>
					</tr>
				{:else}
					<tr><td colspan="8" class="muted">No risks recorded.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
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
	}
	h1 {
		margin: 0;
		font-size: 48px;
		font-weight: 700;
		letter-spacing: -0.035em;
		line-height: 1;
	}
	.cnt {
		min-width: 44px;
		height: 44px;
		border-radius: 999px;
		border: 1.5px solid #b9c7bd;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-weight: 600;
	}
	.sub {
		font-size: 13px;
		color: #3e4640;
	}
	.sub.light {
		color: #c9cfcb;
	}
	h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 700;
	}
	.top {
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
		align-items: stretch;
	}
	.matrix-card {
		flex: 2 1 460px;
		min-width: 0;
		background: #fff;
		border-radius: 32px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.matrix {
		display: grid;
		grid-template-columns: 88px repeat(3, minmax(0, 1fr));
		gap: 8px;
		align-items: stretch;
	}
	.axis {
		font-size: 12px;
		font-weight: 700;
		color: #5b635d;
		align-self: center;
	}
	.axis.c {
		text-align: center;
	}
	.cell {
		min-height: 74px;
		border-radius: 18px;
		padding: 10px;
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		align-content: flex-start;
	}
	.rk {
		background: #fff;
		border-radius: 99px;
		padding: 4px 10px;
		font-size: 12px;
		font-weight: 700;
		height: fit-content;
	}
	.hint {
		font-size: 12px;
		color: #5b635d;
	}
	.strategy {
		flex: 3 1 560px;
		min-width: 0;
		background: #161616;
		color: #fff;
		border-radius: 32px;
		padding: 26px;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.strategy > div {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.strategy ul {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.strategy li {
		display: grid;
		grid-template-columns: 210px 1fr 110px;
		gap: 14px;
		align-items: center;
	}
	.tag {
		font-size: 14px;
		font-weight: 700;
	}
	.track {
		height: 14px;
		border-radius: 99px;
		background: #2a2a2a;
		overflow: hidden;
	}
	.track span {
		display: block;
		height: 14px;
		border-radius: 99px;
	}
	.val {
		font-size: 13px;
		text-align: right;
	}
	.val.gap {
		color: #f2c14e;
		font-weight: 700;
	}
	.register {
		background: #fff;
		border-radius: 32px;
		padding: 24px 12px 12px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.rh {
		padding: 0 14px;
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: 8px;
	}
	.scroll {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 900px;
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
		vertical-align: top;
	}
	td a {
		font-weight: 700;
	}
	.rid {
		box-shadow: inset 0 0 0 1.5px #111;
		border-radius: 99px;
		padding: 2px 9px;
		font-size: 11px;
		font-weight: 700;
	}
	.muted {
		color: #5b635d;
		font-size: 12px;
	}
	@media (max-width: 767px) {
		h1 {
			font-size: 34px;
		}
		.strategy li {
			grid-template-columns: 1fr;
			gap: 6px;
		}
		.val {
			text-align: left;
		}
	}
</style>
