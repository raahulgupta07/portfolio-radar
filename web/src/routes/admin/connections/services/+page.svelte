<script lang="ts">
	import { enhance } from '$app/forms';
	import Icon from '$lib/components/Icon.svelte';

	let { data, form } = $props();
	let ssoProvider = $state('entra');
	$effect(() => {
		ssoProvider = data.i.services.sso.config.provider ?? 'entra';
	});
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
		<p class="sub" style="margin:0;color:#33404f">
			People sign in with their City account; their groups decide their roles. Microsoft Entra ID, or Keycloak
			(which can check passwords against LDAP or Active Directory and pass on the groups). Exceptions per person: <a href="/admin/people">People</a>.
		</p>
		<form class="form" method="POST" action="?/saveSso" use:enhance={submitting('sso')}>
			<div class="lab">Provider
				<div class="seg2" role="radiogroup" aria-label="SSO provider" style="background:#fff">
					<label><input type="radio" name="provider" value="entra" bind:group={ssoProvider} />Entra ID</label>
					<label><input type="radio" name="provider" value="keycloak" bind:group={ssoProvider} />Keycloak / LDAP</label>
				</div>
			</div>
			{#if ssoProvider === 'keycloak'}
				<label class="lab">Realm address (issuer)<input class="inp mono" name="issuer" value={sso.issuer ?? ''} placeholder="https://sso.city.local/realms/city" /></label>
				<label class="lab">Internal address (optional)<input class="inp mono" name="internal_url" value={sso.internal_url ?? ''} placeholder="http://keycloak:8080/realms/city" />
					<span class="hint">Only if the gateway reaches Keycloak by another name than people do, e.g. inside Docker.</span></label>
			{:else}
				<label class="lab">Tenant ID<input class="inp mono" name="tenant_id" value={sso.tenant_id} placeholder="00000000-0000-0000-0000-000000000000" /></label>
			{/if}
			<label class="lab">Gateway audience<input class="inp mono" name="audience" value={sso.audience} placeholder={ssoProvider === 'keycloak' ? 'portfolio-radar-gateway' : 'api://city-mcp-gateway'} /></label>
			<label class="lab">Sign-in apps (client IDs, besides the web app's)<input class="inp mono" name="user_apps" value={(sso.user_apps ?? []).join(', ')} placeholder={ssoProvider === 'keycloak' ? 'portfolio-radar-web' : 'Web app client ID'} /></label>
			<div class="lab">Groups → roles
				{#each [...sso.groups, { group_id: '', name: '', roles: ['viewer'] }] as g, i (i)}
					<div class="secret" style="gap:6px">
						<input class="inp" style="flex:1 1 120px;min-height:36px" name="group_name" value={g.name} placeholder="Name, e.g. PMO" aria-label="Group name" />
						<input class="inp mono" style="flex:2 1 200px;min-height:36px" name="group_id" value={g.group_id}
							placeholder={ssoProvider === 'keycloak' ? 'Group or role, e.g. /portfolio-pmo' : 'Group object ID'} aria-label="Group" />
						<select class="inp" style="flex:0 0 110px;min-height:36px" name="group_role" aria-label="Role">
							{#each ROLES as r (r)}<option value={r} selected={g.roles[0] === r}>{r}</option>{/each}
						</select>
					</div>
				{/each}
				<label class="confirm" style="font-weight:500"><input type="checkbox" name="default_viewer" checked={(sso.default_roles ?? ['viewer']).includes('viewer')} /> Everyone who signs in is a viewer</label>
				<span class="hint">At least one group must be admin.{ssoProvider === 'keycloak' ? ' Keycloak sends groups in the "groups" claim (group membership mapper) and realm roles; LDAP groups come through its LDAP group mapper.' : ''}</span>
			</div>
			<div class="btns"><button class="btn dark" disabled={busy !== ''}>Save SSO</button></div>
		</form>
		{@render testBtn('sso', ssoProvider === 'keycloak' ? 'Check realm' : 'Check tenant')}
		<div class="ro" style="flex-direction:column;align-items:flex-start;gap:4px">
			<span>Web app sign-in (settings of the web container)</span>
			<span class="mono" style="font-weight:500">
				{data.web.provider === 'keycloak' ? `OIDC_ISSUER = ${data.web.issuer}` : data.web.provider === 'entra' ? 'Entra ID' : 'SSO not set'} ·
				client {data.web.client_id || 'not set'} · secret {data.web.secret_set ? 'set' : 'not set'}
			</span>
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
				<div class="hrow" style="margin-top:6px">
					<h3 style="margin:0;font-size:15px">Chat with Radar in Teams</h3>
					<span class="st st-{sv.teams.bot_status === 'ready' ? 'on' : sv.teams.bot_status === 'secret_missing' ? 'review' : 'off'}" style="margin-left:auto">
						{sv.teams.bot_status === 'ready' ? 'ready' : sv.teams.bot_status === 'secret_missing' ? 'secret missing' : 'off'}
					</span>
				</div>
				<p class="sub" style="margin:0">
					People message Radar in a 1:1 chat and get answers there. Radar answers only the person who asked; digests still need approval.
					Needs an Azure Bot whose messaging endpoint is <span class="mono">{data.teamsEndpoint}</span>.
				</p>
				<label class="lab">Bot app ID<input class="inp mono" name="bot_app_id" value={teams.bot_app_id} placeholder="00000000-0000-0000-0000-000000000000" pattern="[0-9a-fA-F\-]{'{36}'}" autocomplete="off" /></label>
				{@render secretField('Bot client secret', 'bot_password_ref', teams.bot_password_ref, sv.teams.bot_status === 'ready', 'bot_password', 'Paste the client secret', 'kv://teams-bot-password')}
				<div class="btns"><button class="btn dark" disabled={busy !== ''}>Save</button></div>
			</form>
			{@render testBtn('teams', 'Test webhook and bot')}
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

		<div class="gw" style="display:block;padding:16px 20px;font-size:13px;line-height:1.5">Nothing is sent until a named approver says yes. Teams and email get approved drafts only, through <span class="mono">/notify/mcp</span>. The one exception is chat: Radar's answer goes back to the person who asked, in the same 1:1 chat, as in the app.</div>
	</div>
</div>

<style>
	.confirm { display: flex; gap: 8px; align-items: center; }
</style>
