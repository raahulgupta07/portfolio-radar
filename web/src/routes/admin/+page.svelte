<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/components/Icon.svelte';
	import { dayTime, plural, source } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	const s = $derived(data.settings);
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update({ reset: false });
			busy = '';
		};
	};
	const dur = (sec: number | null) =>
		sec == null ? '—' : sec >= 60 ? `${Math.floor(sec / 60)} min ${String(Math.round(sec % 60)).padStart(2, '0')} s` : `${sec} s`;
</script>

<svelte:head><title>Admin · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div class="t"><h1>Settings</h1><span class="cnt tabular">{data.sources.length}</span></div>
	<form method="POST" action="?/syncAll" use:enhance={submitting('all')}>
		<button class="pill-btn primary" disabled={busy !== ''}><Icon name="refresh" size={16} />{busy === 'all' ? 'Syncing…' : 'Sync all now'}</button>
	</form>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<p class="note">Sources, sign-in, the LLM, Teams and email are set up in <a href="/admin/connections"><strong>Connections</strong></a>. Tools and agents have their own tabs.</p>

<div class="two">
	<section class="card col">
		<div><h2>Project code prefixes</h2><p class="sub">Only names that start with an active prefix are picked up.</p></div>
		<ul class="pfx">
			{#each data.prefixes as p (p.value)}
				<li class:off={!p.active}>
					<span class="d"></span><span class="pv">{p.value}</span>
					<span class="pc tabular" title="Projects using it">{p.projects}</span>
					<form method="POST" action="?/togglePrefix" use:enhance={submitting(`pfx-${p.value}`)}>
						<input type="hidden" name="value" value={p.value} />
						<input type="hidden" name="active" value={String(!p.active)} />
						<button class="mini" disabled={busy !== ''}>{p.active ? 'Turn off' : 'Turn on'}</button>
					</form>
				</li>
			{/each}
		</ul>
		<form class="row" method="POST" action="?/addPrefix" use:enhance={submitting('pfx-add')}>
			<label class="grow"><span class="sr-only">New prefix</span><input class="field w-full" name="value" placeholder="New prefix, e.g. CHL-FIN-" autocomplete="off" /></label>
			<button class="btn quiet" disabled={busy !== ''}><Icon name="plus" size={16} />Add</button>
		</form>
	</section>

	<section class="card col">
		<h2>Daily sync</h2>
		<form class="row wrap" method="POST" action="?/saveSchedule" use:enhance={submitting('sched')}>
			<label class="lab">Run time<input class="field" type="time" name="sync_time" value={s.sync_time} required /></label>
			<label class="lab">Time zone
				<select class="field" name="timezone">
					<option value="Asia/Yangon" selected={s.timezone === 'Asia/Yangon'}>Asia/Yangon (UTC+06:30)</option>
					<option value="Asia/Singapore" selected={s.timezone === 'Asia/Singapore'}>Asia/Singapore (UTC+08:00)</option>
					<option value="UTC" selected={s.timezone === 'UTC'}>UTC</option>
				</select>
			</label>
			<button class="btn dark" disabled={busy !== ''}>Save</button>
		</form>
		<p class="note">If a source fails, the tracker keeps its last good data and marks those projects <strong>Stale</strong>.</p>
	</section>
</div>

<div class="two">
	<section class="card col dark-card">
		<form method="POST" action="?/saveRadar" use:enhance={submitting('radar')} class="col">
			<div class="sh">
				<div><h2>Radar · portfolio agent</h2><p class="sub light">Runs after each daily sync. Read-only. Drafts need a person's approval.</p></div>
				<label class="toggle"><input type="checkbox" name="radar_on" checked={s.radar_on} />Radar on</label>
			</div>
			<div class="grid4">
				<label class="lab light">Stale after (days)<input class="field" type="number" name="stale_days" min="1" max="90" value={s.stale_days} /></label>
				<label class="lab light">Slipping window (days)<input class="field" type="number" name="slipping_window_days" min="1" max="60" value={s.slipping_window_days} /></label>
				<label class="lab light">Off track: milestone late by (days)<input class="field" type="number" name="overdue_days" min="0" max="60" value={s.overdue_days} /></label>
				<label class="lab light">At risk: progress behind time (pts)<input class="field" type="number" name="behind_points" min="1" max="100" value={s.behind_points} /></label>
			</div>
			<ul class="facts">
				<li><span class="d light"></span>Approvers <strong>{s.approvers_group} group</strong></li>
				<li><span class="d light"></span>Weekly digest <strong>{s.digest_day} {s.digest_time} · {s.digest_recipients}</strong></li>
				<li><span class="d light"></span>Radar can read <strong>Projects, history, findings (through MCP)</strong></li>
			</ul>
			<button class="btn self-start" disabled={busy !== ''}>Save Radar rules</button>
		</form>
	</section>

	<section class="card col">
		<form method="POST" action="?/saveAlerts" use:enhance={submitting('alerts')} class="col">
			<div><h2>Alerts</h2><p class="sub">Who gets told, and when. Alerts to people outside the app need approval.</p></div>
			<fieldset>
				<legend>Send an alert when</legend>
				<label><input type="checkbox" name="off_track" checked={s.alerts.off_track} />A project turns Off track</label>
				<label><input type="checkbox" name="milestone_overdue" checked={s.alerts.milestone_overdue} />A milestone becomes overdue</label>
				<label><input type="checkbox" name="sync_failed" checked={s.alerts.sync_failed} />A source sync fails</label>
				<label><input type="checkbox" name="digest_ready" checked={s.alerts.digest_ready} />The weekly digest is ready for approval</label>
				<label><input type="checkbox" name="no_update" checked={s.alerts.no_update} />A project has no update for {s.stale_days} days</label>
			</fieldset>
			<fieldset>
				<legend>Channels</legend>
				<label><input type="checkbox" name="in_app" checked={s.channels.in_app} />In app</label>
				<label><input type="checkbox" name="email" checked={s.channels.email} />Email</label>
				<label><input type="checkbox" name="teams" checked={s.channels.teams} />Microsoft Teams</label>
			</fieldset>
			<button class="btn dark self-start" disabled={busy !== ''}>Save alerts</button>
		</form>
	</section>
</div>

<section class="card col">
	<div class="sh">
		<div class="flex items-center gap-2.5"><h2>Non-compliant projects</h2><span class="badge">{data.nonCompliant.length}</span></div>
		<p class="sub">Found in a tracker but skipped: the name has no approved prefix. Ask the team to rename it.</p>
	</div>
	<div class="scroll">
		<table>
			<thead><tr><th scope="col">Name in tracker</th><th scope="col">Source</th><th scope="col">Team</th><th scope="col">Reason</th></tr></thead>
			<tbody>
				{#each data.nonCompliant as n (n.source + n.name_in_tracker)}
					<tr><td class="b">{n.name_in_tracker}</td><td><span class="chip" style="background:{source(n.source).bg}">{n.source_name}</span></td><td>{n.team}</td><td>{n.reason}</td></tr>
				{:else}
					<tr><td colspan="4" class="muted">Every project name follows the convention.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>

<section class="card col">
	<div class="sh"><h2>Sync log</h2><p class="sub">Kept for 90 days</p></div>
	<div class="scroll">
		<table>
			<thead><tr><th scope="col">Started</th><th scope="col">Source</th><th scope="col">Duration</th><th scope="col">Projects read</th><th scope="col">Result</th></tr></thead>
			<tbody>
				{#each data.syncLog as r (r.id)}
					<tr>
						<td class="nowrap">{dayTime(r.started_at)}</td>
						<td>{r.source_name}</td>
						<td class="tabular">{dur(r.duration_seconds)}</td>
						<td class="tabular">{r.projects_read}</td>
						<td>
							<span class="res" class:fail={r.result === 'failed'}>{r.result === 'ok' ? 'Success' : r.result === 'failed' ? 'Failed' : 'Running'}</span>
							{#if r.errors?.length}<span class="errs">{r.errors[0]}</span>{/if}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</section>
