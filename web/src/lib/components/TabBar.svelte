<script lang="ts">
	// Phone: floating white tab bar at the bottom (Radar, Overview, Projects, Alerts, avatar).
	import { page } from '$app/state';
	import Icon from './Icon.svelte';
	import RadarFace, { type Mood } from './RadarFace.svelte';

	let { radarCount = 0, mood = 'ready', initials = '' }: { radarCount?: number; mood?: Mood; initials?: string } =
		$props();
	const at = (href: string) => (href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href));
</script>

<nav class="tabbar" aria-label="Main">
	<a href="/radar" aria-current={at('/radar') ? 'page' : undefined}>
		<span class="face"><RadarFace {mood} size={28} /></span>
		<span>Radar</span>
		{#if radarCount > 0}<b class="count">{radarCount}</b>{/if}
	</a>
	<a href="/" aria-current={at('/') ? 'page' : undefined}><Icon name="home" /><span>Overview</span></a>
	<a href="/projects" aria-current={at('/projects') ? 'page' : undefined}><Icon name="projects" /><span>Projects</span></a>
	<a href="/risks" aria-current={at('/risks') ? 'page' : undefined}><Icon name="risks" /><span>Risks</span></a>
	<a href="/account" aria-label="Account"><span class="avatar">{initials}</span></a>
</nav>

<style>
	.tabbar {
		position: fixed;
		left: max(12px, env(safe-area-inset-left));
		right: max(12px, env(safe-area-inset-right));
		bottom: max(12px, env(safe-area-inset-bottom));
		height: 68px;
		background: #fff;
		border-radius: 999px;
		box-shadow: 0 8px 24px rgba(17, 17, 17, 0.1);
		display: flex;
		align-items: center;
		justify-content: space-around;
		padding: 0 8px;
		z-index: 30;
	}
	a {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		min-width: 52px;
		min-height: 52px;
		justify-content: center;
		font-size: 11px;
		font-weight: 700;
		text-decoration: none;
		color: #5b635d;
		border-radius: 999px;
	}
	a[aria-current='page'] {
		color: #111;
	}
	a[aria-current='page']:not(:last-child)::after {
		content: '';
		position: absolute;
		bottom: 2px;
		width: 18px;
		height: 3px;
		border-radius: 99px;
		background: #111;
	}
	.face {
		display: inline-flex;
	}
	.count {
		position: absolute;
		top: 2px;
		right: 6px;
		min-width: 18px;
		height: 18px;
		border-radius: 99px;
		background: #d64545;
		color: #fff;
		font-size: 10px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: 2px solid #fff;
	}
	.avatar {
		width: 40px;
		height: 40px;
		border-radius: 999px;
		background: #111;
		color: #fff;
		font-weight: 800;
		font-size: 13px;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
</style>
