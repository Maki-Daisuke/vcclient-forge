<script lang="ts">
  import RangeField from './RangeField.svelte';
  import PendingIndicator from './PendingIndicator.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
  const modelSettings = $derived(session.modelSettings);
  const estimatorDisabled = $derived(!session.canConfigure || !session.settings?.inputMode || !modelSettings?.supportsPitch || !modelSettings?.pitchEstimator);
  const estimatorReason = $derived(modelSettings && !modelSettings.supportsPitch ? 'forge.pitch_unavailable'
    : session.active === true ? 'forge.pitch_estimator_stopped' : 'forge.pitch_estimator_unavailable');
</script>

<section class="voice-settings" aria-label={ui.t('common.controls.voice_control')}>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex: The disabled group must be focusable to expose its tooltip. -->
  <div class="estimator-wrapper start-button-wrapper" role="group" aria-label={ui.t('common.voice_controls.pitch_estimator')}
    tabindex={estimatorDisabled ? 0 : undefined} aria-describedby={estimatorDisabled ? 'pitch-estimator-reason' : undefined}>
    <fieldset class="radio-field" disabled={estimatorDisabled}>
      <legend><h3>{ui.t('common.voice_controls.pitch_estimator')} {#if !session.error && session.modelDraft?.edits.pitchEstimator !== undefined}<PendingIndicator />{/if}</h3></legend>
      {#each ['rmvpe', 'fcpe'] as estimator}
        <label><input type="radio" name="pitch-estimator" value={estimator} checked={modelSettings?.pitchEstimator === estimator}
          onchange={() => session.setPitchEstimator(estimator as 'rmvpe' | 'fcpe')} />{estimator.toUpperCase()}</label>
      {/each}
      {#if !modelSettings?.pitchEstimator}<span class="muted">—</span>{/if}
    </fieldset>
    {#if estimatorDisabled}<span id="pitch-estimator-reason" class="start-tooltip" role="tooltip">{ui.t(estimatorReason)}</span>{/if}
  </div>
  <RangeField label={ui.t('common.controls.pitch_adjust')} heading value={modelSettings?.pitch ?? null} min={-24} max={24} step={1}
    disabled={!session.canAdjustModel || !modelSettings?.supportsPitch}
    onchange={value => session.setModelValue('pitch', value)} oncommit={() => session.flush()} />
  {#if modelSettings && !modelSettings.supportsPitch}<p class="muted">{ui.t('forge.pitch_unavailable')}</p>{/if}
  <RangeField label={ui.t('forge.index_rate')} heading hint={modelSettings && !modelSettings.hasIndex ? ui.t('forge.index_unavailable') : undefined} value={modelSettings?.indexRatio == null ? null : Math.round(modelSettings.indexRatio * 100)} max={100} step={1} unit="%"
    disabled={!session.canAdjustModel || !modelSettings?.hasIndex}
    onchange={value => session.setModelValue('indexRatio', value / 100)} oncommit={() => session.flush()} />
</section>
<style>
  .estimator-wrapper { display: block; }
  .estimator-wrapper:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
