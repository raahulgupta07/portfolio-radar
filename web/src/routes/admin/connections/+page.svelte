<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/components/Icon.svelte';
	import { dayTime, plural, source } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	const c = $derived(data.c);
	const sum = $derived(c.summary);
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update({ reset: false });
			busy = '';
		};
	};
	const SERVICES: Record<string, { title: string; what: string }> = {
		sso: { title: 'City SSO', what: 'Microsoft Entra ID · groups to roles' },
		llm: { title: 'LLM for Radar', what: 'Summaries and answers · OpenAI-compatible' },
		teams: { title: 'Microsoft Teams', what: 'Approved drafts to a channel' },
		email: { title: 'Email', what: 'Approved drafts by SMTP' }
	};
	const STATUS: Record<string, { label: string; cls: string }> = {
		ready: { label: 'Connected', cls: 'ok' },
		not_set: { label: 'Not set up', cls: 'warn' },
		rules_only: { label: 'Rules only', cls: 'warn' },
		secret_missing: { label: 'Secret missing', cls: 'bad' }
	};
	const svcLine = (name: string, s: any) => {
		const cfg = s.config;
		if (name === 'sso') return cfg.tenant_id ? `Tenant ${cfg.tenant_id.slice(0, 8)}… · ${cfg.groups.length} groups` : SERVICES.sso.what;
		if (name === 'llm') return cfg.base_url ? `${cfg.model || 'no model'} · ${new URL(cfg.base_url).host}` : SERVICES.llm.what;
		if (name === 'teams') return cfg.channel || (cfg.webhook_ref ? cfg.webhook_ref : SERVICES.teams.what);
		return cfg.smtp_host ? `SMTP · ${cfg.smtp_host}` : SERVICES.email.what;
	};
</script>

<svelte:head><title>Connections · Admin · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div>
		<div class="t"><h1>Connections</h1><span class="cnt tabular">{c.sources.length + c.servers.length + 4}</span></div>
		<p class="lead">Everything the gateway connects to. Set each one up here; no files to edit.</p>
	</div>
	<form method="POST" action="?/testAll" use:enhance={submitting('all')}>
		<button class="pill-btn" disabled={busy !== ''}><Icon name="refresh" size={16} />{busy === 'all' ? 'Testing…' : 'Test all sources'}</button>
	</form>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<section class="gw" aria-label="Gateway">
	<div class="what">
		<strong>City MCP Gateway · running</strong>
		<span>Every read and action goes through here. Secrets stay in {sum.secret_store === 'keyvault' ? 'Azure Key Vault' : 'the dev secret store'}; this page only shows their names.</span>
	</div>
	<div class="chips">
		<span><strong>{sum.servers}</strong> servers</span>
		<span><strong>{sum.tools_on}</strong> of {sum.tools} tools on</span>
		<a href="/admin/tools?show=review" style="text-decoration:none"><span><strong>{sum.changes_to_review}</strong> {sum.changes_to_review === 1 ? 'change' : 'changes'} to review</span></a>
		<span><strong>{sum.calls_today.toLocaleString('en')}</strong> calls today · {sum.blocked_today} blocked</span>
		{#if sum.source_mode === 'mock'}<span>Sample data</span>{/if}
	</div>
</section>

<section class="col" aria-labelledby="in-h" style="gap:12px">
	<div class="hrow"><h2 id="in-h">In · source trackers</h2><span class="sub" style="margin:0">Read-only. Only the nightly sync and admins can call these.</span></div>
	<div class="sources">
		{#each c.sources as s (s.id)}
			{@const failed = s.status === 'failed'}
			<div class="srcc" style="background:{source(s.id).bg}">
				<div class="sh">
					<div class="sn"><span class="n">{s.name}</span><span class="mono tm">/{s.id}/mcp</span></div>
					<span class="state" class:fail={failed}>{failed ? 'Sync failed' : !s.enabled ? 'Off' : s.status === 'ok' ? 'Connected' : 'Not synced yet'}</span>
				</div>
				<ul>
					<li><span class="d"></span>Address <strong>{s.base_url ? s.base_url.replace(/^https:\/\//, '') : 'Not set'}</strong></li>
					<li><span class="d"></span>Secret <strong class="mono" style="font-size:12px">{s.secret_ref || 'Not set'}{s.secret_ref && !s.secret_set ? ' (empty)' : ''}</strong></li>
					{#if failed}
						<li><span class="d"></span>Error <strong class="err">{s.error}</strong></li>
						<li><span class="d"></span>Last good <strong>{s.last_good_sync_at ? `${dayTime(s.last_good_sync_at)} · ${plural(s.projects, 'project')}` : 'never'}</strong></li>
					{:else}
						<li><span class="d"></span>Last sync <strong>{s.last_sync_at ? `${dayTime(s.last_sync_at)} · ${plural(s.projects, 'project')}` : 'never'}</strong></li>
					{/if}
					<li><span class="d"></span>Tools <strong>{s.tools.on} of {s.tools.total} on{s.tools.review ? ` · ${s.tools.review} to review` : ''}</strong></li>
					{#if s.unmapped_statuses.length}
						<li><span class="d"></span>Statuses <strong class="err">{s.unmapped_statuses.length} not mapped</strong></li>
					{/if}
				</ul>
				<div class="btns">
					<form method="POST" action="?/test" use:enhance={submitting(`test-${s.id}`)}>
						<input type="hidden" name="source" value={s.id} />
						<button class="btn" disabled={busy !== ''}>{busy === `test-${s.id}` ? 'Testing…' : 'Test'}</button>
					</form>
					<form method="POST" action="?/sync" use:enhance={submitting(`sync-${s.id}`)}>
						<input type="hidden" name="source" value={s.id} />
						<button class="btn" disabled={busy !== ''}>{busy === `sync-${s.id}` ? 'Syncing…' : 'Sync now'}</button>
					</form>
					<a class="btn dark" href="/admin/connections/{s.id}" style="text-decoration:none">{failed ? 'Fix' : 'Set up'}</a>
				</div>
			</div>
		{/each}
	</div>
</section>

<section class="card col" aria-labelledby="out-h" style="gap:14px">
	<div class="hrow"><h2 id="out-h">Out · app servers</h2><span class="sub" style="margin:0">What the web app, Radar and other agents use.</span><a class="end" href="/admin/tools">Manage tools</a></div>
	<div class="grid3" style="gap:10px">
		{#each c.servers as s (s.server)}
			<a class="srv" class:warn={s.tools.review > 0} href="/admin/tools?server={s.server}">
				<span class="top"><strong class="mono">/{s.server}/mcp</strong><span class="small b">{s.tools.on}/{s.tools.total} on{s.tools.review ? ` · ${s.tools.review} review` : ''}</span></span>
				<span class="small" style="color:#3e4640">{s.description}</span>
			</a>
		{/each}
	</div>
</section>

<section class="col" aria-labelledby="ext-h" style="gap:12px">
	<div class="hrow"><h2 id="ext-h">Outside services</h2><span class="sub" style="margin:0">Sign-in, Radar's words, and sending approved messages.</span></div>
	<div class="grid4c">
		{#each Object.entries(c.services) as [name, s] (name)}
			{@const st = STATUS[(s as any).status] ?? STATUS.not_set}
			<a class="svc" href="/admin/connections/services#{name}">
				<span class="top"><strong style="font-size:15px">{SERVICES[name].title}</strong><span class="tag {st.cls}">{st.label}</span></span>
				<span class="small" style="color:#3e4640">{svcLine(name, s)}</span>
			</a>
		{/each}
	</div>
	<p class="note">Agents such as CityGPT or Claude connect in <a href="/admin/agents"><strong>Agents</strong></a>.</p>
</section>
