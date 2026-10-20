<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { dayTime } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	const ROLES = ['viewer', 'approver', 'admin'];
	const editId = $derived(page.url.searchParams.get('edit'));
	const editing = $derived(editId ? data.people.find((p: any) => p.id === editId) : null);
	const showForm = $derived(!!editing || page.url.searchParams.has('new'));
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update({ reset: false });
			busy = '';
		};
	};
	const provider = $derived(data.sso.provider === 'keycloak' ? 'Keycloak (LDAP)' : 'Entra ID');
</script>

<svelte:head><title>People · Admin · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div>
		<div class="t"><h1>People</h1><span class="cnt tabular">{data.people.length}</span></div>
		<p class="lead">
			Who can sign in and what they may do. Roles come from their groups in {provider}
			(set under <a href="/admin/connections/services#sso">Connections → City SSO</a>). Here you can add a role or block someone, at once.
		</p>
	</div>
	<a class="pill-btn primary" href="?new" style="text-decoration:none">+ Add a person</a>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

{#if showForm}
	<section class="card col" aria-labelledby="f-h">
		<div class="hrow"><h2 id="f-h">{editing ? `Change ${editing.name || editing.id}` : 'Add a person'}</h2><a class="mini" href="/admin/people" style="margin-left:auto;text-decoration:none;background:#f1f5f2">Close</a></div>
		<form class="form" method="POST" action="?/save" use:enhance={submitting('save')}>
			<div class="fgrid">
				<label class="lab">Account (as SSO gives it)
					<input class="inp mono" name="id" required value={editing?.id ?? ''} readonly={!!editing} placeholder="aye.aye@cityholdings.com.mm" autocomplete="off" />
				</label>
				<label class="lab">Name<input class="inp" name="name" value={editing?.name ?? ''} placeholder="Aye Aye" /></label>
			</div>
			<div class="lab">Roles added here (on top of SSO groups)
				<div class="seg2" role="group" aria-label="Extra roles" style="background:#f1f5f2">
					{#each ROLES as r (r)}<label><input type="checkbox" name="extra_roles" value={r} checked={editing?.extra_roles.includes(r)} />{r}</label>{/each}
				</div>
				{#if editing}<span class="hint">From SSO groups: {editing.sso_roles.length ? editing.sso_roles.join(', ') : 'none'}.</span>{/if}
			</div>
			<label class="lab">Note for other admins<input class="inp" name="note" value={editing?.note ?? ''} placeholder="Why, e.g. PMO cover until 30 Nov" maxlength="300" /></label>
			{#if editing?.id !== data.me}
				<label class="confirm"><input type="checkbox" name="blocked" checked={editing?.blocked} /> Block this person. Every call is refused, even with a valid SSO sign-in.</label>
			{/if}
			<div class="btns"><button class="btn dark" disabled={busy !== ''}>{busy === 'save' ? 'Saving…' : 'Save'}</button></div>
		</form>
	</section>
{/if}

<section class="card col">
	<div class="filters">
		<form method="GET" style="display:flex;gap:8px;width:100%">
			<label style="flex:1"><span class="sr-only">Search people</span><input class="field" style="min-height:36px;width:100%" name="q" value={data.q} placeholder="Search name or account" /></label>
			<button class="mini" style="background:#f1f5f2">Search</button>
		</form>
	</div>
	<div class="scroll">
		<table>
			<thead><tr><th scope="col">Person</th><th scope="col">Roles</th><th scope="col">Last sign-in</th><th scope="col">Status</th><th scope="col"><span class="sr-only">Change</span></th></tr></thead>
			<tbody>
				{#each data.people as p (p.id)}
					<tr>
						<td><span class="b">{p.name || p.id}</span>{#if p.name}<br /><span class="mono muted" style="font-size:12px">{p.id}</span>{/if}{#if p.note}<br /><span class="muted" style="font-size:12px">{p.note}</span>{/if}</td>
						<td>
							{#each p.sso_roles as r (r)}<span class="tag">{r}</span> {/each}
							{#each p.extra_roles.filter((r: string) => !p.sso_roles.includes(r)) as r (r)}<span class="tag" style="background:#fbe6a9" title="Added in Admin">+{r}</span> {/each}
							{#if !p.roles.length}<span class="muted">none</span>{/if}
						</td>
						<td class="nowrap">{p.last_seen ? dayTime(p.last_seen) : 'not yet'}</td>
						<td>{#if p.blocked}<span class="res fail">blocked</span>{:else}<span class="res">active</span>{/if}</td>
						<td><a class="mini" href={`?edit=${encodeURIComponent(p.id)}`} style="text-decoration:none;background:#f1f5f2">Change</a></td>
					</tr>
				{:else}
					<tr><td colspan="5" class="muted">Nobody has signed in yet. People appear here after their first sign-in.</td></tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="sub" style="margin:0">To give a whole team a role, map their group under City SSO instead. Use this page for exceptions.</p>
</section>

<style>
	.confirm { display: flex; gap: 10px; align-items: center; }
</style>
