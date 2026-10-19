<script lang="ts">
	import { enhance } from '$app/forms';
	import { page } from '$app/state';
	import { dayTime } from '$lib/format';

	let { data, form } = $props();
	let busy = $state('');
	let q = $state('');
	type Tool = { server: string; tool: string; status: string; callers: string[]; roles: string[]; read_only: boolean; description: string; changed_by: string | null };
	const show = $derived(page.url.searchParams.get('show') ?? 'all');
	const only = $derived(page.url.searchParams.get('server'));
	const all = $derived(data.tools as Tool[]);
	const count = (s: string) => all.filter((t) => t.status === s).length;
	const filters = $derived([
		{ id: 'all', label: `All ${all.length}` },
		{ id: 'on', label: `On ${count('on')}` },
		{ id: 'off', label: `Off ${count('off')}` },
		{ id: 'review', label: `Review ${count('review')}` }
	]);
	const byServer = $derived.by(() => {
		const acc: Record<string, Tool[]> = {};
		const needle = q.trim().toLowerCase();
		for (const t of all) {
			if (show !== 'all' && t.status !== show) continue;
			if (only && t.server !== only) continue;
			if (needle && !`${t.server}.${t.tool} ${t.description}`.toLowerCase().includes(needle)) continue;
			(acc[t.server] ??= []).push(t);
		}
		return Object.entries(acc);
	});
	const href = (id: string) => `?show=${id}${only ? `&server=${only}` : ''}`;
	const submitting = (name: string) => () => {
		busy = name;
		return async ({ update }: { update: (o?: { reset?: boolean }) => Promise<void> }) => {
			await update({ reset: false });
			busy = '';
		};
	};
	const who = (t: Tool) => `${t.callers.join(' · ')}${t.roles.length ? ` — ${t.roles.join(', ')}` : ''}`;
	const show1 = (v: unknown) => (typeof v === 'string' ? v : JSON.stringify(v));
</script>

<svelte:head><title>MCP tools · Admin · Portfolio Radar</title></svelte:head>

<section class="title-row">
	<div>
		<div class="t"><h1>MCP tools</h1><span class="cnt tabular">{all.length}</span></div>
		<p class="lead">Turn tools on or off, see who can call them, and review changes. New tools start off.</p>
	</div>
</section>

{#if form?.message}
	<p class="flash" class:bad={!form.ok} role="status">{form.message}</p>
{/if}

<div class="split">
	<section class="card col" aria-labelledby="tools-h">
		<div class="hrow"><h2 id="tools-h">Tools by server</h2>{#if only}<a class="end" href="?show={show}">Show all servers</a>{/if}</div>
		<div class="filters">
			{#each filters as f (f.id)}<a href={href(f.id)} aria-current={show === f.id ? 'true' : undefined}>{f.label}</a>{/each}
			<label style="margin-left:auto"><span class="sr-only">Search tools</span><input class="field" style="min-height:36px" bind:value={q} placeholder="Search tools…" /></label>
		</div>
		<div class="tools">
			{#each byServer as [server, tools] (server)}
				<details open={!!only || show !== 'all' || !!q || byServer.length <= 2}>
					<summary>
						<span class="b mono">/{server}/mcp</span>
						<span class="muted">{tools.filter((t) => t.status === 'on').length} of {tools.length} on</span>
					</summary>
					<div class="btns" style="padding-bottom:10px">
						<form method="POST" action="?/serverStatus" use:enhance={submitting(`srv-${server}`)}>
							<input type="hidden" name="server" value={server} /><input type="hidden" name="status" value="on" />
							<button class="mini" disabled={busy !== ''}>Turn all on</button>
						</form>
						<form method="POST" action="?/serverStatus" use:enhance={submitting(`srv-${server}`)}>
							<input type="hidden" name="server" value={server} /><input type="hidden" name="status" value="off" />
							<button class="mini" disabled={busy !== ''}>Turn all off</button>
						</form>
					</div>
					<ul>
						{#each tools as t (t.tool)}
							<li style={t.status === 'review' ? 'background:#fbe6a9' : ''}>
								<div class="tn">
									<span class="b mono">{t.tool}</span>
									<span class="muted small">{who(t)}{t.read_only ? ' · read-only' : ' · changes our own data'}</span>
								</div>
								<span class="st st-{t.status}">{t.status}</span>
								{#if t.status !== 'review'}
									<form method="POST" action="?/toolStatus" use:enhance={submitting(`tool-${server}-${t.tool}`)}>
										<input type="hidden" name="server" value={server} /><input type="hidden" name="tool" value={t.tool} />
										<input type="hidden" name="status" value={t.status === 'on' ? 'off' : 'on'} />
										<button class="mini" disabled={busy !== ''} aria-label="{t.status === 'on' ? 'Turn off' : 'Turn on'} {server}.{t.tool}">{t.status === 'on' ? 'Turn off' : 'Turn on'}</button>
									</form>
								{/if}
							</li>
						{/each}
					</ul>
				</details>
			{:else}
				<p class="muted">No tools match.</p>
			{/each}
		</div>
	</section>

	<div class="side">
		<section class="card col" style="background:#fbe6a9" aria-labelledby="rev-h">
			<div class="hrow"><h2 id="rev-h">Changes to review</h2><span class="tag end" style="background:#fff">{data.changes.length} waiting</span></div>
			{#each data.changes as c (c.id)}
				<div class="col" style="gap:10px">
					<p style="margin:0;font-size:13px">The code for <strong class="mono">{c.server}.{c.tool}</strong> changed. It stays off until its owner approves.</p>
					<pre class="code">{#each Object.entries(c.diff) as [field, d] (field)}<span style="color:#c9cfcb">{field}</span>
<span style="color:#f59a9a">- {show1((d as any).old)}</span>
<span style="color:#8fd6a8">+ {show1((d as any).new)}</span>
{/each}</pre>
					<p class="small muted" style="margin:0">Found {dayTime(c.created_at)}</p>
					<div class="btns">
						<form method="POST" action="?/decideChange" use:enhance={submitting(`chg-${c.id}`)}><input type="hidden" name="change_id" value={c.id} /><input type="hidden" name="approve" value="true" /><button class="btn dark" disabled={busy !== ''}>Approve and turn on</button></form>
						<form method="POST" action="?/decideChange" use:enhance={submitting(`chg-${c.id}`)}><input type="hidden" name="change_id" value={c.id} /><input type="hidden" name="approve" value="false" /><button class="btn" disabled={busy !== ''}>Reject</button></form>
					</div>
				</div>
			{:else}
				<p style="margin:0;font-size:13px">Nothing to review. When a tool's description, inputs or access rules change in code, it waits here.</p>
			{/each}
		</section>

		<section class="card col" aria-labelledby="calls-h">
			<div class="hrow"><h2 id="calls-h">Latest calls</h2><a class="end" href="/admin/activity">Open the audit log</a></div>
			<ul class="checks">
				{#each data.audit as a, i (i)}
					<li style="align-items:flex-start">
						<span class="small muted" style="min-width:86px">{dayTime(a.at)}</span>
						<span class="small"><strong>{a.caller}</strong><br /><span class="mono">{a.server}.{a.tool}</span></span>
						<span class="res" class:fail={a.outcome !== 'ok'} style="margin-left:auto">{a.outcome === 'denied' ? 'blocked' : a.outcome}</span>
					</li>
				{/each}
			</ul>
		</section>
	</div>
</div>
