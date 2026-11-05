<script lang="ts">
  import { Play, Square, Mic, FileAudio, Monitor, Circle, Repeat2, Volume2, SlidersHorizontal } from '@lucide/svelte';
  import SettingsDialog from './SettingsDialog.svelte';
  import RangeField from './RangeField.svelte';
  import SelectField from './SelectField.svelte';
  import DeviceField from './DeviceField.svelte';
  import ModelImage from './ModelImage.svelte';
  import SettingsStatus from './SettingsStatus.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useCatalog } from '../lib/catalog.svelte';
  import { displayNumber } from '../lib/settings';
  const ui = useUi();
  const catalog = useCatalog();
  const settings = $derived(catalog.settings);
  const modelSettings = $derived(catalog.currentModel?.settings);
</script>

<div class="conversion-layout">
  <aside class="portrait-column" aria-label={ui.t('common.voice.character')}>
    <div class="portrait">
      {#if catalog.currentModel}
        <ModelImage src={catalog.currentModel.imageUrl} alt={catalog.currentModel.name} />
      {:else}
        <span class="muted">{ui.t('common.model.not_selected')}</span>
      {/if}
    </div>
    <span class="status"><span class="status-dot"></span>{ui.t('forge.controls_preview')}</span>
    <section class="performance" aria-label={ui.t('common.advanced_settings_dialog.realtime_analysis_settings')}>
      {#each ['input_volume', 'output_volume'] as key}
        <div class="meter-label"><span>{ui.t(`common.controls.${key}`)}</span><span>0.000</span></div>
        <div class="meter" role="meter" aria-label={ui.t(`common.controls.${key}`)} aria-valuenow="0" aria-valuemin="0" aria-valuemax="1"><span></span></div>
      {/each}
      <div class="buffer-chart" aria-hidden="true"><span>0.00 s</span></div>
      <dl>
        <div><dt>{ui.t('common.performance.input_buffer')}</dt><dd>0.00 s</dd></div>
        <div><dt>{ui.t('common.performance.output_buffer')}</dt><dd>0.00 s</dd></div>
      </dl>
      <button class="button small" disabled>{ui.t('common.performance.clear')}</button>
    </section>
  </aside>
  <section class="controls-column" aria-label={ui.t('common.controls.title')}>
    <SettingsStatus />
    <div class="transport-row">
      <button class="button primary" disabled><Play size={17} />{ui.t('common.controls.start')}</button>
      <button class="button" disabled><Square size={16} />{ui.t('common.controls.stop')}</button>
      <button class="button" disabled><Repeat2 size={16} />{ui.t('common.controls.passthrough')}</button>
      <span class="spacer"></span><SettingsDialog />
    </div>
    <div class="input-section">
      <div class="section-heading compact">
        <h3>{ui.t('common.controls.input_type')}</h3>
        <span class="tag">{settings?.inputMode ? ui.t(`common.controls.${settings.inputMode}_mode`) : '—'}</span>
      </div>
      <div class="button-row input-types">
        <button class="button" disabled><Mic size={16} />{ui.t('common.controls.microphone')}</button>
        <button class="button" disabled><FileAudio size={16} />{ui.t('common.controls.file')}</button>
        <button class="button" disabled><Monitor size={16} />{ui.t('common.controls.capture')}</button>
        <button class="button" disabled><Circle size={14} />{ui.t('common.controls.record')}</button>
      </div>
      <DeviceField label={ui.t('common.controls.mic_device')} id={settings?.inputDevice} direction="input" />
    </div>
    <details class="control-group" open>
      <summary><Volume2 size={17} />{ui.t('common.controls.volume_control')}</summary>
      <div class="control-group-body">
        <RangeField label={ui.t('common.controls.input_volume')} value={settings?.inputGain ?? null} step={0.01} />
        <RangeField label={ui.t('common.controls.output_volume')} value={settings?.outputGain ?? null} step={0.01} />
        <RangeField label={ui.t('common.controls.monitor_volume')} value={settings?.monitorGain ?? null} step={0.01} />
      </div>
    </details>
    <details class="control-group" open>
      <summary><SlidersHorizontal size={17} />{ui.t('common.controls.voice_control')}</summary>
      <div class="control-group-body">
        <RangeField label={ui.t('common.controls.pitch_adjust')} value={modelSettings?.pitch ?? null} min={-24} max={24} step={1} />
        <RangeField label={ui.t('common.controls.formant_adjust')} value={null} min={-2} max={2} step={0.1} />
        <RangeField label={ui.t('common.controls.index_adjust')} value={modelSettings?.indexRatio ?? null} max={1} step={0.01} />
        <div class="field-grid">
          <SelectField label={ui.t('common.voice_controls.pitch_estimator')} value={modelSettings?.pitchEstimator ?? '—'} />
          <SelectField label={ui.t('common.voice_controls.embedder')} value={modelSettings?.embedder ?? '—'} />
          <SelectField label={ui.t('common.controls.chunksec_adjust')} value={displayNumber(modelSettings?.chunkSeconds, ' s')} />
          <SelectField label={ui.t('common.controls.extraframe_adjust')} value={displayNumber(settings?.extraSeconds, ' s')} />
        </div>
      </div>
    </details>
  </section>
</div>
