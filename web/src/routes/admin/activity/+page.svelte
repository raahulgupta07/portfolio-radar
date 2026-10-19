<script lang="ts">
	import { dayTime } from '$lib/format';

	let { data } = $props();
	const link = (outcome: string) => `?outcome=${outcome}${data.caller ? `&caller=${encodeURIComponent(data.caller)}` : ''}`;
</script>

<svelte:head><title>Activity · Admin · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div>
		<h1>Activity</h1>
		<p class="lead">Every MCP call by people, agents and services, allowed or blocked. Kept for 90 days.</p>
	</div>
</section>

<section class="card col">
	<div class="filters">
		<a href={link('all')} aria-current={data.outcome === 'all' ? 'true' : undefined}>All</a>
		<a href={link('denied')} aria-current={data.outcome === 'denied' ? 'true' : undefined}>Blocked</a>
		<a href={link('error')} aria-current={data.outcome === 'error' ? 'true' : undefined}>Errors</a>
		<form method="GET" style="margin-left:auto;display:flex;gap:8px">
			<input type="hidden" name="outcome" value={data.outcome} />
			<label><span class="sr-only">Caller</span><input class="field" style="min-height:36px" name="caller" value={data.caller} placeholder="Caller, e.g. radar" /></label>
			<button class="mini" style="background:#f1f5f2">Filter</button>
		</form>
	</div>
	<div class="scroll">
		<table>
			<thead><tr><th scope="col">When</th><th scope="col">Caller</th><th scope="col">Tool</th><th scope="col">Result</th><th scope="col">Time</th></tr></thead>
			<tbody>
				{#each data.calls as a, i (i)}
					<tr>
						<td class="nowrap">{dayTime(a.at)}</td>
						<td>{a.caller}</td>
						<td><code>{a.server}.{a.tool}</code></td>
						<td><span class="res" class:fail={a.outcome !== 'ok'}>{a.outcome === 'denied' ? 'blocked' : a.outcome}</span>{#if a.reason}<span class="errs">{a.reason}</span>{/if}</td>
						<td class="tabular nowrap">{a.duration_ms} ms</td>
					</tr>
				{:else}
					<tr><td colspan="5" class="muted">No calls match.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>
