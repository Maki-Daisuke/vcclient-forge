<script lang="ts">
  import RangeField from './RangeField.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
  const modelSettings = $derived(session.modelSettings);
</script>

<section class="voice-settings" aria-label={ui.t('common.controls.voice_control')}>
  <RangeField label={ui.t('common.controls.pitch_adjust')} heading value={modelSettings?.pitch ?? null} min={-24} max={24} step={1}
    disabled={!session.canAdjustModel || !modelSettings?.supportsPitch}
    onchange={value => session.setModelValue('pitch', value)} oncommit={() => session.flush()} />
  {#if modelSettings && !modelSettings.supportsPitch}<p class="muted">{ui.t('forge.pitch_unavailable')}</p>{/if}
  <RangeField label={ui.t('forge.index_rate')} heading hint={modelSettings && !modelSettings.hasIndex ? ui.t('forge.index_unavailable') : undefined} value={modelSettings?.indexRatio ?? null} max={1} step={0.01}
    disabled={!session.canAdjustModel || !modelSettings?.hasIndex}
    onchange={value => session.setModelValue('indexRatio', value)} oncommit={() => session.flush()} />
  <fieldset class="radio-field" disabled>
    <legend><h3>{ui.t('common.voice_controls.pitch_estimator')}</h3></legend>
    {#each ['rmvpe', 'fcpe'] as estimator}
      <label><input type="radio" name="pitch-estimator" value={estimator} checked={modelSettings?.pitchEstimator === estimator} />{estimator.toUpperCase()}</label>
    {/each}
    {#if !modelSettings?.pitchEstimator}<span class="muted">—</span>{/if}
  </fieldset>
  <p class="muted">{ui.t('forge.pitch_estimator_readonly')}</p>
</section>
