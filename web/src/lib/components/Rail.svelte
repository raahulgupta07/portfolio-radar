<script lang="ts">
	// Floating menu, desktop and iPad: white pill, centred vertically on the left.
	import { page } from '$app/state';
	import Icon from './Icon.svelte';
	import RadarFace, { type Mood } from './RadarFace.svelte';

	let {
		radarCount = 0,
		mood = 'ready',
		avg = null,
		initials = '',
		userName = '',
		isAdmin = false
	}: { radarCount?: number; mood?: Mood; avg?: number | null; initials?: string; userName?: string; isAdmin?: boolean } =
		$props();

	const items = $derived([
		{ href: '/', label: 'Portfolio overview', icon: 'home', bg: '#E2F2E7' },
		{ href: '/projects', label: 'Projects', icon: 'projects', bg: '#FBE6A9' },
		{ href: '/roadmap', label: 'Roadmap', icon: 'roadmap', bg: '#CFE3FB' },
		{ href: '/risks', label: 'Risks and strategy', icon: 'risks', bg: '#F8CDD0' },
		...(isAdmin ? [{ href: '/admin', label: 'Admin and agent rules', icon: 'admin', bg: '#F1F5F2' }] : [])
	]);
	const active = (href: string) =>
		href === '/' ? page.url.pathname === '/' : page.url.pathname === href || page.url.pathname.startsWith(href + '/');
	const dash = $derived(avg == null ? 0 : (avg / 100) * 88);
	let menuOpen = $state(false);
</script>

<nav class="rail" aria-label="Main">
	<a href="/radar" aria-label="Radar, your portfolio agent" title="Radar, your portfolio agent" style="background:#E2F2E7" aria-current={active('/radar') ? 'page' : undefined}>
		<RadarFace {mood} size={38} />
		{#if radarCount > 0}<span class="count">{radarCount}</span>{/if}
	</a>
	<span class="sep"></span>
	{#each items as it (it.href)}
		<a
			href={it.href}
			aria-label={it.label}
			title={it.label}
			aria-current={active(it.href) ? 'page' : undefined}
			style={active(it.href) ? 'background:#111111;color:#FFFFFF' : `background:${it.bg}`}
		>
			<Icon name={it.icon} />
		</a>
	{/each}
	<span class="sep"></span>
	<a href="/projects?focus=search" aria-label="Search projects" title="Search" style="background:transparent"><Icon name="search" /></a>
	<a href="/radar" aria-label={`Alerts, ${radarCount} new`} title="Alerts" style="background:transparent">
		<Icon name="bell" />
		{#if radarCount > 0}<span class="dot"></span>{/if}
	</a>
	{#if avg != null}
		<div class="progress" title={`Average progress ${avg}%`}>
			<svg width="34" height="34" viewBox="0 0 36 36" role="img" aria-label={`Average progress ${avg} percent`}>
				<circle cx="18" cy="18" r="14" fill="none" stroke="#E3EAE5" stroke-width="4" />
				<circle cx="18" cy="18" r="14" fill="none" stroke="#111111" stroke-width="4" stroke-linecap="round" stroke-dasharray={`${dash} 88`} transform="rotate(-90 18 18)" />
			</svg>
			<span>{avg}%</span>
		</div>
	{/if}
	<div class="me">
		<button type="button" class="avatar" title={`${userName} · City SSO`} aria-haspopup="true" aria-expanded={menuOpen} onclick={() => (menuOpen = !menuOpen)}>{initials}</button>
		{#if menuOpen}
			<div class="menu" role="menu">
				<p>{userName}</p>
				<form method="POST" action="/logout"><button type="submit" role="menuitem"><Icon name="logout" size={16} /> Sign out</button></form>
			</div>
		{/if}
	</div>
</nav>

<style>
	.rail {
		/* Fixed to the window and centred on its height: never moves when the page scrolls. */
		position: fixed;
		left: 14px;
		top: 50%;
		transform: translateY(-50%);
		max-height: calc(100vh - 28px);
		overflow-y: auto;
		width: 64px;
		background: #fff;
		border-radius: 36px;
		padding: 12px 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		box-shadow: 0 8px 24px rgba(17, 17, 17, 0.06);
		z-index: 20;
	}
	.rail a,
	.avatar {
		width: 44px;
		height: 44px;
		border-radius: 999px;
		border: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: #111;
		position: relative;
		cursor: pointer;
		text-decoration: none;
	}
	.rail a:hover {
		filter: brightness(0.96);
	}
	.sep {
		width: 28px;
		height: 1px;
		background: #e3eae5;
	}
	.count {
		position: absolute;
		top: -2px;
		right: -2px;
		min-width: 18px;
		height: 18px;
		border-radius: 99px;
		background: #d64545;
		color: #fff;
		font-size: 10px;
		font-weight: 800;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 2px solid #fff;
	}
	.dot {
		position: absolute;
		top: 8px;
		right: 9px;
		width: 8px;
		height: 8px;
		border-radius: 99px;
		background: #d64545;
	}
	.progress {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		font-size: 11px;
		font-weight: 800;
	}
	.avatar {
		width: 40px;
		height: 40px;
		background: #111;
		color: #fff;
		font-weight: 800;
		font-size: 13px;
	}
	.me {
		position: relative;
	}
	.menu {
		position: absolute;
		left: 54px;
		bottom: 0;
		background: #fff;
		border-radius: 22px;
		padding: 12px;
		box-shadow: 0 8px 24px rgba(17, 17, 17, 0.12);
		min-width: 200px;
	}
	.menu p {
		margin: 0 0 8px;
		font-size: 13px;
		font-weight: 700;
		padding: 0 8px;
	}
	.menu button {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		min-height: 44px;
		border: 0;
		border-radius: 999px;
		background: #f1f5f2;
		font: 600 14px var(--font-sans);
		padding: 0 14px;
		cursor: pointer;
	}
</style>
