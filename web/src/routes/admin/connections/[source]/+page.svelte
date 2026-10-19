<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/components/Icon.svelte';
	import { dayTime, source } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	const s = $derived(data.s);
	const check = $derived(form && 'check' in form ? (form as any).check : null);
	const defaults = $derived(
		Object.fromEntries(s.mapping.filter((m: any) => m.from === 'default').map((m: any) => [m.tracker_status.toLowerCase(), m.app_status]))
	);
	const AUTH: Record<string, string> = {
		api_token: 'API token + email (Cloud)',
		pat: 'Personal access token (Data Center)',
		api_key: 'API key',
		token: 'Access token'
	};
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update, result, formElement }: { update: (o?: { reset?: boolean }) => Promise<void>; result: { type: string }; formElement: HTMLFormElement }) => {
			await update({ reset: false });
			// A pasted secret is gone from the page once it is saved.
			if (result.type === 'success') formElement.querySelectorAll<HTMLInputElement>('input[type=password]').forEach((i) => (i.value = ''));
			busy = '';
		};
	};
	const steps = $derived([
		{ n: 1, label: 'Connection', done: !!s.base_url && (!!s.secret_set || s.source_mode === 'mock') },
		{ n: 2, label: 'Test', done: !!check?.ok },
		...(s.fields ? [{ n: 3, label: 'Field mapping', done: !!s.fields.confirmed_by }] : []),
		{ n: s.fields ? 4 : 3, label: 'Status mapping', done: s.unmapped.length === 0 },
		{ n: s.fields ? 5 : 4, label: 'Tools', done: s.tools.every((t: any) => t.status === 'on') }
	]);
</script>

<svelte:head><title>Set up {s.name} · Admin · Portfolio Radar</title></svelte:head>

<a class="crumb" href="/admin/connections"><Icon name="back" size={14} />Connections</a>
<section class="title-row">
	<div>
		<h1>Set up {s.name}</h1>
		<p class="lead">{s.team} · <span class="mono">/{s.source}/mcp</span> · read-only{s.last_sync_at ? ` · last sync ${dayTime(s.last_sync_at)}` : ''}</p>
	</div>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<ol class="card" style="list-style:none;margin:0;padding:14px 22px;border-radius:999px;display:flex;gap:12px;flex-wrap:wrap" aria-label="Steps">
	{#each steps as st (st.n)}
		<li style="display:flex;align-items:center;gap:10px;flex:1;min-width:140px">
			<span class="ic" class:no={!st.done} style={st.done ? '' : 'background:#111;color:#fff'}>{st.done ? '✓' : st.n}</span>
			<span class="b" style="font-size:14px">{st.label}</span>
		</li>
	{/each}
</ol>

<div class="halves">
	<div class="side">
		<section class="card col" style="background:{source(s.source).bg}" aria-labelledby="c-h">
			<div class="hrow"><h2 id="c-h">1 · Connection</h2>{#if s.source_mode === 'mock'}<span class="tag end">Sample data in use</span>{/if}</div>
			<form class="form" method="POST" action="?/saveConnection" use:enhance={submitting('conn')}>
				{#if s.source === 'jira'}
					<div class="lab">Where JIRA runs
						<div class="seg2" role="radiogroup" aria-label="Where JIRA runs">
							<label><input type="radio" name="flavor" value="cloud" checked={s.flavor !== 'datacenter'} />Cloud</label>
							<label><input type="radio" name="flavor" value="datacenter" checked={s.flavor === 'datacenter'} />Data Center</label>
						</div>
					</div>
				{/if}
				<label class="lab">Address<input class="inp" name="base_url" type="url" placeholder="https://…" value={s.base_url} pattern="https://.*" /></label>
				<div class="fgrid">
					<label class="lab">Sign-in
						<select class="inp" name="auth_method">
							{#each s.auth_methods as m (m)}<option value={m} selected={s.auth_method === m}>{AUTH[m] ?? m}</option>{/each}
						</select>
					</label>
					<label class="lab">Service account<input class="inp" name="account" value={s.account} placeholder="svc-portfolio-read@…" autocomplete="off" /></label>
				</div>
				<div class="lab">Read token
					<div class="secret">
						<span class="name mono"><Icon name="lock" size={14} />{s.secret_ref || 'none yet'}</span>
						<span class="tag {s.secret_set ? 'ok' : 'warn'}">{s.secret_set ? 'Set' : 'Empty'}</span>
					</div>
					<input class="inp" name="token" type="password" autocomplete="new-password" placeholder={s.secret_set ? 'Paste a new token to replace it' : 'Paste the read-only token'} />
					<span class="hint">You paste it once. It goes straight to the secret store; this page keeps only its name.</span>
				</div>
				<label class="lab">Secret name<input class="inp mono" name="secret_ref" value={s.secret_ref} placeholder="kv://{s.source}-read-token" /></label>
				<label class="toggle" style="align-self:flex-start"><input type="checkbox" name="enabled" checked={s.enabled} />Sync this source</label>
				<div class="ro"><Icon name="lock" size={14} />Read-only. The connector can only send GET requests. It cannot create, change or delete anything in {s.name}.</div>
				<button class="btn dark" style="align-self:flex-start" disabled={busy !== ''}>{busy === 'conn' ? 'Saving…' : 'Save connection'}</button>
			</form>
		</section>

		<section class="card col" aria-labelledby="t-h">
			<div class="hrow">
				<h2 id="t-h">2 · Test</h2>
				{#if check}<span class="sub" style="margin:0">Ran {dayTime(check.checked_at)}</span>{/if}
				<form class="end" method="POST" action="?/check" use:enhance={submitting('check')}><button class="btn quiet" disabled={busy !== ''}>{busy === 'check' ? 'Checking…' : check ? 'Run again' : 'Run the check'}</button></form>
			</div>
			{#if check}
				<ul class="checks">
					{#each check.checks as c (c.check)}
						<li><span class="ic" class:no={!c.ok}>{c.ok ? '✓' : '!'}</span><span>{c.check}</span><strong>{c.detail}</strong></li>
					{/each}
				</ul>
			{:else}
				<p class="sub" style="margin:0">Reads the project list through <span class="mono">/{s.source}/mcp</span>, like the nightly sync. Changes nothing.</p>
			{/if}
			{#if s.last_error}<p class="warnbox">Last sync: {s.last_error}</p>{/if}
		</section>
	</div>

	<div class="side">
		<section class="card col" aria-labelledby="m-h">
			<div class="hrow"><h2 id="m-h">{s.fields ? 4 : 3} · Status mapping</h2><span class="sub" style="margin:0">{s.name} status → app status</span></div>
			{#if s.unmapped.length}
				<p class="warnbox">{s.unmapped.length === 1 ? '1 status has' : `${s.unmapped.length} statuses have`} no mapping. Projects using {s.unmapped.length === 1 ? 'it' : 'them'} do not sync until you choose. Nothing is guessed.</p>
			{/if}
			<form class="form" method="POST" action="?/saveMapping" use:enhance={submitting('map')} style="gap:6px">
				<input type="hidden" name="defaults" value={JSON.stringify(defaults)} />
				{#each s.unmapped as st (st)}
					<div class="maprow miss">
						<span class="b">{st}</span><span class="muted">→</span>
						<input type="hidden" name="status" value={st} />
						<select name="app_status" aria-label="App status for {st}">
							<option value="">Choose…</option>
							{#each s.app_statuses as a (a)}<option value={a}>{a}</option>{/each}
						</select>
					</div>
				{/each}
				{#each s.mapping as m (m.tracker_status)}
					<div class="maprow">
						<span class="b">{m.tracker_status}</span><span class="from">{m.from === 'default' ? 'default' : s.name}</span><span class="muted">→</span>
						<input type="hidden" name="status" value={m.tracker_status} />
						<select name="app_status" aria-label="App status for {m.tracker_status}">
							{#each s.app_statuses as a (a)}<option value={a} selected={m.app_status === a}>{a}</option>{/each}
						</select>
					</div>
				{/each}
				<div class="maprow" style="background:#fff;border:1.5px dashed #dde5df">
					<input class="inp" style="min-height:36px;max-width:220px" name="new_status" placeholder="Add a status, e.g. UAT" aria-label="New tracker status" />
					<span class="muted">→</span>
					<select name="new_app_status" aria-label="App status for the new status">
						<option value="">Choose…</option>
						{#each s.app_statuses as a (a)}<option value={a}>{a}</option>{/each}
					</select>
				</div>
				<button class="btn dark" style="align-self:flex-start;margin-top:8px" disabled={busy !== ''}>{busy === 'map' ? 'Saving…' : 'Save mapping'}</button>
			</form>
		</section>

		<section class="card col" aria-labelledby="tl-h">
			<div class="hrow"><h2 id="tl-h">{s.fields ? 5 : 4} · Tools</h2><span class="sub" style="margin:0">on <span class="mono">/{s.source}/mcp</span></span></div>
			<ul class="checks">
				{#each s.tools as t (t.tool)}
					<li>
						<span class="mono b">{t.tool}</span>
						<span class="tag">{t.callers.join(' · ')}</span>
						<span class="st st-{t.status}" style="margin-left:auto">{t.status}</span>
						{#if t.status !== 'review'}
							<form method="POST" action="?/toolStatus" use:enhance={submitting(`tool-${t.tool}`)}>
								<input type="hidden" name="tool" value={t.tool} /><input type="hidden" name="status" value={t.status === 'on' ? 'off' : 'on'} />
								<button class="mini" style="background:#f1f5f2" disabled={busy !== ''}>{t.status === 'on' ? 'Turn off' : 'Turn on'}</button>
							</form>
						{:else}
							<a class="mini" href="/admin/tools?show=review" style="display:inline-flex;align-items:center;background:#fbe6a9;text-decoration:none">Review</a>
						{/if}
					</li>
				{/each}
			</ul>
			<p class="sub" style="margin:0">New tools start off. Only the nightly sync (service) and admins (people) can call them.</p>
		</section>
	</div>
</div>

{#if s.fields}
	<section class="card col" aria-labelledby="f-h">
		<div class="hrow">
			<h2 id="f-h">3 · Field mapping</h2>
			<span class="sub" style="margin:0">where {s.name} keeps each project field</span>
			<span class="st {s.fields.confirmed_by ? 'st-on' : 'st-review'}" style="margin-left:auto">
				{s.fields.confirmed_by ? `confirmed by ${s.fields.confirmed_by}` : 'not confirmed'}
			</span>
		</div>
		<p class={s.fields.confirmed_by ? 'sub' : 'warnbox'} style="margin:0">
			Every company sets up {s.name} its own way, so nothing here is guessed. These are proposals. Check each one against
			{s.name}, then confirm. A live sync does not read project fields until a person confirms. Changing a field later needs a new confirmation.
		</p>
		<form class="form fieldmap" method="POST" action="?/saveFields" use:enhance={submitting('fields')}>
			<input type="hidden" name="about" value={JSON.stringify(s.fields.about)} />
			{#each s.fields.about as a (a.field)}
				{@const v = s.fields.values[a.field]}
				<label class="fm">
					<span class="mono b">{a.field}</span>
					{#if a.kind === 'choice'}
						<select name="f_{a.field}">
							{#each a.options as o (o)}<option value={o} selected={v === o}>{o}</option>{/each}
						</select>
					{:else}
						<input class="inp mono" name="f_{a.field}" value={a.kind === 'list' ? (v ?? []).join(', ') : (v ?? '')} />
					{/if}
					<span class="sub">{a.help}{JSON.stringify(v) !== JSON.stringify(a.default) ? ' · changed from the proposal' : ''}</span>
				</label>
			{/each}
			<label class="confirm">
				<input type="checkbox" name="confirm" checked={!!s.fields.confirmed_by} />
				<span>I checked these against {s.name}. Use them for the live sync.</span>
			</label>
			<button class="btn dark" style="align-self:flex-start" disabled={busy !== ''}>{busy === 'fields' ? 'Saving…' : 'Save field mapping'}</button>
		</form>
	</section>
{/if}

<style>
	.fieldmap { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
	.fieldmap > .confirm, .fieldmap > button { grid-column: 1 / -1; }
	.confirm { display: flex; gap: 10px; align-items: center; }
	.fm { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
	.fm .inp, .fm select { min-height: 38px; width: 100%; }
</style>
