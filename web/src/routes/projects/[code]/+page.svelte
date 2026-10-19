<script lang="ts">
	import HealthPill from '$lib/components/HealthPill.svelte';
	import Icon from '$lib/components/Icon.svelte';
	import RadarFace from '$lib/components/RadarFace.svelte';
	import { STATUS_DOT, day, dayTime, fullDate, health, source } from '$lib/format';

	let { data } = $props();
	const p = $derived(data.p);
	const src = $derived(source(p.source));
	const h = $derived(health(p.health));
	let copied = $state(false);

	const trendMax = $derived(Math.max(1, ...p.trend.map((t: any) => t.percent_done ?? 0)));
	const weekDelta = $derived(
		p.trend.length > 1 ? (p.trend.at(-1).percent_done ?? 0) - (p.trend.at(-2).percent_done ?? 0) : null
	);
	const radarTitle = $derived(
		p.health === 'on_track'
			? 'Radar: on track'
			: p.health === 'done'
				? 'Radar: done'
				: `Radar: ${h.label.toLowerCase()}`
	);
	const radarText = $derived(
		p.radar_note ?? (p.health_reasons.length ? p.health_reasons.join('. ') + '.' : 'No problems found in the last check.')
	);
	const keyLabel = $derived(`${src.label} key`);
	function copy() {
		navigator.clipboard?.writeText(location.href).then(() => {
			copied = true;
			setTimeout(() => (copied = false), 2000);
		});
	}
	const msTone = (m: any) =>
		m.status === 'done'
			? { bg: '#CFE3FB', num: '#33404F' }
			: m.overdue
				? { bg: '#F8CDD0', num: '#4E2F32' }
				: m.next
					? { bg: '#FBE6A9', num: '#4A4128' }
					: { bg: '#FFFFFF', num: '#5B635D' };
</script>

<svelte:head><title>{p.name} · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div class="t">
		<a href="/" class="icon-btn" aria-label="Back to overview"><Icon name="back" /></a>
		<h1>Project Detail</h1>
		<span class="code">{p.code}</span>
	</div>
	<div class="flex gap-2.5">
		<button type="button" class="icon-btn" aria-label="Copy link" title={copied ? 'Link copied' : 'Copy link'} onclick={copy}>
			<Icon name={copied ? 'check' : 'external'} />
		</button>
		<a class="icon-btn" href={`/projects/${p.code}/one-pager.pdf`} target="_blank" rel="noopener" data-sveltekit-reload aria-label="One-pager PDF of this project" title="One-pager PDF"><Icon name="file" /></a>
	</div>
</section>

<section class="hero">
	<div class="left">
		<div class="big" style="background:{src.bg}">
			<span class="cap">Progress</span>
			<span class="pct tabular">{p.percent_done ?? '—'}<small>%</small></span>
			<div class="track"><div style="width:{p.percent_done ?? 0}%"></div></div>
			<span class="cap">{p.tasks ? `${p.tasks.done} of ${p.tasks.total} tasks done` : 'No task counts'}</span>
		</div>
		<div class="minis">
			<div style="background:#FBE6A9"><b class="tabular">{p.milestones_done}/{p.milestones.length}</b><span style="color:#4A4128">Milestones</span></div>
			<div style="background:#F8CDD0"><b class="tabular">{p.days_left ?? '—'}</b><span style="color:#4E2F32">{p.days_left != null && p.days_left < 0 ? 'Days over' : 'Days left'}</span></div>
		</div>
	</div>

	<div class="right">
		<div class="name-row">
			<div class="nm">
				<h2>{p.name}</h2>
				<span class="srcbadge">{src.short}</span>
			</div>
			<div class="chips">
				<span class="status"><span class="sd" style={STATUS_DOT[p.status] ?? ''}></span>{p.status}</span>
				<HealthPill value={p.health} />
				{#if p.stale}
					<span class="stale" title={p.source_info.error}>Stale · data from {day(p.source_info.last_good_sync_at)}</span>
				{:else}
					<span class="synced" title="Synced"><Icon name="check" size={16} stroke={2.2} /></span>
				{/if}
			</div>
		</div>

		<dl>
			<div><span class="dd"></span><dt>Team</dt><dd>{p.team}</dd></div>
			<div><span class="dd"></span><dt>Start</dt><dd>{fullDate(p.start_date)}</dd></div>
			<div><span class="dd"></span><dt>End</dt><dd>{fullDate(p.end_date)}</dd></div>
			<div><span class="dd" class:hollow={!p.owner}></span><dt>Owner</dt><dd>{p.owner ?? 'No owner'}</dd></div>
			<div><span class="dd"></span><dt>Strategy</dt><dd>{p.strategy ?? 'Not tagged'}</dd></div>
			<div><span class="dd"></span><dt>Prefix</dt><dd>{p.prefix}</dd></div>
			<div><span class="dd hollow"></span><dt>{keyLabel}</dt><dd>{p.source_key}</dd></div>
			<div><span class="dd"></span><dt>Updated</dt><dd>{day(p.updated)}</dd></div>
			<div><span class="dd"></span><dt>Synced</dt><dd>{dayTime(p.synced_at)}</dd></div>
		</dl>

		{#if p.sprint}
			<div class="sprint">
				<div class="sh">
					<h3>{p.sprint.name} · {day(p.sprint.start_date)}–{day(p.sprint.end_date)}</h3>
					<span class="chip">Current</span>
				</div>
				{#if p.sprint.goal}<p>Goal: {p.sprint.goal}</p>{:else}<p class="muted">No sprint goal set.</p>{/if}
			</div>
		{/if}
		{#if p.tasks}
			<div class="tasks">
				<div><b class="tabular">{p.tasks.done}</b><span>Done</span></div>
				<div><b class="tabular">{p.tasks.in_progress}</b><span>In progress</span></div>
				<div><b class="tabular">{p.tasks.todo}</b><span>To do</span></div>
			</div>
			<div class="stack" role="img" aria-label={`Tasks: ${p.tasks.done} done, ${p.tasks.in_progress} in progress, ${p.tasks.todo} to do`}>
				<span style="flex:{p.tasks.done};background:#7FB2EC"></span>
				<span style="flex:{p.tasks.in_progress};background:#EAC45A"></span>
				<span style="flex:{p.tasks.todo};background:#EE9AA0"></span>
			</div>
		{/if}
	</div>

	{#if p.source_url}
		<a class="edit" href={p.source_url} target="_blank" rel="noopener noreferrer"><Icon name="external" size={16} />Open in {src.label} to edit</a>
	{/if}
</section>

<section class="ms">
	<div class="msh"><h2>Milestones</h2><span class="n">{p.milestones.length}</span></div>
	{#if p.milestones.length}
		<ol>
			{#each p.milestones as m, i (m.name + i)}
				{@const tone = msTone(m)}
				<li style="background:{tone.bg}">
					<div class="mtop">
						<span class="num" style="color:{tone.num}">{String(i + 1).padStart(2, '0')}</span>
						{#if m.status === 'done'}<span class="ok"><Icon name="check" size={16} stroke={2.2} /></span>
						{:else if m.overdue}<span class="tag" style="background:#C23B3B">Overdue</span>
						{:else if m.next}<span class="tag">Next</span>
						{:else}<span class="empty"></span>{/if}
					</div>
					<span class="mn">{m.name}</span>
					<span class="md" class:muted={m.status !== 'done' && !m.next && !m.overdue}>
						<span class="mdot" class:hollow={m.status !== 'done' && !m.next && !m.overdue}></span>
						{m.status === 'done' ? `Done ${fullDate(m.completed_at ?? m.due_date)}` : m.due_date ? `Due ${fullDate(m.due_date)}` : 'No date'}
					</span>
				</li>
			{/each}
		</ol>
	{:else}
		<p class="muted">No milestones in {src.label} yet.</p>
	{/if}
</section>

<section class="radar">
	<span class="face"><RadarFace mood={p.health === 'off_track' ? 'alert' : p.health === 'at_risk' ? 'asking' : 'ready'} size={44} /></span>
	<div class="rt">
		<span class="rh">{radarTitle}</span>
		<span class="rb">{radarText}</span>
	</div>
	<a href={`/radar?about=${encodeURIComponent(p.code)}`} class="ask">Ask Radar about this project</a>
</section>

<div class="grid3">
	<section class="card2">
		<div class="sh">
			<h2>Progress trend</h2>
			{#if weekDelta != null}<span class="chip">{weekDelta >= 0 ? '+' : ''}{weekDelta} {Math.abs(weekDelta) === 1 ? 'pt' : 'pts'} this week</span>{/if}
		</div>
		{#if p.trend.length}
			<div class="bars" role="img" aria-label={`Progress by week: ${p.trend.map((t: any) => t.percent_done).join(', ')} percent`}>
				{#each p.trend as t, i (t.date)}
					<div class="bc">
						<span class="tabular">{t.percent_done}</span>
						<div style="height:{Math.max(4, Math.round(((t.percent_done ?? 0) / trendMax) * 102))}px;background:{i === p.trend.length - 1 ? '#111111' : src.bg}"></div>
					</div>
				{/each}
			</div>
			<div class="bl">{#each p.trend as t (t.date)}<span>{day(t.date)}</span>{/each}</div>
		{:else}
			<p class="muted">No history yet.</p>
		{/if}
	</section>

	<section class="card2">
		<h2>What changed this week</h2>
		<ul class="dots">
			{#each p.changes as c (c)}
				<li><span class="dd" class:hollow={c.startsWith('No ')}></span>{c}</li>
			{/each}
		</ul>
	</section>

	<section class="card2">
		<div class="sh"><h2>Risks and dependencies</h2><a href="/risks" class="lnk">All risks</a></div>
		{#each p.risks as r (r.id)}
			<div class="risk">
				<span class="rr"><span class="rid">{r.id}</span><strong>{r.title}</strong></span>
				<span class="rm">Likelihood {r.likelihood.toLowerCase()} · impact {r.impact.toLowerCase()}{r.review_date ? ` · review ${day(r.review_date)}` : ''}</span>
			</div>
		{:else}
			<p class="muted">No risks recorded in {src.label}.</p>
		{/each}
		<ul class="dots">
			<li>
				<span class="dd" class:hollow={!p.waits_for.length}></span>
				Waits for:
				{#each p.waits_for as w, i (w.code)}<a href={`/projects/${w.code}`}>{w.short}</a>{#if w.health === 'off_track'} (off track){/if}{i < p.waits_for.length - 1 ? ', ' : ''}{:else}no other project{/each}
			</li>
			<li>
				<span class="dd" class:hollow={!p.blocks.length}></span>
				Blocks:
				{#each p.blocks as b, i (b.code)}<a href={`/projects/${b.code}`}>{b.short}</a>{i < p.blocks.length - 1 ? ', ' : ''}{:else}no other project{/each}
			</li>
		</ul>
	</section>
</div>

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
	.code {
		height: 44px;
		border-radius: 999px;
		border: 1.5px solid #b9c7bd;
		display: inline-flex;
		align-items: center;
		padding: 0 16px;
		font-size: 14px;
		font-weight: 600;
	}
	.hero {
		background: #fff;
		border-radius: 36px;
		padding: 20px 20px 44px;
		display: flex;
		flex-wrap: wrap;
		gap: 28px;
		position: relative;
		margin-bottom: 8px;
	}
	.left {
		flex: 0 1 260px;
		min-width: 220px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.big {
		border-radius: 26px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		min-height: 220px;
	}
	.cap {
		font-size: 13px;
		font-weight: 600;
		color: #33404f;
	}
	.big .cap:last-child {
		font-size: 12px;
		font-weight: 500;
	}
	.pct {
		font-size: 64px;
		font-weight: 700;
		letter-spacing: -0.04em;
		line-height: 1;
	}
	.pct small {
		font-size: 26px;
	}
	.track {
		height: 10px;
		background: rgba(255, 255, 255, 0.75);
		border-radius: 99px;
		overflow: hidden;
	}
	.track div {
		height: 10px;
		background: #111;
		border-radius: 99px;
	}
	.minis {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px;
	}
	.minis div {
		border-radius: 22px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.minis b {
		font-size: 22px;
	}
	.minis span {
		font-size: 12px;
	}
	.right {
		flex: 1 1 520px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 22px;
		padding: 8px 8px 8px 0;
	}
	.name-row {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 16px;
		flex-wrap: wrap;
	}
	.nm {
		display: flex;
		align-items: center;
		gap: 16px;
	}
	h2 {
		margin: 0;
		font-size: 17px;
		font-weight: 700;
	}
	.nm h2 {
		font-size: 34px;
		letter-spacing: -0.03em;
		line-height: 1.1;
		max-width: 16ch;
	}
	.srcbadge {
		width: 60px;
		height: 60px;
		border-radius: 999px;
		border: 1.5px solid #dde5df;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		font-size: 12px;
		font-weight: 800;
		flex-shrink: 0;
	}
	.chips {
		display: flex;
		align-items: center;
		gap: 8px;
		flex-wrap: wrap;
	}
	.status {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		border: 1.5px solid #dde5df;
		border-radius: 999px;
		padding: 0 16px;
		height: 44px;
		font-size: 13px;
		font-weight: 600;
	}
	.sd {
		width: 8px;
		height: 8px;
		border-radius: 99px;
	}
	.synced {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border-radius: 999px;
		background: #111;
		color: #fff;
	}
	.stale {
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 0 14px;
		height: 44px;
		display: inline-flex;
		align-items: center;
		font-size: 12px;
		font-weight: 700;
	}
	dl {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 16px 24px;
		font-size: 14px;
	}
	dl div {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	dt {
		color: #5b635d;
	}
	dd {
		margin: 0;
		font-weight: 700;
	}
	.dd {
		width: 8px;
		height: 8px;
		border-radius: 99px;
		background: #111;
		flex-shrink: 0;
	}
	.dd.hollow,
	.mdot.hollow {
		background: #fff;
		box-shadow: inset 0 0 0 1.5px #111;
	}
	.sprint,
	.card2 {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.sh {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
	}
	h3 {
		margin: 0;
		font-size: 17px;
		font-weight: 700;
	}
	.sprint p {
		margin: 0;
		font-size: 15px;
		line-height: 1.5;
		color: #2a302c;
	}
	.chip {
		font-size: 12px;
		font-weight: 700;
		background: #f1f5f2;
		border-radius: 99px;
		padding: 4px 10px;
		white-space: nowrap;
	}
	.tasks {
		display: flex;
		gap: 36px;
		flex-wrap: wrap;
	}
	.tasks div {
		display: flex;
		flex-direction: column;
	}
	.tasks b {
		font-size: 26px;
		font-weight: 600;
	}
	.tasks span {
		font-size: 12px;
		color: #5b635d;
	}
	.stack {
		display: flex;
		height: 14px;
		gap: 3px;
	}
	.stack span {
		border-radius: 99px;
	}
	.edit {
		position: absolute;
		left: 50%;
		bottom: -24px;
		transform: translateX(-50%);
		display: inline-flex;
		align-items: center;
		gap: 10px;
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 0 26px;
		min-height: 48px;
		font-weight: 700;
		font-size: 14px;
		text-decoration: none;
		white-space: nowrap;
	}
	.ms {
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding-top: 16px;
	}
	.msh {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.msh h2 {
		font-size: 18px;
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
	ol {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
		gap: 12px;
	}
	ol li {
		border-radius: 26px;
		padding: 18px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.mtop {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.num {
		font-size: 12px;
		font-weight: 700;
	}
	.ok {
		width: 34px;
		height: 34px;
		border-radius: 999px;
		background: #fff;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.tag {
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 6px 12px;
		font-size: 11px;
		font-weight: 700;
	}
	.empty {
		width: 34px;
		height: 34px;
		border-radius: 999px;
		border: 1.5px solid #dde5df;
	}
	.mn {
		font-size: 15px;
		font-weight: 700;
	}
	.md {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
	}
	.mdot {
		width: 7px;
		height: 7px;
		border-radius: 99px;
		background: #111;
	}
	.muted {
		color: #5b635d;
		margin: 0;
		font-size: 14px;
	}
	.md.muted {
		font-size: 12px;
	}
	.radar {
		background: #161616;
		color: #fff;
		border-radius: 32px;
		padding: 22px 26px;
		display: flex;
		flex-wrap: wrap;
		gap: 16px;
		align-items: center;
	}
	.face {
		width: 48px;
		height: 48px;
		border-radius: 999px;
		background: #fff;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.rt {
		flex: 1 1 420px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.rh {
		font-size: 16px;
		font-weight: 700;
	}
	.rb {
		font-size: 14px;
		line-height: 1.5;
		color: #d9deda;
	}
	.ask {
		display: inline-flex;
		align-items: center;
		background: #fff;
		color: #111;
		border-radius: 999px;
		padding: 0 20px;
		min-height: 44px;
		font-weight: 700;
		font-size: 14px;
		text-decoration: none;
	}
	.grid3 {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(340px, 100%), 1fr));
		gap: 16px;
		align-items: stretch;
	}
	.card2 {
		background: #fff;
		border-radius: 30px;
		padding: 24px;
		gap: 12px;
	}
	.bars {
		display: flex;
		align-items: flex-end;
		gap: 10px;
		height: 130px;
		border-bottom: 1px solid #e3eae5;
	}
	.bc {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}
	.bc span {
		font-size: 11px;
		font-weight: 700;
	}
	.bc div {
		width: 100%;
		max-width: 28px;
		border-radius: 8px 8px 2px 2px;
	}
	.bl {
		display: flex;
		gap: 10px;
		font-size: 11px;
		color: #5b635d;
	}
	.bl span {
		flex: 1;
		text-align: center;
	}
	.dots {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 12px;
		font-size: 14px;
	}
	.dots li {
		display: flex;
		gap: 10px;
		align-items: baseline;
		flex-wrap: wrap;
	}
	.dots a {
		font-weight: 700;
	}
	.risk {
		background: #f4f7f5;
		border-radius: 20px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.rr {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.rid {
		box-shadow: inset 0 0 0 1.5px #111;
		border-radius: 99px;
		padding: 2px 9px;
		font-size: 11px;
		font-weight: 700;
	}
	.rm {
		font-size: 13px;
		color: #3e4640;
	}
	.lnk {
		font-size: 13px;
		font-weight: 700;
	}
	@media (max-width: 767px) {
		h1 {
			font-size: 30px;
		}
		.nm h2 {
			font-size: 26px;
		}
		.edit {
			position: static;
			transform: none;
			width: 100%;
			justify-content: center;
		}
		.hero {
			padding-bottom: 20px;
		}
	}
	@media print {
		.edit,
		.ask,
		.icon-btn {
			display: none;
		}
	}
</style>
