<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/components/Icon.svelte';
	import { dayTime, plural, source } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	const s = $derived(data.settings);
	type Tool = { server: string; tool: string; status: string; callers: string[]; roles: string[]; read_only: boolean };
	const byServer = $derived.by(() => {
		const acc: Record<string, Tool[]> = {};
		for (const t of data.tools as Tool[]) (acc[t.server] ??= []).push(t);
		return Object.entries(acc);
	});
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
	<div class="t"><h1>Admin Settings</h1><span class="cnt tabular">{data.sources.length}</span></div>
	<form method="POST" action="?/syncAll" use:enhance={submitting('all')}>
		<button class="pill-btn primary" disabled={busy !== ''}><Icon name="refresh" size={16} />{busy === 'all' ? 'Syncing…' : 'Sync all now'}</button>
	</form>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<section class="sources" aria-label="Source connections">
	{#each data.sources as src (src.id)}
		{@const si = source(src.id)}
		{@const failed = src.status === 'failed'}
		<div class="srcc" style="background:{si.bg}">
			<div class="sh">
				<div class="sn"><span class="n">{src.name}</span><span class="tm">{src.team}</span></div>
				<span class="state" class:fail={failed}>{failed ? 'Sync failed' : src.status === 'ok' ? 'Connected' : 'Not synced yet'}</span>
			</div>
			<ul>
				<li><span class="d"></span>URL <strong>{src.base_url || 'Not set (sample data)'}</strong></li>
				<li><span class="d"></span>Access <strong>Read-only token</strong></li>
				{#if failed}
					<li><span class="d"></span>Last good sync <strong>{src.last_good_sync_at ? `${dayTime(src.last_good_sync_at)} · ${plural(src.projects, 'project')}` : 'never'}</strong></li>
					<li><span class="d"></span>Error <strong class="err">{src.error}</strong></li>
				{:else}
					<li><span class="d"></span>Last sync <strong>{src.last_sync_at ? `${dayTime(src.last_sync_at)} · ${plural(src.projects, 'project')}` : 'never'}</strong></li>
				{/if}
			</ul>
			<div class="btns">
				<form method="POST" action="?/testSource" use:enhance={submitting(`test-${src.id}`)}>
					<input type="hidden" name="source" value={src.id} />
					<button class="btn" disabled={busy !== ''}>{busy === `test-${src.id}` ? 'Testing…' : 'Test'}</button>
				</form>
				<form method="POST" action="?/syncSource" use:enhance={submitting(`sync-${src.id}`)}>
					<input type="hidden" name="source" value={src.id} />
					<button class="btn" disabled={busy !== ''}>{busy === `sync-${src.id}` ? 'Syncing…' : 'Sync now'}</button>
				</form>
				<details class="tok">
					<summary class="btn" class:dark={failed}>{failed ? 'Update token' : 'Token'}</summary>
					<p>The read-only token is kept in the secret store as <code>{src.secret_ref}</code>, never in this app. Update it there, then press Test.</p>
				</details>
			</div>
		</div>
	{/each}
</section>

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

<section class="card col">
	<div class="sh">
		<div><h2>MCP tools</h2><p class="sub">Every tool starts off. Turn on only what people and agents need. Changed tools wait for review.</p></div>
	</div>
	{#each data.changes as c (c.id)}
		<div class="change">
			<p><strong>{c.server}.{c.tool}</strong> changed and waits for review.</p>
			<pre>{JSON.stringify(c.diff, null, 2)}</pre>
			<div class="btns">
				<form method="POST" action="?/decideChange" use:enhance={submitting(`chg-${c.id}`)}><input type="hidden" name="change_id" value={c.id} /><input type="hidden" name="approve" value="true" /><button class="btn dark" disabled={busy !== ''}>Approve</button></form>
				<form method="POST" action="?/decideChange" use:enhance={submitting(`chg-${c.id}`)}><input type="hidden" name="change_id" value={c.id} /><input type="hidden" name="approve" value="false" /><button class="btn" disabled={busy !== ''}>Reject</button></form>
			</div>
		</div>
	{/each}
	<div class="tools">
		{#each byServer as [server, tools] (server)}
			<details>
				<summary><span class="b">/{server}/mcp</span><span class="muted">{tools.filter((t) => t.status === 'on').length} of {tools.length} on</span></summary>
				<ul>
					{#each tools as t (t.tool)}
						<li>
							<div class="tn"><span class="b">{t.tool}</span><span class="muted small">{t.callers.join(', ')} · {t.roles.join(', ') || 'any role'}{t.read_only ? ' · read-only' : ''}</span></div>
							<span class="st st-{t.status}">{t.status}</span>
							{#if t.status !== 'review'}
								<form method="POST" action="?/toolStatus" use:enhance={submitting(`tool-${server}-${t.tool}`)}>
									<input type="hidden" name="server" value={server} /><input type="hidden" name="tool" value={t.tool} />
									<input type="hidden" name="status" value={t.status === 'on' ? 'off' : 'on'} />
									<button class="mini" disabled={busy !== ''}>{t.status === 'on' ? 'Turn off' : 'Turn on'}</button>
								</form>
							{/if}
						</li>
					{/each}
				</ul>
			</details>
		{/each}
	</div>
</section>

<section class="card col">
	<div class="sh"><h2>Recent activity</h2><p class="sub">Every MCP call, by people, agents and services. Kept for 90 days.</p></div>
	<div class="scroll">
		<table>
			<thead><tr><th scope="col">When</th><th scope="col">Caller</th><th scope="col">Tool</th><th scope="col">Result</th></tr></thead>
			<tbody>
				{#each data.audit as a, i (i)}
					<tr>
						<td class="nowrap">{dayTime(a.at)}</td>
						<td>{a.caller}</td>
						<td><code>{a.server}.{a.tool}</code></td>
						<td><span class="res" class:fail={a.outcome !== 'ok'}>{a.outcome}</span>{#if a.reason}<span class="errs">{a.reason}</span>{/if}</td>
					</tr>
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
	h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 700;
	}
	.sub {
		margin: 4px 0 0;
		font-size: 13px;
		color: #5b635d;
	}
	.sub.light {
		color: #c9cfcb;
	}
	.flash {
		margin: 0;
		background: #e2f2e7;
		border-radius: 20px;
		padding: 14px 18px;
		font-weight: 600;
		font-size: 14px;
	}
	.flash.bad {
		background: #f8cdd0;
	}
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		border-radius: 999px;
		padding: 0 16px;
		min-height: 44px;
		font: 600 13px var(--font-sans);
		cursor: pointer;
		border: 0;
		background: #fff;
		color: #111;
		list-style: none;
	}
	.btn:hover {
		background: #f4f7f5;
	}
	.btn.dark {
		background: #111;
		color: #fff;
	}
	.btn.quiet {
		background: #f1f5f2;
	}
	.btn:disabled,
	.mini:disabled {
		opacity: 0.5;
		cursor: wait;
	}
	.sources {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
		gap: 16px;
	}
	.srcc {
		border-radius: 30px;
		padding: 22px 24px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.sh {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 12px;
		flex-wrap: wrap;
	}
	.sn {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.sn .n {
		font-size: 20px;
		font-weight: 700;
	}
	.tm {
		font-size: 13px;
		color: #33404f;
	}
	.state {
		background: #fff;
		border-radius: 999px;
		padding: 8px 14px;
		font-size: 12px;
		font-weight: 700;
	}
	.state.fail {
		background: #111;
		color: #fff;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.srcc ul,
	.facts {
		display: flex;
		flex-direction: column;
		gap: 10px;
		font-size: 13px;
	}
	.srcc li,
	.facts li {
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.srcc strong,
	.facts strong {
		margin-left: auto;
		text-align: right;
	}
	.err {
		color: #8a1c1c;
	}
	.d {
		width: 7px;
		height: 7px;
		border-radius: 99px;
		background: #111;
		flex-shrink: 0;
	}
	.d.light {
		background: #fff;
	}
	.btns {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
		align-items: flex-start;
	}
	.tok summary::-webkit-details-marker {
		display: none;
	}
	.tok p {
		margin: 8px 0 0;
		font-size: 13px;
		background: rgba(255, 255, 255, 0.7);
		border-radius: 16px;
		padding: 10px 12px;
	}
	.two {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(420px, 100%), 1fr));
		gap: 16px;
	}
	.col {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.pfx {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.pfx li {
		display: flex;
		align-items: center;
		gap: 10px;
		background: #161616;
		color: #fff;
		border-radius: 18px;
		padding: 8px 8px 8px 16px;
	}
	.pfx li.off {
		background: #f1f5f2;
		color: #5b635d;
	}
	.pfx .d {
		background: currentColor;
	}
	.pv {
		font-weight: 700;
		font-size: 14px;
		letter-spacing: 0.02em;
	}
	.pc {
		margin-left: auto;
		background: rgba(255, 255, 255, 0.15);
		border-radius: 99px;
		padding: 2px 10px;
		font-size: 12px;
		font-weight: 700;
	}
	.mini {
		min-height: 36px;
		border-radius: 999px;
		border: 0;
		padding: 0 12px;
		font: 600 12px var(--font-sans);
		cursor: pointer;
		background: #fff;
		color: #111;
	}
	.row {
		display: flex;
		gap: 8px;
		align-items: flex-end;
	}
	.row.wrap {
		flex-wrap: wrap;
	}
	.grow {
		flex: 1;
	}
	.lab {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 12px;
		font-weight: 600;
		color: #3e4640;
	}
	.lab.light {
		color: #d9deda;
	}
	.note {
		margin: 0;
		background: #f4f7f5;
		border-radius: 18px;
		padding: 12px 14px;
		font-size: 13px;
	}
	.dark-card {
		background: #161616;
		color: #fff;
	}
	.grid4 {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
		gap: 12px;
	}
	.toggle {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		background: #fff;
		color: #111;
		border-radius: 999px;
		padding: 0 14px;
		min-height: 40px;
		font-size: 13px;
		font-weight: 700;
	}
	fieldset {
		border: 0;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	legend {
		font-size: 12px;
		font-weight: 700;
		color: #5b635d;
		margin-bottom: 8px;
	}
	fieldset label {
		display: flex;
		align-items: center;
		gap: 10px;
		font-size: 14px;
		min-height: 32px;
	}
	input[type='checkbox'] {
		width: 18px;
		height: 18px;
		accent-color: #111;
	}
	.badge {
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
	.scroll {
		overflow-x: auto;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		min-width: 640px;
	}
	th {
		font-size: 12px;
		font-weight: 600;
		color: #5b635d;
		text-align: left;
		padding: 8px 12px;
	}
	td {
		padding: 12px;
		font-size: 14px;
		border-top: 1px solid #eef2ef;
		vertical-align: top;
	}
	.b {
		font-weight: 700;
	}
	.nowrap {
		white-space: nowrap;
	}
	.chip {
		border-radius: 999px;
		padding: 5px 11px;
		font-size: 12px;
		font-weight: 700;
	}
	.res {
		display: inline-block;
		background: #e2f2e7;
		border-radius: 999px;
		padding: 3px 10px;
		font-size: 12px;
		font-weight: 700;
	}
	.res.fail {
		background: #f8cdd0;
	}
	.errs {
		display: block;
		font-size: 12px;
		color: #5b635d;
		margin-top: 4px;
	}
	.muted {
		color: #5b635d;
	}
	.small {
		font-size: 12px;
	}
	.change {
		background: #fbe6a9;
		border-radius: 22px;
		padding: 14px 16px;
	}
	.change p {
		margin: 0 0 8px;
	}
	.change pre {
		margin: 0 0 10px;
		font-size: 12px;
		background: rgba(255, 255, 255, 0.6);
		border-radius: 14px;
		padding: 10px;
		overflow-x: auto;
	}
	.tools {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.tools details {
		background: #f4f7f5;
		border-radius: 20px;
		padding: 0 16px;
	}
	.tools summary {
		display: flex;
		justify-content: space-between;
		gap: 12px;
		min-height: 52px;
		align-items: center;
		cursor: pointer;
		font-size: 14px;
	}
	.tools ul {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding-bottom: 14px;
	}
	.tools li {
		display: flex;
		align-items: center;
		gap: 10px;
		background: #fff;
		border-radius: 16px;
		padding: 8px 10px 8px 14px;
	}
	.tn {
		display: flex;
		flex-direction: column;
		flex: 1;
		min-width: 0;
		font-size: 14px;
	}
	.st {
		font-size: 11px;
		font-weight: 800;
		text-transform: uppercase;
		border-radius: 99px;
		padding: 3px 9px;
		letter-spacing: 0.04em;
	}
	.st-on {
		background: #e2f2e7;
		color: #1f5c3a;
	}
	.st-off {
		background: #eef2ef;
		color: #5b635d;
	}
	.st-review {
		background: #fbe6a9;
		color: #4a4128;
	}
	.tools .mini {
		background: #f1f5f2;
	}
	@media (max-width: 767px) {
		h1 {
			font-size: 34px;
		}
	}
</style>
