<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/components/Icon.svelte';

	let { data, form } = $props();
	let busy = $state('');
	const sv = $derived(data.i.services);
	const sso = $derived(sv.sso.config);
	const llm = $derived(sv.llm.config);
	const teams = $derived(sv.teams.config);
	const email = $derived(sv.email.config);
	const store = $derived(data.i.secret_store === 'keyvault' ? 'Azure Key Vault' : 'the dev secret store');
	const STATUS: Record<string, { label: string; cls: string }> = {
		ready: { label: 'Connected', cls: 'ok' },
		not_set: { label: 'Not set up', cls: 'warn' },
		rules_only: { label: 'Rules only', cls: 'warn' },
		secret_missing: { label: 'Secret missing', cls: 'bad' }
	};
	const PROVIDERS = [
		{ id: 'citygpt', label: 'CityGPT' },
		{ id: 'azure_openai', label: 'Azure OpenAI' },
		{ id: 'claude', label: 'Claude' },
		{ id: 'other', label: 'Other' }
	];
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update, result, formElement }: { update: (o?: { reset?: boolean }) => Promise<void>; result: { type: string }; formElement: HTMLFormElement }) => {
			await update({ reset: false });
			// A pasted secret is gone from the page once it is saved.
			if (result.type === 'success') formElement.querySelectorAll<HTMLInputElement>('input[type=password]').forEach((i) => (i.value = ''));
			busy = '';
		};
	};
	const ROLES = ['viewer', 'approver', 'admin'];
</script>

<svelte:head><title>Sign-in, LLM and sending · Admin · Portfolio Radar</title></svelte:head>

{#snippet status(name: string)}
	{@const st = STATUS[sv[name].status] ?? STATUS.not_set}
	<span class="tag {st.cls} end">{st.label}{sv[name].saved_in_admin ? '' : ' · from environment'}</span>
{/snippet}

{#snippet secretField(label: string, refName: string, refValue: string, isSet: boolean, valueName: string, placeholder: string, fallback: string)}
	<div class="lab">{label}
		<div class="secret">
			<span class="name mono"><Icon name="lock" size={14} />{refValue || 'none yet'}</span>
			{#if refValue}<span class="tag {isSet ? 'ok' : 'warn'}">{isSet ? 'Set' : 'Empty'}</span>{/if}
		</div>
		<input class="inp" type="password" name={valueName} autocomplete="new-password" placeholder={refValue && isSet ? 'Paste a new value to replace it' : placeholder} />
		<input type="hidden" name={refName} value={refValue} />
		<span class="hint">Pasted once, saved in {store} as <span class="mono">{refValue || fallback}</span>. Never shown again.</span>
	</div>
{/snippet}

{#snippet testBtn(name: string, label: string)}
	<form method="POST" action="?/test" use:enhance={submitting(`test-${name}`)}>
		<input type="hidden" name="name" value={name} />
		<button class="btn quiet" disabled={busy !== ''}>{busy === `test-${name}` ? 'Testing…' : label}</button>
	</form>
{/snippet}

<a class="crumb" href="/admin/connections"><Icon name="back" size={14} />Connections</a>
<section class="title-row">
	<div>
		<h1>Sign-in, LLM and sending</h1>
		<p class="lead">Outside services the gateway uses. Secrets go to {store}; you see only their names.</p>
	</div>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<div class="grid3" style="align-items:start">
	<section class="card col" id="sso" style="background:#cfe3fb" aria-labelledby="sso-h">
		<div class="hrow"><h2 id="sso-h">City SSO</h2>{@render status('sso')}</div>
		<p class="sub" style="margin:0;color:#33404f">Microsoft Entra ID. People sign in with their City account; their groups decide their roles.</p>
		<form class="form" method="POST" action="?/saveSso" use:enhance={submitting('sso')}>
			<label class="lab">Tenant ID<input class="inp mono" name="tenant_id" value={sso.tenant_id} placeholder="00000000-0000-0000-0000-000000000000" /></label>
			<label class="lab">Gateway audience<input class="inp mono" name="audience" value={sso.audience} placeholder="api://city-mcp-gateway" /></label>
			<div class="lab">Groups → roles
				{#each [...sso.groups, { group_id: '', name: '', roles: ['viewer'] }] as g, i (i)}
					<div class="secret" style="gap:6px">
						<input class="inp" style="flex:1 1 120px;min-height:36px" name="group_name" value={g.name} placeholder="Name, e.g. PMO" aria-label="Group name" />
						<input class="inp mono" style="flex:2 1 200px;min-height:36px" name="group_id" value={g.group_id} placeholder="Group object ID" aria-label="Group object ID" />
						<select class="inp" style="flex:0 0 110px;min-height:36px" name="group_role" aria-label="Role">
							{#each ROLES as r (r)}<option value={r} selected={g.roles[0] === r}>{r}</option>{/each}
						</select>
					</div>
				{/each}
				<span class="hint">Every signed-in employee is a viewer. At least one group must be admin.</span>
			</div>
			<div class="btns"><button class="btn dark" disabled={busy !== ''}>Save SSO</button></div>
		</form>
		{@render testBtn('sso', 'Check tenant')}
		<div class="ro" style="flex-direction:column;align-items:flex-start;gap:4px">
			<span>Web app sign-in (settings of the web container)</span>
			<span class="mono" style="font-weight:500">ENTRA_CLIENT_ID {data.web.client_id ? `= ${data.web.client_id}` : 'not set'} · secret {data.web.secret_set ? 'set' : 'not set'}</span>
			{#if data.web.dev_login}<span style="font-weight:500">Sample-user sign-in is on (DEV_LOGIN). Turn it off in production.</span>{/if}
		</div>
	</section>

	<section class="card col" id="llm" aria-labelledby="llm-h">
		<div class="hrow"><h2 id="llm-h">LLM for Radar</h2>{@render status('llm')}</div>
		<p class="sub" style="margin:0">Radar writes summaries and answers with this. Empty: Radar answers from rules, with evidence.</p>
		<form class="form" method="POST" action="?/saveLlm" use:enhance={submitting('llm')}>
			<div class="lab">Provider
				<div class="seg2" role="radiogroup" aria-label="Provider" style="background:#f1f5f2">
					{#each PROVIDERS as p (p.id)}<label><input type="radio" name="provider" value={p.id} checked={llm.provider === p.id} />{p.label}</label>{/each}
				</div>
			</div>
			<label class="lab">Address (OpenAI-compatible)<input class="inp mono" name="base_url" type="url" value={llm.base_url} placeholder="https://citygpt.city.local/v1" /></label>
			<label class="lab">Model<input class="inp mono" name="model" value={llm.model} placeholder="Model or deployment name" /></label>
			{@render secretField('API key', 'api_key_ref', llm.api_key_ref, !!sv.llm.secret_set, 'api_key', 'Paste the API key', 'kv://llm-api-key')}
			<div class="note small">Tracker text goes to the LLM as data, never as instructions. Health is always decided by rules.</div>
			<div class="btns">
				<button class="btn dark" disabled={busy !== ''}>Save LLM</button>
				<button class="btn quiet" name="rules_only" value="true" disabled={busy !== ''}>Use rules only</button>
			</div>
		</form>
		{@render testBtn('llm', 'Test with one question')}
	</section>

	<div class="side">
		<section class="card col" id="teams" aria-labelledby="teams-h">
			<div class="hrow"><h2 id="teams-h">Microsoft Teams</h2>{@render status('teams')}</div>
			<form class="form" method="POST" action="?/saveTeams" use:enhance={submitting('teams')}>
				{@render secretField('Incoming webhook URL', 'webhook_ref', teams.webhook_ref, !!sv.teams.secret_set, 'webhook', 'Paste the webhook URL', 'kv://teams-webhook')}
				<label class="lab">Channel name (for people)<input class="inp" name="channel" value={teams.channel} placeholder="#steerco-portfolio" /></label>
				<div class="btns"><button class="btn dark" disabled={busy !== ''}>Save</button></div>
			</form>
			{@render testBtn('teams', 'Send a test message')}
		</section>

		<section class="card col" id="email" aria-labelledby="email-h">
			<div class="hrow"><h2 id="email-h">Email</h2>{@render status('email')}</div>
			<form class="form" method="POST" action="?/saveEmail" use:enhance={submitting('email')}>
				<div class="fgrid" style="grid-template-columns:minmax(0,1fr) 90px">
					<label class="lab">SMTP server<input class="inp" name="smtp_host" value={email.smtp_host} placeholder="smtp.office365.com" /></label>
					<label class="lab">Port<input class="inp" name="smtp_port" type="number" min="1" max="65535" value={email.smtp_port} /></label>
				</div>
				<label class="lab">User<input class="inp" name="username" value={email.username} autocomplete="off" /></label>
				{@render secretField('Password', 'password_ref', email.password_ref, !!sv.email.secret_set, 'password', 'Paste the password', 'kv://smtp-password')}
				<label class="lab">From<input class="inp" name="sender" value={email.sender} /></label>
				<label class="lab">Weekly digest to<textarea class="inp" style="padding:10px 14px;min-height:64px" name="recipients" placeholder="steerco@…, pmo@…" value={email.recipients.join(', ')}></textarea></label>
				<div class="btns"><button class="btn dark" disabled={busy !== ''}>Save</button></div>
			</form>
			{@render testBtn('email', 'Send a test email to me')}
		</section>

		<div class="gw" style="display:block;padding:16px 20px;font-size:13px;line-height:1.5">Nothing is sent until a named approver says yes. Teams and email get approved drafts only, through <span class="mono">/notify/mcp</span>.</div>
	</div>
</div>
