<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { dayTime } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	let copied = $state(false);
	const editId = $derived(page.url.searchParams.get('edit'));
	const editing = $derived(editId ? data.agents.find((a: any) => String(a.id) === editId) : null);
	const showForm = $derived(!!editing || page.url.searchParams.has('new') || data.agents.length === 0);
	let kind = $state('agent');
	$effect(() => {
		kind = editing?.kind ?? 'agent';
	});
	const savedId = $derived(form && 'saved' in form ? (form as any).saved : null);
	const preview = $derived(form && 'preview' in form ? (form as any).preview : null);
	const target = $derived(data.agents.find((a: any) => a.id === savedId) ?? editing);
	const snippet = $derived(
		JSON.stringify(
			{ mcpServers: { 'city-portfolio': { type: 'http', url: `${data.publicUrl}/omni/mcp`, headers: { Authorization: 'Bearer <Entra access token>' } } } },
			null,
			2
		)
	);
	const scope = $derived(data.audience ? `${data.audience}/.default` : '<gateway audience>/.default');
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update({ reset: false });
			busy = '';
		};
	};
	async function copy() {
		await navigator.clipboard.writeText(snippet);
		copied = true;
		setTimeout(() => (copied = false), 1500);
	}
</script>

<svelte:head><title>Agents · Admin · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div>
		<div class="t"><h1>Agents</h1><span class="cnt tabular">{data.agents.length + data.built_in.length}</span></div>
		<p class="lead">Let CityGPT, Claude or another City agent use the portfolio through MCP. Agents read and draft; they never approve or send.</p>
	</div>
	<a class="pill-btn primary" href="?new" style="text-decoration:none">+ Connect an agent</a>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<div class="split" style="grid-template-columns:minmax(0,1fr) minmax(0,1.25fr)">
	<section class="card col" aria-labelledby="list-h">
		<div class="hrow"><h2 id="list-h">Connected agents</h2></div>
		<ul class="col" style="gap:8px">
			{#each data.agents as a (a.id)}
				<li class="agent mine" class:offline={!a.enabled}>
					<span class="top">
						<strong style="font-size:15px">{a.name}</strong><span class="tag" style="background:#fff">{a.kind}</span>
						{#if !a.enabled}<span class="tag dark">Off</span>{/if}
						<span class="small" style="margin-left:auto;color:#3e4640">{a.calls_today} calls today</span>
					</span>
					<span class="small" style="color:#3e4640">Entra app <span class="mono">{a.app_id.slice(0, 8)}…</span> · <span class="mono">{a.servers.map((s: string) => '/' + s).join(' ')}</span> · {a.rate_limit}/min</span>
					<div class="btns">
						<a class="mini" href="?edit={a.id}" style="display:inline-flex;align-items:center;text-decoration:none">Change</a>
						<form method="POST" action="?/preview" use:enhance={submitting(`pv-${a.id}`)}><input type="hidden" name="id" value={a.id} /><button class="mini" disabled={busy !== ''}>Test as this agent</button></form>
						<form method="POST" action="?/enable" use:enhance={submitting(`en-${a.id}`)}>
							<input type="hidden" name="id" value={a.id} /><input type="hidden" name="enabled" value={String(!a.enabled)} />
							<button class="mini" disabled={busy !== ''}>{a.enabled ? 'Turn off' : 'Turn on'}</button>
						</form>
					</div>
				</li>
			{/each}
			{#each data.built_in as b (b.caller_id)}
				<li class="agent">
					<span class="top">
						<strong style="font-size:15px">{b.name}</strong><span class="tag" style="background:#fff">{b.kind}</span><span class="tag ok">Built in</span>
						<span class="small" style="margin-left:auto;color:#3e4640">{b.calls_today} calls today</span>
					</span>
					<span class="small" style="color:#3e4640">{b.what} · <span class="mono">{b.servers.map((s: string) => '/' + s).join(' ')}</span>{b.last_call_at ? ` · last ${dayTime(b.last_call_at)}` : ''}</span>
				</li>
			{/each}
		</ul>
		<p class="note small">Agents can read and draft. They can never approve or send: that rule is in the gateway, not in the agent.</p>
	</section>

	<div class="side">
		{#if showForm}
			<section class="card col" style="background:#cfe3fb" aria-labelledby="form-h">
				<div class="hrow"><h2 id="form-h">{editing ? `Change ${editing.name}` : 'Connect an agent'}</h2></div>
				<form class="form" method="POST" action="?/save" use:enhance={submitting('save')}>
					{#if editing}<input type="hidden" name="id" value={editing.id} />{/if}
					<div class="fgrid">
						<label class="lab">Name<input class="inp" name="name" required minlength="2" value={editing?.name ?? ''} placeholder="Claude for PMO" /></label>
						<div class="lab">Kind
							<div class="seg2" role="radiogroup" aria-label="Kind">
								<label><input type="radio" name="kind" value="agent" bind:group={kind} />Agent</label>
								<label><input type="radio" name="kind" value="service" bind:group={kind} />Service</label>
							</div>
						</div>
					</div>
					<label class="lab">Entra app (client) ID
						<input class="inp mono" name="app_id" required value={editing?.app_id ?? ''} placeholder="00000000-0000-0000-0000-000000000000" pattern="[0-9a-fA-F\-]{'{36}'}" />
						<span class="hint">The agent signs in with its own City app registration. No shared keys.</span>
					</label>
					{#if kind === 'service'}
						<div class="lab">Role
							<div class="seg2" style="background:#fff">
								{#each data.roles.service as r (r)}<label><input type="checkbox" name="roles" value={r} checked={editing?.roles.includes(r)} />{r}</label>{/each}
							</div>
						</div>
					{/if}
					<div class="lab"><span>What it can use (through <span class="mono">/omni</span> or directly)</span>
						<ul class="checks" style="background:#fff;border-radius:18px;padding:12px 16px">
							{#each data.servers as s (s.server)}
								<li>
									<label style="display:flex;gap:10px;align-items:center;width:100%">
										<input type="checkbox" name="servers" value={s.server} checked={editing ? editing.servers.includes(s.server) : s.server === 'portfolio'} />
										<span class="mono b">/{s.server}</span><span class="muted small">{s.title}</span>
									</label>
								</li>
							{/each}
						</ul>
						<span class="hint">Omni and system are always there. The tool rules still apply: an agent never gets admin, approve or send tools.</span>
					</div>
					<div class="fgrid">
						<label class="lab">Rate limit (calls per minute)<input class="inp" type="number" name="rate_limit" min="1" max="2000" value={editing?.rate_limit ?? 120} /></label>
						<div class="lab">Personal data<span class="secret" style="min-height:44px">Emails and phone numbers removed</span></div>
					</div>
					<div class="btns"><button class="btn dark" disabled={busy !== ''}>{busy === 'save' ? 'Saving…' : 'Save and test'}</button>{#if editing}<a class="btn" href="/admin/agents" style="text-decoration:none">Cancel</a>{/if}</div>
				</form>
			</section>
		{/if}

		<section class="card col" aria-labelledby="addr-h">
			<div class="hrow"><h2 id="addr-h">Give the agent its address</h2></div>
			<p style="margin:0;font-size:13px">One URL for every agent. <span class="mono">/omni</span> lists only the tools that agent may use.</p>
			<pre class="code">{snippet}</pre>
			<p class="small muted" style="margin:0">The agent gets its token from Entra ID with client credentials, scope <span class="mono">{scope}</span>{data.tenant ? '' : ' (set up City SSO first)'}.</p>
			<div class="btns"><button class="btn quiet" type="button" onclick={copy}>{copied ? 'Copied' : 'Copy'}</button></div>
			{#if preview}
				<div class="col" style="gap:8px">
					<strong style="font-size:14px">What {target?.name ?? preview.caller_id} sees now · {preview.tool_count} tools</strong>
					<ul class="checks">
						{#each preview.servers as s (s.server)}
							<li style="align-items:flex-start"><span class="ic">✓</span><span><span class="mono b">/{s.server}</span> <span class="small muted">{s.tools.join(', ')}</span></span></li>
						{/each}
						{#each preview.never_allowed as t (t)}
							<li><span class="ic">✓</span><span><span class="mono">{t}</span> is hidden from this agent</span></li>
						{/each}
					</ul>
				</div>
			{/if}
		</section>
	</div>
</div>
