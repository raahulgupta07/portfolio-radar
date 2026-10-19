<script lang="ts">
	import { page } from '$app/state';
	import '$lib/admin.css';

	let { children } = $props();
	const tabs = [
		{ href: '/admin', label: 'Settings' },
		{ href: '/admin/connections', label: 'Connections' },
		{ href: '/admin/tools', label: 'MCP tools' },
		{ href: '/admin/agents', label: 'Agents' },
		{ href: '/admin/activity', label: 'Activity' }
	];
	const current = (href: string) =>
		href === '/admin' ? page.url.pathname === '/admin' : page.url.pathname === href || page.url.pathname.startsWith(href + '/');
</script>

<div class="adm adm-wrap">
	<nav class="adm-tabs" aria-label="Admin">
		{#each tabs as t (t.href)}
			<a href={t.href} aria-current={current(t.href) ? 'page' : undefined}>{t.label}</a>
		{/each}
	</nav>
	{@render children()}
</div>
