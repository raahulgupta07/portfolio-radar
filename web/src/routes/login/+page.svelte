<script lang="ts">
	import RadarFace from '$lib/components/RadarFace.svelte';
	let { data, form } = $props();
</script>

<svelte:head><title>Sign in · Portfolio Radar</title></svelte:head>

<div class="wrap">
	<section class="box">
		<RadarFace mood="ready" size={72} />
		<h1>Portfolio Radar</h1>
		<p class="lead">City Holdings projects from JIRA, OpenProject and Multica, in one view. View only.</p>

		{#if form?.error}<p class="err" role="alert">{form.error}</p>{/if}

		{#if data.sso}
			<form method="POST" action="?/sso"><button class="pill-btn primary wide" type="submit">Sign in with City SSO</button></form>
		{:else}
			<p class="note">City SSO is not set up on this server yet.</p>
		{/if}

		{#if data.dev}
			<div class="dev">
				<h2>Development sign-in</h2>
				<p class="note">Sample users. Turned off in production.</p>
				<form method="POST" action="?/dev" class="users">
					{#each data.devUsers as u (u.token)}
						<button class="user" type="submit" name="token" value={u.token}>
							<span class="name">{u.name}</span><span class="role">{u.label}</span>
						</button>
					{/each}
				</form>
			</div>
		{/if}
	</section>
</div>

<style>
	.wrap {
		min-height: 100vh;
		display: grid;
		place-items: center;
		padding: 24px 16px;
		box-sizing: border-box;
	}
	.box {
		background: #fff;
		border-radius: 32px;
		padding: 36px 32px;
		width: 100%;
		max-width: 440px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		align-items: flex-start;
	}
	h1 {
		margin: 4px 0 0;
		font-size: 34px;
		letter-spacing: -0.03em;
	}
	h2 {
		margin: 0;
		font-size: 15px;
	}
	.lead {
		margin: 0;
		color: #3e4640;
		font-size: 15px;
		line-height: 1.5;
	}
	.note {
		margin: 0;
		color: #5b635d;
		font-size: 13px;
	}
	.err {
		margin: 0;
		background: #f8cdd0;
		border-radius: 16px;
		padding: 10px 14px;
		font-size: 14px;
		font-weight: 600;
	}
	.wide {
		width: 100%;
		justify-content: center;
	}
	form {
		width: 100%;
	}
	.dev {
		width: 100%;
		border-top: 1px solid #eef2ef;
		padding-top: 16px;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}
	.users {
		display: grid;
		gap: 8px;
	}
	.user {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 12px;
		min-height: 48px;
		border: 0;
		border-radius: 18px;
		background: #f4f7f5;
		padding: 0 16px;
		font: 600 14px var(--font-sans);
		cursor: pointer;
		text-align: left;
	}
	.user:hover {
		background: #e2f2e7;
	}
	.role {
		font-size: 12px;
		color: #5b635d;
	}
</style>
