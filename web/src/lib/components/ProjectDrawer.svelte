<script lang="ts">
	// Add or edit one program-office project. Admin only. Saved in Radar's own tables and logged in Activity;
	// nothing is written to JIRA, OpenProject or Multica.
	import { untrack } from 'svelte';
	import { enhance } from '$app/forms';

	let {
		project = null,
		programs,
		statuses,
		defaultProgram = '',
		by,
		onclose,
		ondone
	}: {
		project?: any | null;
		programs: any[];
		statuses: string[];
		defaultProgram?: string;
		by: string;
		onclose: () => void;
		ondone: (message: string) => void;
	} = $props();

	const p = untrack(() => project);
	let f = $state({
		id: p?.id ?? '',
		program: p?.program ?? untrack(() => defaultProgram) ?? '',
		name: p?.name ?? '',
		workstream: p?.workstream ?? '',
		owner: p?.owner ?? '',
		status: p?.status ?? 'Planned',
		health: p?.health ?? '',
		pct: p?.pct ?? 0,
		start: p?.start ?? '',
		target: p?.target ?? '',
		targetPrecision: p?.target_precision ?? '',
		timingNote: p?.timing_note ?? '',
		milestoneId: p?.milestone_id ?? '',
		description: p?.description ?? '',
		impact: p?.impact ?? '',
		nextStep: p?.next_step ?? '',
		decision: p?.decision ?? '',
		remarks: p?.remarks ?? '',
		raci: { R: p?.raci?.R ?? '', A: p?.raci?.A ?? '', C: p?.raci?.C ?? '', I: p?.raci?.I ?? '' }
	});
	if (!f.program) f.program = untrack(() => programs[0]?.id ?? '');

	const healths = untrack(() => [...new Set(['', 'Green', 'Amber', 'Red', f.health])]);
	const milestones = $derived<any[]>(programs.find((x) => x.id === f.program)?.milestones ?? []);
	let busy = $state(false);
	let error = $state('');
	let confirm = $state(false);
	const isNew = !p;

	const payload = () => ({ ...f, pct: Number(f.pct) || 0 });
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<button type="button" class="scrim" aria-label="Close without saving" tabindex="-1" onclick={onclose}></button>
<div class="drawer" role="dialog" aria-modal="true" aria-labelledby="pd-h">
	<form
		method="POST"
		action="?/saveProject"
		use:enhance={({ formData }) => {
			busy = true;
			error = '';
			formData.set('payload', JSON.stringify(payload()));
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
				<div class="eyebrow">{isNew ? 'New project' : f.id}</div>
				<h2 id="pd-h">{isNew ? 'Add project' : 'Edit project'}</h2>
			</div>
			<button type="button" class="x" aria-label="Close" onclick={onclose}>&times;</button>
		</header>

		<div class="body">
			<label class="wide">Project name<input class="field" bind:value={f.name} maxlength="200" required /></label>
			<label>Program
				<select class="field" bind:value={f.program} required>
					{#each programs as pr (pr.id)}<option value={pr.id}>{pr.name}</option>{/each}
				</select>
			</label>
			<label>Workstream<input class="field" bind:value={f.workstream} maxlength="120" /></label>
			<label>Owner<input class="field" bind:value={f.owner} maxlength="200" /></label>
			<label>Status
				<select class="field" bind:value={f.status}>
					{#each statuses as s (s)}<option>{s}</option>{/each}
					{#if f.status && !statuses.includes(f.status)}<option>{f.status}</option>{/if}
				</select>
			</label>
			<label>Health
				<select class="field" bind:value={f.health}>
					{#each healths as h (h)}<option value={h}>{h || 'Not rated'}</option>{/each}
				</select>
			</label>
			<label>% complete<input class="field" type="number" min="0" max="100" step="1" bind:value={f.pct} /></label>
			<label>Start date<input class="field" type="date" bind:value={f.start} /></label>
			<label>Target date<input class="field" type="date" bind:value={f.target} /></label>
			<label>Target is exact to
				<select class="field" bind:value={f.targetPrecision}>
					<option value="">Not set</option><option value="day">The day</option><option value="month">The month</option>
				</select>
			</label>
			<label>Timing note<input class="field" bind:value={f.timingNote} maxlength="300" placeholder="For example: after vendor sign-off" /></label>
			<label class="wide">Charter milestone
				<select class="field" bind:value={f.milestoneId}>
					<option value="">None</option>
					{#each milestones as m (m.id)}<option value={m.id}>{m.name}{m.target ? ` (${m.target})` : ''}</option>{/each}
				</select>
			</label>
			<label class="wide">Description<textarea class="field" rows="3" bind:value={f.description} maxlength="2000"></textarea></label>
			<label class="wide">Impact<textarea class="field" rows="2" bind:value={f.impact} maxlength="2000"></textarea></label>
			<label class="wide">Next step<textarea class="field" rows="2" bind:value={f.nextStep} maxlength="1000"></textarea></label>
			<label class="wide">Decision needed<textarea class="field" rows="2" bind:value={f.decision} maxlength="1000"></textarea></label>
			<label class="wide">Remarks<textarea class="field" rows="2" bind:value={f.remarks} maxlength="2000"></textarea></label>

			<fieldset class="wide">
				<legend>RACI (separate names with commas)</legend>
				<label>Responsible<input class="field" bind:value={f.raci.R} maxlength="500" /></label>
				<label>Accountable<input class="field" bind:value={f.raci.A} maxlength="500" /></label>
				<label>Consulted<input class="field" bind:value={f.raci.C} maxlength="500" /></label>
				<label>Informed<input class="field" bind:value={f.raci.I} maxlength="500" /></label>
			</fieldset>
		</div>

		<footer>
			{#if error}<p class="err" role="alert">{error}</p>{/if}
			<p class="note">Saved in Radar only and logged in Activity as {by || 'you'}. JIRA, OpenProject and Multica are not changed.</p>
			<div class="row">
				<button type="submit" class="btn dark" disabled={busy}>{busy ? 'Saving…' : isNew ? 'Add project' : 'Save changes'}</button>
				<button type="button" class="btn" onclick={onclose}>Cancel</button>
				{#if !isNew}
					{#if confirm}
						<button type="submit" class="btn danger" formaction="?/deleteProject" disabled={busy}>Yes, delete {f.id}</button>
						<button type="button" class="btn" onclick={() => (confirm = false)}>Keep it</button>
					{:else}
						<button type="button" class="btn quiet" onclick={() => (confirm = true)}>Delete</button>
					{/if}
				{/if}
			</div>
		</footer>
	</form>
</div>

<style>
	.scrim { position: fixed; inset: 0; background: rgba(17, 17, 17, 0.35); border: 0; padding: 0; z-index: 40; cursor: default; }
	.drawer { position: fixed; top: 12px; right: 12px; bottom: 12px; width: min(620px, calc(100vw - 24px)); background: #fff; border-radius: 28px; z-index: 41; box-shadow: 0 16px 48px rgba(17, 17, 17, 0.2); display: flex; flex-direction: column; overflow: hidden; }
	form { display: flex; flex-direction: column; min-height: 0; height: 100%; }
	header { display: flex; justify-content: space-between; align-items: flex-start; padding: 22px 28px 12px; gap: 12px; }
	.eyebrow { font-size: 12px; font-weight: 800; letter-spacing: 0.08em; color: #5b635d; text-transform: uppercase; }
	h2 { margin: 2px 0 0; font-size: 24px; letter-spacing: -0.02em; }
	.x { width: 44px; height: 44px; border-radius: 999px; border: 0; background: #f1f5f2; font-size: 24px; line-height: 1; cursor: pointer; }
	.body { flex: 1; min-height: 0; overflow-y: auto; padding: 4px 28px 16px; display: grid; grid-template-columns: 1fr 1fr; gap: 12px 14px; align-content: start; }
	label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 700; color: #3e4640; min-width: 0; }
	.wide { grid-column: 1 / -1; }
	.field { min-height: 44px; font-weight: 500; color: #111; width: 100%; box-sizing: border-box; }
	textarea.field { resize: vertical; padding-top: 10px; }
	fieldset { border: 1.5px solid #e3eae5; border-radius: 20px; padding: 10px 16px 14px; margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 10px 14px; }
	legend { font-size: 12px; font-weight: 700; color: #3e4640; padding: 0 6px; }
	footer { border-top: 1px solid #eef2ef; padding: 14px 28px 20px; display: flex; flex-direction: column; gap: 8px; }
	.note { margin: 0; font-size: 12px; color: #5b635d; }
	.err { margin: 0; font-size: 13px; font-weight: 700; color: #b02a2a; background: #f8cdd0; border-radius: 14px; padding: 8px 12px; }
	.row { display: flex; flex-wrap: wrap; gap: 8px; }
	.btn { min-height: 44px; padding: 0 20px; border-radius: 999px; border: 0; background: #f1f5f2; color: #111; font: 700 14px inherit; cursor: pointer; }
	.btn.dark { background: #111; color: #fff; } .btn.danger { background: #b02a2a; color: #fff; } .btn.quiet { background: transparent; text-decoration: underline; }
	.btn:disabled { opacity: 0.6; cursor: default; }
	@media (max-width: 560px) { .body, fieldset { grid-template-columns: 1fr; } .drawer { top: 0; right: 0; bottom: 0; width: 100vw; border-radius: 0; } }
</style>
