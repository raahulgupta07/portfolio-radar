<script lang="ts">
	import { page } from '$app/state';
	import RadarFace from '$lib/components/RadarFace.svelte';
</script>

<svelte:head><title>{page.status} · Portfolio Radar</title></svelte:head>

<section class="card flex flex-col items-start gap-3">
	<RadarFace mood={page.status === 404 ? 'thinking' : 'offline'} size={64} />
	<h1 class="m-0 text-3xl font-bold tracking-tight">{page.status === 404 ? 'Not found' : 'Something went wrong'}</h1>
	<p class="m-0 text-[15px] text-soft">{page.error?.message}</p>
	<a class="pill-btn primary no-underline" href="/">Back to overview</a>
</section>
