<script lang="ts">
	let { data } = $props();
</script>

<svelte:head><title>Account · Portfolio Radar</title></svelte:head>

<h1 class="m-0 text-[34px] font-bold tracking-tight">Account</h1>
<section class="card flex flex-col gap-3">
	<p class="m-0 text-lg font-bold">{data.user?.name}</p>
	<p class="m-0 text-sm text-muted">{data.user?.id} · {data.user?.roles.join(', ')}</p>
	<p class="m-0 text-sm text-muted">Signed in with City SSO. This app is view only.</p>
	<form method="POST" action="/logout"><button class="pill-btn primary" type="submit">Sign out</button></form>
</section>
