<script lang="ts">
	import { source } from '$lib/format';
	let { id, stale = false }: { id: string; stale?: boolean } = $props();
	const s = $derived(source(id));
</script>

<span class="wrap">
	<span class="chip" style="background:{s.bg}">{s.label}</span>
	{#if stale}<span class="stale" title="This source failed its last sync. Showing its last good data.">Stale</span>{/if}
</span>

<style>
	.wrap {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		border-radius: 999px;
		padding: 6px 12px;
		font-size: 12px;
		font-weight: 700;
	}
	.stale {
		font-size: 11px;
		font-weight: 700;
		color: #fff;
		background: #111;
		border-radius: 999px;
		padding: 4px 9px;
	}
</style>
