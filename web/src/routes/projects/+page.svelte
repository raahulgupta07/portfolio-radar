<script lang="ts">
	import { page } from '$app/state';
	import ProjectTable from '$lib/components/ProjectTable.svelte';
	let { data } = $props();
	let query = $state(page.url.searchParams.get('q') ?? '');
</script>

<svelte:head><title>Projects · Portfolio Radar</title></svelte:head>

<section class="page-head flex flex-wrap items-center gap-4">
	<h1 class="m-0 text-[48px] leading-none font-bold tracking-[-0.035em] max-md:text-[34px]">Projects</h1>
	<span class="inline-flex h-11 min-w-11 items-center justify-center rounded-full border-[1.5px] border-[#B9C7BD] text-[15px] font-semibold">{data.projects.length}</span>
</section>

<ProjectTable rows={data.projects} title="All projects" bind:query showSearch autofocus={page.url.searchParams.get('focus') === 'search'} />
