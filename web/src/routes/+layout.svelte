<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import Rail from '$lib/components/Rail.svelte';
	import TabBar from '$lib/components/TabBar.svelte';

	let { data, children } = $props();
	const mood = $derived(
		data.shell?.radarCount ? 'alert' : data.shell?.offline ? 'offline' : ('ready' as const)
	);
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<title>Portfolio Radar</title>
</svelte:head>

{#if data.user}
	<div class="shell">
		<div class="rail-slot">
			<Rail
				radarCount={data.shell?.radarCount ?? 0}
				{mood}
				avg={data.shell?.avg ?? null}
				initials={data.user.initials}
				userName={data.user.name}
				isAdmin={data.isAdmin}
			/>
		</div>
		<main id="main">{@render children()}</main>
	</div>
	<div class="tab-slot">
		<TabBar radarCount={data.shell?.radarCount ?? 0} {mood} initials={data.user.initials} />
	</div>
{:else}
	{@render children()}
{/if}

<style>
	.shell {
		min-height: 100vh;
		padding: 14px 32px 56px 14px;
		box-sizing: border-box;
		display: flex;
		gap: 24px;
		align-items: flex-start;
	}
	main {
		flex: 1;
		min-width: 0;
		max-width: 1440px;
		margin: 0 auto;
		padding-top: 12px;
		display: flex;
		flex-direction: column;
		gap: 28px;
	}
	.tab-slot {
		display: none;
	}
	@media (max-width: 767px) {
		.shell {
			padding: 14px 14px 110px;
		}
		.rail-slot {
			display: none;
		}
		.tab-slot {
			display: block;
		}
		main {
			gap: 18px;
			padding-top: 4px;
		}
	}
	@media (min-width: 768px) and (max-width: 1199px) {
		.shell {
			padding: 14px 20px 40px 12px;
			gap: 16px;
		}
	}
</style>
