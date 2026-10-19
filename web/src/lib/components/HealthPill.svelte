<script lang="ts">
	import { health } from '$lib/format';
	let { value }: { value: string | null | undefined } = $props();
	const h = $derived(health(value));
</script>

<span class="pill" style="background:{h.bg}"><span class="dot" style="background:{h.dot}"></span>{h.label}</span>

<style>
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		border-radius: 999px;
		padding: 6px 12px;
		font-size: 12px;
		font-weight: 700;
		white-space: nowrap;
	}
	.dot {
		width: 8px;
		height: 8px;
		border-radius: 99px;
	}
</style>
