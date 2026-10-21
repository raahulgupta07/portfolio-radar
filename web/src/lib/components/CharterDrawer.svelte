<script lang="ts">
	// Add a program or edit its charter. Admin only. Saved in Radar's own tables and logged in Activity;
	// nothing is written to JIRA, OpenProject or Multica.
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';

	let {
		program = null,
		by,
		onclose,
		ondone
	}: { program?: any | null; by: string; onclose: () => void; ondone: (message: string) => void } = $props();

	const p = untrack(() => program);
	const copy = (rows: any[] | undefined) => JSON.parse(JSON.stringify(rows ?? []));
	let f = $state({
		id: p?.id ?? '',
		name: p?.name ?? '',
		title: p?.title ?? '',
		pm: p?.pm ?? '',
		sponsor: p?.sponsor ?? '',
		health: p?.health ?? '',
		start: p?.start ?? '',
		end: p?.end ?? '',
		currency: p?.currency ?? '',
		statusSummary: p?.statusSummary ?? '',
		itscMessage: p?.itscMessage ?? '',
		problem: p?.problem ?? '',
		goal: p?.goal ?? '',
		scopeIn: p?.scopeIn ?? '',
		scopeOut: p?.scopeOut ?? '',
		benefits: p?.benefits ?? '',
		risks: p?.risks ?? '',
		assumptions: p?.assumptions ?? '',
		budgetNote: p?.budgetNote ?? '',
		budget: copy(p?.budget),
		milestones: copy(p?.milestones),
		measurables: copy(p?.measurables),
		team: copy(p?.team),
		steering: copy(p?.steering)
	});

	type Col = [key: string, label: string, kind?: string];
	const LISTS: { key: 'budget' | 'milestones' | 'measurables' | 'team' | 'steering'; title: string; add: string; cols: Col[] }[] = [
		{ key: 'budget', title: 'Financials (estimated budget)', add: 'Add cost line', cols: [['item', 'Cost item'], ['prudent', 'Prudent', 'number'], ['expansionary', 'Expansionary', 'number'], ['actual', 'Actual / committed', 'number']] },
		{ key: 'milestones', title: 'Milestones (key results)', add: 'Add milestone', cols: [['name', 'Milestone'], ['start', 'Start', 'date'], ['target', 'End (target)', 'date'], ['actual', 'End (actual)', 'date']] },
		{ key: 'measurables', title: 'Measurables', add: 'Add measurable', cols: [['metric', 'Metric'], ['base', 'Base target'], ['stretch', 'Stretch target'], ['actual', 'Actual'], ['status', 'Status']] },
		{ key: 'team', title: 'Project team', add: 'Add person', cols: [['name', 'Name'], ['role', 'Role']] },
		{ key: 'steering', title: 'Steering committee', add: 'Add person', cols: [['name', 'Name'], ['role', 'Role']] }
	];
	const TEXTS: [keyof typeof f, string, number][] = [
		['statusSummary', 'Status summary', 3],
		['itscMessage', 'ITSC key message', 2],
		['problem', 'Problem statement', 3],
		['goal', 'Goal and deliverables', 3],
		['scopeIn', 'Scope: in', 2],
		['scopeOut', 'Scope: out', 2],
		['benefits', 'Customer benefits', 3],
		['risks', 'Risks and issues', 3],
		['assumptions', 'Assumptions and dependencies', 3],
		['budgetNote', 'Budget basis', 2]
	];
	const healths = untrack(() => [...new Set(['', 'Green', 'Amber', 'Red', f.health])]);
	let busy = $state(false);
	let error = $state('');
	let confirm = $state(false);
	const isNew = !p;
	const hasProjects = (p?.kpis?.projects ?? 0) > 0;
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<button type="button" class="scrim" aria-label="Close without saving" tabindex="-1" onclick={onclose}></button>
<div class="drawer" role="dialog" aria-modal="true" aria-labelledby="cd-h">
	<form
		method="POST"
		action="?/saveProgram"
		use:enhance={({ formData }) => {
			busy = true;
			error = '';
			formData.set('payload', JSON.stringify(f));
			return async ({ result, update }) => {
				busy = false;
				if (result.type === 'success') {
					await update({ reset: false });
					ondone(String((result.data as any)?.message ?? 'Saved.'));
				} else if (result.type === 'failure') {
					error = String((result.data as any)?.message ?? 'The change was not saved.');
				} else {
					error = 'Something went wrong. Nothing was saved.';
				}
			};
		}}
	>
		<input type="hidden" name="id" value={f.id} />
		<input type="hidden" name="by" value={by} />
		<input type="hidden" name="base_updated_at" value={p?.updated_at ?? ''} />

		<header>
			<div>
				<div class="eyebrow">{isNew ? 'New program' : 'Program charter'}</div>
				<h2 id="cd-h">{isNew ? 'Add program' : `Edit ${p.name}`}</h2>
			</div>
			<button type="button" class="x" aria-label="Close" onclick={onclose}>&times;</button>
		</header>

		<div class="body">
			<label class="wide">Program name<input class="field" bind:value={f.name} maxlength="200" required /></label>
			<label class="wide">Charter title<input class="field" bind:value={f.title} maxlength="300" /></label>
			<label>Program manager<input class="field" bind:value={f.pm} maxlength="200" /></label>
			<label>Sponsor<input class="field" bind:value={f.sponsor} maxlength="200" /></label>
			<label>Start date<input class="field" type="date" bind:value={f.start} /></label>
			<label>End date<input class="field" type="date" bind:value={f.end} /></label>
			<label>Health
				<select class="field" bind:value={f.health}>{#each healths as h (h)}<option value={h}>{h || 'Not rated'}</option>{/each}</select>
			</label>
			<label>Currency<input class="field" bind:value={f.currency} maxlength="12" placeholder="USD" /></label>

			{#each TEXTS as [key, label, rows] (key)}
				<label class="wide">{label}<textarea class="field" {rows} bind:value={f[key] as string} maxlength="4000"></textarea></label>
			{/each}

			{#each LISTS as L (L.key)}
				<fieldset class="wide">
					<legend>{L.title}</legend>
					{#each f[L.key] as row, i (i)}
						<div class="lrow" style="grid-template-columns: repeat({L.cols.length}, minmax(0, 1fr)) 44px">
							{#each L.cols as [k, label, kind] (k)}
								<input class="field" type={kind ?? 'text'} aria-label={label} placeholder={label} bind:value={row[k]} maxlength="300" />
							{/each}
							<button type="button" class="x sm" aria-label="Remove this row" onclick={() => f[L.key].splice(i, 1)}>&times;</button>
						</div>
					{:else}
						<p class="muted">None yet.</p>
					{/each}
					<button type="button" class="btn add" onclick={() => f[L.key].push({})}>+ {L.add}</button>
				</fieldset>
			{/each}
		</div>

		<footer>
			{#if error}<p class="err" role="alert">{error}</p>{/if}
			<p class="note">Saved in Radar only and logged in Activity as {by || 'you'}. JIRA, OpenProject and Multica are not changed.</p>
			<div class="row">
				<button type="submit" class="btn dark" disabled={busy}>{busy ? 'Saving…' : isNew ? 'Add program' : 'Save charter'}</button>
				<button type="button" class="btn" onclick={onclose}>Cancel</button>
				{#if !isNew}
					{#if hasProjects}
						<span class="note">To delete this program, move or delete its {p.kpis.projects} projects first.</span>
					{:else if confirm}
						<button type="submit" class="btn danger" formaction="?/deleteProgram" disabled={busy}>Yes, delete {p.name}</button>
						<button type="button" class="btn" onclick={() => (confirm = false)}>Keep it</button>
					{:else}
						<button type="button" class="btn quiet" onclick={() => (confirm = true)}>Delete program</button>
					{/if}
				{/if}
			</div>
		</footer>
	</form>
</div>

<style>
	.scrim { position: fixed; inset: 0; background: rgba(17, 17, 17, 0.35); border: 0; padding: 0; z-index: 40; cursor: default; }
	.drawer { position: fixed; top: 12px; right: 12px; bottom: 12px; width: min(760px, calc(100vw - 24px)); background: #fff; border-radius: 28px; z-index: 41; box-shadow: 0 16px 48px rgba(17, 17, 17, 0.2); display: flex; flex-direction: column; overflow: hidden; }
	form { display: flex; flex-direction: column; min-height: 0; height: 100%; }
	header { display: flex; justify-content: space-between; align-items: flex-start; padding: 22px 28px 12px; gap: 12px; }
	.eyebrow { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #5b635d; text-transform: uppercase; }
	h2 { margin: 2px 0 0; font-size: 24px; letter-spacing: -0.02em; }
	.x { width: 44px; height: 44px; border-radius: 999px; border: 0; background: #f1f5f2; font-size: 24px; line-height: 1; cursor: pointer; }
	.x.sm { width: 44px; height: 44px; font-size: 20px; }
	.body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 28px 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px 14px; align-content: start; }
	label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; color: #3e4640; min-width: 0; }
	.wide { grid-column: 1 / -1; }
	.field { min-height: 44px; font-weight: 500; color: #111; width: 100%; box-sizing: border-box; }
	textarea.field { resize: vertical; padding-top: 10px; }
	fieldset { border: 1.5px solid #e3eae5; border-radius: 20px; padding: 10px 16px 14px; margin: 0; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
	legend { font-size: 12px; font-weight: 700; color: #3e4640; padding: 0 6px; }
	.lrow { display: grid; gap: 8px; align-items: center; }
	.muted { margin: 0; font-size: 13px; color: #7a847d; }
	footer { border-top: 1px solid #eef2ef; padding: 14px 28px 20px; display: flex; flex-direction: column; gap: 8px; }
	.note { margin: 0; font-size: 12px; color: #5b635d; align-self: center; }
	footer > .note { align-self: flex-start; }
	.err { margin: 0; font-size: 13px; font-weight: 700; color: #b02a2a; background: #f8cdd0; border-radius: 14px; padding: 8px 12px; }
	.row { display: flex; flex-wrap: wrap; gap: 8px; }
	.btn { min-height: 44px; padding: 0 20px; border-radius: 999px; border: 0; background: #f1f5f2; color: #111; font: 700 14px inherit; cursor: pointer; }
	.btn.add { align-self: flex-start; background: transparent; border: 1.5px dashed #b9c7bd; font-size: 13px; }
	.btn.dark { background: #111; color: #fff; } .btn.danger { background: #b02a2a; color: #fff; } .btn.quiet { background: transparent; text-decoration: underline; }
	.btn:disabled { opacity: 0.6; cursor: default; }
	@media (max-width: 640px) { .body { grid-template-columns: 1fr; } .lrow { grid-template-columns: 1fr 1fr !important; } .drawer { top: 0; right: 0; bottom: 0; width: 100vw; border-radius: 0; } }
</style>
