<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';
	import Icon from '$lib/components/Icon.svelte';
	import RadarFace from '$lib/components/RadarFace.svelte';
	import { HEALTH, day, dayTime, fullDate } from '$lib/format';
	import { onMount, tick, untrack } from 'svelte';

	let { data, form } = $props();
	const c = $derived(data.conv);
	const st = $derived(c.status);
	const isApprover = $derived(data.user?.roles.includes('approver'));
	let draft = $state(untrack(() => (data.about ? `How is ${data.about} doing?` : '')));
	let editing = $state<number | null>(null);
	let editText = $state('');
	let memText = $state('');
	let scroller: HTMLDivElement | undefined = $state();

	const dot: Record<string, string> = {
		ready: '#2E8B57', happy: '#2E8B57', scanning: '#7FB2EC', thinking: '#7FB2EC', listening: '#7FB2EC',
		alert: '#D64545', asking: '#F2C14E', offline: '#9AA59D', resting: '#9AA59D'
	};
	const sevTone: Record<string, { bg: string; label: string }> = {
		high: { bg: '#F8CDD0', label: 'Off track' },
		medium: { bg: '#FBE6A9', label: 'At risk' },
		low: { bg: '#F4F7F5', label: 'Data' }
	};
	const typeLabel: Record<string, string> = { sync: 'Sync', data: 'Data', stale: 'Stale', change: 'Change', slipping: 'At risk', health: 'Off track' };
	const suggestions = ['What needs me today?', 'What is off track?', 'Is the sync ok?', 'How is POS03?'];

	async function scrollDown() {
		await tick();
		scroller?.scrollTo({ top: scroller.scrollHeight, behavior: 'smooth' });
	}
	onMount(() => {
		scrollDown();
		// While Radar is writing an answer, check again every 2 seconds.
		const t = setInterval(() => {
			if (c.thinking) invalidateAll().then(scrollDown);
		}, 2000);
		return () => clearInterval(t);
	});
	const sent = () => {
		const text = draft;
		draft = '';
		return async ({ update, result }: any) => {
			if (result.type === 'failure') draft = text;
			await update({ reset: false });
			scrollDown();
		};
	};
</script>

<svelte:head><title>Radar · Portfolio Radar</title></svelte:head>

<div class="radar-page">
	<section class="conv">
		<header>
			<span class="face"><RadarFace mood={st.mood} size={60} /><span class="sdot" style="background:{dot[st.mood] ?? '#2E8B57'}"></span></span>
			<div class="ht">
				<h1>Radar</h1>
				<span>{c.thinking ? 'Writing an answer…' : st.status_text}</span>
			</div>
			<div class="hb">
				<a class="ib" href="/" aria-label="Back to overview" title="Overview"><Icon name="home" /></a>
			</div>
		</header>

		{#if c.waiting.length}
			<div class="waiting">
				<span class="wl">WAITING FOR YOU</span>
				{#each c.waiting as w (w.message_id)}
					<a class="wait" href={`#m${w.message_id}`} style="background:{w.type === 'ask' ? '#FBE6A9' : w.kind === 'nudge' ? '#F8CDD0' : '#CFE3FB'}">{w.label}</a>
				{/each}
			</div>
		{/if}

		<div class="scroll" bind:this={scroller}>
			<div class="thread">
				<div class="welcome">
					<RadarFace mood="happy" size={84} />
					<span class="wt">This is your conversation with Radar</span>
					<span class="ws">Radar reads JIRA, OpenProject and Multica every night, checks every project, and tells you what needs you. It never changes the trackers and asks before it sends anything.</span>
				</div>

				{#each c.messages as m (m.id)}
					<div id={`m${m.id}`} class="msg">
						{#if m.kind === 'divider'}
							<div class="divider"><span>{m.body}</span></div>
						{:else if m.kind === 'pill'}
							<div class="pill-row"><span class="pill"><Icon name="check" size={14} />{m.body}</span></div>
						{:else if m.kind === 'me'}
							<div class="me-row"><div class="me">{m.body}</div></div>
						{:else if m.kind === 'radar'}
							<div class="r-row">
								<span class="av"><RadarFace mood={m.mood ?? 'ready'} size={38} /></span>
								<div class="rcol">
									<div class="bubble">{m.body}</div>
									{#if m.payload?.evidence}<span class="ev">Evidence: {m.payload.evidence}</span>{/if}
								</div>
							</div>
						{:else if m.kind === 'ask'}
							<div class="r-row">
								<span class="av"><RadarFace mood={m.payload.answer ? 'happy' : 'asking'} size={38} /></span>
								<div class="ask">
									<span class="al">RADAR ASKS</span>
									<span class="at">{m.body}</span>
									{#if !m.payload.answer && isApprover}
										<div class="ab">
											<form method="POST" action="?/answer" use:enhance><input type="hidden" name="message_id" value={m.id} /><input type="hidden" name="answer" value="yes" /><button class="btn dark">Yes, draft it</button></form>
											<form method="POST" action="?/answer" use:enhance><input type="hidden" name="message_id" value={m.id} /><input type="hidden" name="answer" value="no" /><button class="btn">Not now</button></form>
										</div>
									{:else if m.payload.answer}
										<span class="aa">{m.payload.answered_by} answered: {m.payload.answer === 'yes' ? 'Yes, draft it' : 'Not now'}{m.payload.draft_id ? ' · draft ready below' : ''}</span>
									{/if}
								</div>
							</div>
						{:else if m.kind === 'health'}
							<div class="cards4">
								{#each m.payload.tiles ?? [] as t (t.health)}
									<a href={`/projects?health=${t.health}`} style="background:{HEALTH[t.health as keyof typeof HEALTH]?.bg ?? '#E2F2E7'}"><b class="tabular">{t.count}</b><span>{t.label}</span></a>
								{/each}
							</div>
						{:else if m.kind === 'findings'}
							<div class="finds">
								{#each m.payload.items ?? [] as f, i (i)}
									<a href={f.project ? `/projects/${f.project}` : '/admin'} style="background:{f.type === 'sync' ? '#CFE3FB' : sevTone[f.severity]?.bg}">
										<span class="tag">{typeLabel[f.type] ?? f.type}</span>
										<span class="ft"><strong>{f.text}</strong><span>{f.detail}</span></span>
									</a>
								{/each}
							</div>
						{:else if m.kind === 'dep'}
							<div class="dep">
								<a href={`/projects/${m.payload.from.code}`} class="dn" style="background:#F8CDD0"><strong>{m.payload.from.short}</strong><span>{m.payload.from.milestone} · {day(m.payload.from.due)} · late</span></a>
								<Icon name="arrow" size={18} />
								{#each m.payload.to as t (t.code)}
									<a href={`/projects/${t.code}`} class="dn" style="background:#FBE6A9"><strong>{t.short}</strong><span>{t.milestone} · {day(t.due)} · {t.percent_done}%</span></a>
								{/each}
								<a href="/roadmap" class="btn">Open roadmap</a>
							</div>
						{:else if m.kind === 'approval' && m.approval}
							{@const a = m.approval}
							<div class="appr">
								<div class="aph">
									<span><strong>{a.title}</strong><span>To: {a.to}{a.send_at ? ` · sends ${dayTime(a.send_at)} after approval` : ''}</span></span>
									<span class="badge" class:pending={a.status === 'pending'} class:rej={a.status === 'rejected'}>{a.status === 'pending' ? 'Needs approval' : a.sent_at ? 'Sent' : a.status === 'approved' ? 'Approved' : 'Rejected'}</span>
								</div>
								{#if editing === a.id}
									<form method="POST" action="?/decide" use:enhance={() => async ({ update }) => { editing = null; await update(); }}>
										<input type="hidden" name="approval_id" value={a.id} /><input type="hidden" name="decision" value="approve" />
										<label class="sr-only" for={`edit-${a.id}`}>Edit draft</label>
										<textarea id={`edit-${a.id}`} name="body" bind:value={editText} rows="12"></textarea>
										<div class="ab"><button class="btn">Approve edited</button><button type="button" class="btn ghost" onclick={() => (editing = null)}>Cancel</button></div>
									</form>
								{:else}
									<div class="draft">{a.body}</div>
									{#if a.status === 'pending' && isApprover}
										<div class="ab">
											<form method="POST" action="?/decide" use:enhance><input type="hidden" name="approval_id" value={a.id} /><input type="hidden" name="decision" value="approve" /><button class="btn">{a.kind === 'digest' ? 'Approve digest' : 'Approve and send'}</button></form>
											<button type="button" class="btn ghost" onclick={() => { editing = a.id; editText = a.body; }}>Edit</button>
											<form method="POST" action="?/decide" use:enhance><input type="hidden" name="approval_id" value={a.id} /><input type="hidden" name="decision" value="reject" /><button class="btn ghost">Reject</button></form>
										</div>
									{:else if a.status !== 'pending'}
										<span class="done">{a.status === 'approved' ? 'Approved' : 'Rejected'} by {a.decided_by} · {dayTime(a.decided_at)}{a.sent_at ? ` · sent ${dayTime(a.sent_at)}` : a.status === 'approved' && a.send_result && !a.send_result.ok ? ` · not sent: ${a.send_result.detail}` : ''}</span>
									{:else}
										<span class="done">Waiting for an approver.</span>
									{/if}
								{/if}
							</div>
						{/if}
					</div>
				{/each}
				{#if c.thinking}
					<div class="r-row"><span class="av"><RadarFace mood="thinking" size={38} /></span><div class="bubble muted">Writing an answer…</div></div>
				{/if}
			</div>
		</div>

		<div class="composer">
			<div class="cin">
				{#if form?.message}<p class="err" role="alert">{form.message}</p>{/if}
				<div class="sugg">
					{#each suggestions as s (s)}<button type="button" class="chipq" onclick={() => (draft = s)}>{s}</button>{/each}
				</div>
				<form method="POST" action="?/ask" use:enhance={sent} class="box">
					<label class="grow"><span class="sr-only">Message Radar</span>
						<input name="text" type="text" bind:value={draft} placeholder="Message Radar. Ask about any project, team or date…" autocomplete="off" maxlength="2000" />
					</label>
					<button type="submit" class="send" class:on={draft.trim().length > 0} disabled={!draft.trim()}>Send</button>
				</form>
			</div>
		</div>
	</section>

	<aside aria-label="About Radar">
		<section class="me-card">
			<div class="mc">
				<span class="mface"><RadarFace mood={st.mood} size={56} /></span>
				<div><span class="mn">Radar</span><span class="ms">Portfolio agent · read-only</span></div>
			</div>
			<span class="mtext">Watches all {st.projects} projects every day and tells you only what needs you.</span>
			<div class="stats">
				<div><b class="tabular">{st.projects}</b><span>projects</span></div>
				<div><b class="tabular">{st.sources}</b><span>sources</span></div>
				<div><b class="tabular">{st.findings}</b><span>findings</span></div>
			</div>
			<span class="last"><span class="ld" style="background:{dot[st.mood]}"></span>{st.last_run ? `Last check ${dayTime(st.last_run.ended_at)}` : 'No check yet'} · next after the {st.rules.sync_time} sync</span>
		</section>

		<section class="side">
			<h2>What Radar does</h2>
			<ul class="does">
				<li><span class="g"></span><span>Checks project health</span><span>{st.last_run ? day(st.last_run.ended_at) : '—'}</span></li>
				<li><span class="g"></span><span>Finds missing data</span><span>Daily</span></li>
				<li><span class="g"></span><span>Watches the sync</span><span>Every sync</span></li>
				<li><span class="g"></span><span>Writes the weekly digest</span><span>{st.rules.digest_day} {st.rules.digest_time}</span></li>
				<li><span class="g"></span><span>Answers your questions</span><span>Any time</span></li>
			</ul>
		</section>

		<section class="side">
			<div class="sh"><h2>Routines</h2>{#if data.isAdmin}<a href="/admin">Edit</a>{/if}</div>
			<div class="routines">
				{#each st.routines as r, i (r.what)}
					<div style="background:{['#E2F2E7', '#CFE3FB', '#FBE6A9', '#F8CDD0'][i % 4]}"><strong>{r.when}</strong><span>{r.what}</span></div>
				{/each}
			</div>
		</section>

		<section class="side">
			<h2>Radar's rules</h2>
			<ul class="rules">
				<li>Reads only. Never changes JIRA, OpenProject or Multica.</li>
				<li>Asks before it sends any message. Only an approver can say yes.</li>
				<li>Shows the evidence behind every answer.</li>
			</ul>
		</section>

		<section class="side">
			<h2>Radar remembers</h2>
			<ul class="mem">
				{#each c.memory as m (m.id)}
					<li><span>{m.text}</span>
						<form method="POST" action="?/forget" use:enhance><input type="hidden" name="id" value={m.id} /><button class="x" aria-label={`Forget: ${m.text}`}><Icon name="x" size={14} /></button></form>
					</li>
				{:else}
					<li class="none">Nothing yet.</li>
				{/each}
			</ul>
			<form method="POST" action="?/remember" use:enhance={() => async ({ update }) => { memText = ''; await update(); }} class="memf">
				<label class="grow"><span class="sr-only">Something Radar should remember</span><input name="text" bind:value={memText} placeholder="Add something to remember" maxlength="300" /></label>
				<button class="btn quiet" disabled={memText.trim().length < 3}>Add</button>
			</form>
		</section>
	</aside>
</div>

<style>
	.radar-page {
		display: flex;
		gap: 16px;
		align-items: flex-start;
	}
	.conv {
		flex: 999 1 600px;
		min-width: 0;
		background: #fff;
		border-radius: 32px;
		display: flex;
		flex-direction: column;
		height: calc(100vh - 40px);
		min-height: 640px;
		overflow: hidden;
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 16px;
		padding: 18px 24px;
		border-bottom: 1px solid #eef2ef;
	}
	.face {
		position: relative;
		width: 60px;
		height: 60px;
		display: inline-flex;
		flex-shrink: 0;
	}
	.sdot {
		position: absolute;
		right: 1px;
		bottom: 1px;
		width: 14px;
		height: 14px;
		border-radius: 99px;
		border: 3px solid #fff;
	}
	.ht {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1;
		min-width: 0;
	}
	h1 {
		margin: 0;
		font-size: 26px;
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1;
	}
	.ht span {
		font-size: 13px;
		color: #5b635d;
	}
	.ib {
		width: 44px;
		height: 44px;
		border-radius: 999px;
		border: 1.5px solid #dde5df;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: #111;
	}
	.waiting {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		padding: 12px 24px;
		background: #fafcfb;
		border-bottom: 1px solid #eef2ef;
	}
	.wl {
		font-size: 12px;
		font-weight: 800;
		letter-spacing: 0.03em;
		color: #3e4640;
		margin-right: 4px;
	}
	.wait {
		display: inline-flex;
		align-items: center;
		border-radius: 999px;
		padding: 0 14px;
		min-height: 38px;
		font-size: 13px;
		font-weight: 600;
		text-decoration: none;
	}
	.scroll {
		flex: 1;
		overflow-y: auto;
		padding: 24px;
	}
	.thread {
		max-width: 780px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.msg {
		scroll-margin-top: 20px;
	}
	.welcome {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		padding: 8px 0 18px;
		text-align: center;
	}
	.wt {
		font-size: 18px;
		font-weight: 800;
	}
	.ws {
		font-size: 13px;
		color: #3e4640;
		max-width: 460px;
		line-height: 1.5;
	}
	.divider {
		display: flex;
		justify-content: center;
		padding: 6px 0;
	}
	.divider span {
		background: #f1f5f2;
		border-radius: 999px;
		padding: 6px 14px;
		font-size: 12px;
		font-weight: 700;
		color: #3e4640;
	}
	.pill-row {
		margin-left: 50px;
		display: flex;
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		background: #f4f7f5;
		border-radius: 999px;
		padding: 8px 14px;
		font-size: 12px;
		color: #3e4640;
	}
	.me-row {
		display: flex;
		justify-content: flex-end;
	}
	.me {
		max-width: 70%;
		background: #111;
		color: #fff;
		border-radius: 22px 22px 6px 22px;
		padding: 12px 18px;
		font-size: 14px;
		line-height: 1.5;
		font-weight: 600;
		white-space: pre-line;
	}
	.r-row {
		display: flex;
		gap: 12px;
		align-items: flex-end;
	}
	.av {
		width: 38px;
		height: 38px;
		flex-shrink: 0;
		display: inline-flex;
	}
	.rcol {
		max-width: 84%;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.bubble {
		background: #f1f5f2;
		border-radius: 22px 22px 22px 6px;
		padding: 14px 18px;
		font-size: 14px;
		line-height: 1.55;
		white-space: pre-line;
	}
	.bubble.muted {
		color: #5b635d;
	}
	.ev {
		font-size: 12px;
		color: #5b635d;
		padding-left: 8px;
	}
	.ask {
		max-width: 84%;
		display: flex;
		flex-direction: column;
		gap: 10px;
		background: #fbe6a9;
		border-radius: 22px;
		padding: 14px 18px;
	}
	.al {
		font-size: 12px;
		font-weight: 800;
		letter-spacing: 0.03em;
	}
	.at {
		font-size: 14px;
		line-height: 1.55;
	}
	.aa {
		font-size: 12px;
		font-weight: 700;
	}
	.ab {
		display: flex;
		gap: 8px;
		flex-wrap: wrap;
	}
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		border-radius: 999px;
		padding: 0 16px;
		min-height: 40px;
		font: 600 13px var(--font-sans);
		cursor: pointer;
		border: 0;
		background: #fff;
		color: #111;
		text-decoration: none;
	}
	.btn.dark {
		background: #111;
		color: #fff;
	}
	.btn.ghost {
		background: #2a2a2a;
		color: #fff;
	}
	.btn.quiet {
		background: #f1f5f2;
	}
	.btn:disabled {
		opacity: 0.5;
	}
	.cards4 {
		margin-left: 50px;
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 8px;
		max-width: 600px;
	}
	.cards4 a {
		border-radius: 20px;
		padding: 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		text-decoration: none;
	}
	.cards4 b {
		font-size: 26px;
	}
	.cards4 span {
		font-size: 12px;
		font-weight: 600;
	}
	.finds {
		margin-left: 50px;
		display: flex;
		flex-direction: column;
		gap: 8px;
		max-width: 640px;
	}
	.finds a {
		display: flex;
		align-items: center;
		gap: 14px;
		border-radius: 22px;
		padding: 12px 16px;
		text-decoration: none;
	}
	.tag {
		background: #111;
		color: #fff;
		border-radius: 999px;
		padding: 4px 10px;
		font-size: 11px;
		font-weight: 700;
		white-space: nowrap;
	}
	.ft {
		flex: 1;
		display: flex;
		flex-direction: column;
		font-size: 12px;
	}
	.ft strong {
		font-size: 14px;
	}
	.dep {
		margin-left: 50px;
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
		background: #f4f7f5;
		border-radius: 22px;
		padding: 12px 16px;
		max-width: 640px;
	}
	.dn {
		border-radius: 16px;
		padding: 10px 14px;
		display: flex;
		flex-direction: column;
		text-decoration: none;
		font-size: 12px;
	}
	.dn strong {
		font-size: 14px;
	}
	.appr {
		margin-left: 50px;
		max-width: 640px;
		background: #161616;
		color: #fff;
		border-radius: 26px;
		padding: 18px 20px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}
	.aph {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}
	.aph > span:first-child {
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 12px;
		color: #c9cfcb;
	}
	.aph strong {
		font-size: 15px;
		color: #fff;
	}
	.badge {
		border-radius: 999px;
		padding: 6px 12px;
		font-size: 12px;
		font-weight: 700;
		background: #7fd69a;
		color: #111;
	}
	.badge.pending {
		background: #f2c14e;
	}
	.badge.rej {
		background: #f27e7e;
	}
	.draft {
		background: #2a2a2a;
		border-radius: 18px;
		padding: 14px 16px;
		font-size: 13px;
		line-height: 1.55;
		white-space: pre-line;
		color: #e8ece9;
	}
	textarea {
		width: 100%;
		box-sizing: border-box;
		background: #2a2a2a;
		color: #fff;
		border: 1.5px solid #3a3a3a;
		border-radius: 18px;
		padding: 14px 16px;
		font: 13px/1.55 var(--font-sans);
		margin-bottom: 10px;
	}
	.done {
		font-size: 13px;
		color: #d9deda;
	}
	.composer {
		border-top: 1px solid #eef2ef;
		padding: 14px 24px 18px;
	}
	.cin {
		max-width: 780px;
		margin: 0 auto;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.err {
		margin: 0;
		background: #f8cdd0;
		border-radius: 14px;
		padding: 8px 12px;
		font-size: 13px;
		font-weight: 600;
	}
	.sugg {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.chipq {
		border: 1.5px solid #dde5df;
		background: #fff;
		border-radius: 999px;
		padding: 0 14px;
		min-height: 38px;
		font: 600 13px var(--font-sans);
		cursor: pointer;
	}
	.chipq:hover {
		border-color: #111;
	}
	.box {
		display: flex;
		align-items: center;
		gap: 6px;
		background: #f1f5f2;
		border-radius: 999px;
		padding: 6px 6px 6px 18px;
	}
	.grow {
		flex: 1;
		display: flex;
	}
	.box input {
		flex: 1;
		border: 0;
		outline: none;
		background: transparent;
		font: 500 14px var(--font-sans);
		min-height: 44px;
	}
	.send {
		border: 0;
		border-radius: 999px;
		padding: 0 24px;
		min-height: 44px;
		font: 700 14px var(--font-sans);
		background: #dde5df;
		color: #5b635d;
	}
	.send.on {
		background: #111;
		color: #fff;
		cursor: pointer;
	}
	aside {
		flex: 1 1 320px;
		max-width: 360px;
		min-width: 280px;
		display: flex;
		flex-direction: column;
		gap: 14px;
		height: calc(100vh - 40px);
		min-height: 640px;
		overflow-y: auto;
	}
	.me-card {
		background: #111;
		color: #fff;
		border-radius: 32px;
		padding: 24px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.mc {
		display: flex;
		align-items: center;
		gap: 14px;
	}
	.mface {
		width: 64px;
		height: 64px;
		border-radius: 20px;
		background: #1f2a22;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.mc div {
		display: flex;
		flex-direction: column;
	}
	.mn {
		font-size: 20px;
		font-weight: 800;
	}
	.ms,
	.mtext {
		font-size: 13px;
		color: #c9cfcb;
	}
	.stats {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 8px;
	}
	.stats div {
		background: #1f1f1f;
		border-radius: 16px;
		padding: 10px 12px;
		display: flex;
		flex-direction: column;
	}
	.stats b {
		font-size: 20px;
	}
	.stats span {
		font-size: 11px;
		color: #c9cfcb;
	}
	.last {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 12px;
		color: #c9cfcb;
	}
	.ld {
		width: 8px;
		height: 8px;
		border-radius: 99px;
	}
	.side {
		background: #fff;
		border-radius: 28px;
		padding: 20px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	h2 {
		margin: 0;
		font-size: 16px;
		font-weight: 800;
	}
	.sh {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.sh a {
		font-size: 12px;
		font-weight: 700;
	}
	ul {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.does {
		display: flex;
		flex-direction: column;
		gap: 10px;
		font-size: 14px;
	}
	.does li {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.does li span:nth-child(2) {
		flex: 1;
		font-weight: 600;
	}
	.does li span:last-child {
		font-size: 12px;
		color: #5b635d;
	}
	.g {
		width: 8px;
		height: 8px;
		border-radius: 99px;
		background: #2e8b57;
	}
	.routines {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 8px;
	}
	.routines div {
		border-radius: 18px;
		padding: 12px 14px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		font-size: 12px;
	}
	.routines strong {
		font-size: 13px;
	}
	.rules {
		display: flex;
		flex-direction: column;
		gap: 8px;
		font-size: 13px;
		color: #2a302c;
		padding-left: 18px;
		list-style: disc;
	}
	.mem {
		display: flex;
		flex-direction: column;
		gap: 8px;
		font-size: 13px;
		color: #2a302c;
	}
	.mem li {
		background: #f4f7f5;
		border-radius: 14px;
		padding: 6px 6px 6px 12px;
		display: flex;
		align-items: center;
		gap: 8px;
	}
	.mem li span {
		flex: 1;
	}
	.mem .none {
		color: #5b635d;
		padding: 9px 12px;
	}
	.x {
		width: 30px;
		height: 30px;
		border-radius: 99px;
		border: 0;
		background: transparent;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.x:hover {
		background: #e3eae5;
	}
	.memf {
		display: flex;
		gap: 6px;
	}
	.memf input {
		flex: 1;
		min-height: 40px;
		border-radius: 999px;
		border: 1.5px solid #dde5df;
		padding: 0 14px;
		font: 500 13px var(--font-sans);
	}
	@media (max-width: 1100px) {
		aside {
			display: none;
		}
	}
	@media (max-width: 767px) {
		.conv {
			height: calc(100vh - 120px);
			border-radius: 26px;
		}
		.scroll,
		.composer {
			padding-left: 14px;
			padding-right: 14px;
		}
		.cards4 {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			margin-left: 0;
		}
		.finds,
		.dep,
		.appr,
		.pill-row {
			margin-left: 0;
		}
		.sugg {
			flex-wrap: nowrap;
			overflow-x: auto;
			padding-bottom: 2px;
		}
		.chipq {
			flex-shrink: 0;
		}
		header {
			padding: 14px 16px;
		}
	}
</style>
