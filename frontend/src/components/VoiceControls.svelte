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
    <fieldset class="radio-field estimator-field" disabled={estimatorDisabled}>
      <legend class="visually-hidden">{ui.t('common.voice_controls.pitch_estimator')}</legend>
      <h3>{ui.t('common.voice_controls.pitch_estimator')} {#if !session.error && session.modelDraft?.edits.pitchEstimator !== undefined}<PendingIndicator />{/if}</h3>
      {#each ['rmvpe', 'fcpe'] as estimator}
        <label><input type="radio" name="pitch-estimator" value={estimator} checked={modelSettings?.pitchEstimator === estimator}
          onchange={() => session.setPitchEstimator(estimator as 'rmvpe' | 'fcpe')} />{estimator.toUpperCase()}</label>
      {/each}
      {#if !modelSettings?.pitchEstimator}<span class="muted">—</span>{/if}
    </fieldset>
    {#if estimatorDisabled}<span id="pitch-estimator-reason" class="start-tooltip" role="tooltip">{ui.t(estimatorReason)}</span>{/if}
  </div>
  <div class="field-grid">
    <!-- svelte-ignore a11y_no_noninteractive_tabindex: The disabled group must be focusable to expose its tooltip. -->
    <div class="model-range-wrapper start-button-wrapper" role={modelSettings && !modelSettings.supportsPitch ? 'group' : undefined}
      aria-label={modelSettings && !modelSettings.supportsPitch ? ui.t('common.controls.pitch_adjust') : undefined}
      tabindex={modelSettings && !modelSettings.supportsPitch ? 0 : undefined}
      aria-describedby={modelSettings && !modelSettings.supportsPitch ? 'pitch-adjust-reason' : undefined}>
      <RangeField label={ui.t('common.controls.pitch_adjust')} heading value={modelSettings?.pitch ?? null} min={-24} max={24} step={1}
        disabled={!session.canAdjustModel || !modelSettings?.supportsPitch}
        onchange={value => session.setModelValue('pitch', value)} oncommit={() => session.flush()} />
      {#if modelSettings && !modelSettings.supportsPitch}<span id="pitch-adjust-reason" class="start-tooltip" role="tooltip">{ui.t('forge.pitch_unavailable')}</span>{/if}
    </div>
    <!-- svelte-ignore a11y_no_noninteractive_tabindex: The disabled group must be focusable to expose its tooltip. -->
    <div class="model-range-wrapper start-button-wrapper" role={modelSettings && !modelSettings.hasIndex ? 'group' : undefined}
      aria-label={modelSettings && !modelSettings.hasIndex ? ui.t('forge.index_rate') : undefined}
      tabindex={modelSettings && !modelSettings.hasIndex ? 0 : undefined}
      aria-describedby={modelSettings && !modelSettings.hasIndex ? 'index-rate-reason' : undefined}>
      <RangeField label={ui.t('forge.index_rate')} heading value={modelSettings?.indexRatio == null ? null : Math.round(modelSettings.indexRatio * 100)} max={100} step={1} unit="%"
        disabled={!session.canAdjustModel || !modelSettings?.hasIndex}
        onchange={value => session.setModelValue('indexRatio', value / 100)} oncommit={() => session.flush()} />
      {#if modelSettings && !modelSettings.hasIndex}<span id="index-rate-reason" class="start-tooltip" role="tooltip">{ui.t('forge.index_unavailable')}</span>{/if}
    </div>
  </div>
</section>
<style>
  .estimator-wrapper, .model-range-wrapper { display: block; min-width: 0; }
  .estimator-field { align-items: center; }
  .estimator-wrapper:focus-visible, .model-range-wrapper:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
</style>
