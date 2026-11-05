<script lang="ts">
  import { Play, Square, Mic, FileAudio, Monitor, Circle, Repeat2, Volume2, SlidersHorizontal } from '@lucide/svelte';
  import SettingsDialog from './SettingsDialog.svelte';
  import RangeField from './RangeField.svelte';
  import SelectField from './SelectField.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { preview } from '../lib/preview';
  const ui = useUi();
</script>

<div class="conversion-layout">
  <aside class="portrait-column" aria-label={ui.t('common.voice.character')}>
    <div class="portrait"><img src={preview.portraitUrl} alt={ui.t('forge.sample_model')} /></div>
    <span class="status"><span class="status-dot"></span>{ui.t('forge.idle')}</span>
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
    <div class="transport-row">
      <button class="button primary" disabled><Play size={17} />{ui.t('common.controls.start')}</button>
      <button class="button" disabled><Square size={16} />{ui.t('common.controls.stop')}</button>
      <button class="button" disabled><Repeat2 size={16} />{ui.t('common.controls.passthrough')}</button>
      <span class="spacer"></span><SettingsDialog />
    </div>
    <div class="input-section">
      <div class="section-heading compact">
        <h3>{ui.t('common.controls.input_type')}</h3>
        <span class="tag">{ui.t('common.controls.server_mode')}</span>
      </div>
      <div class="button-row input-types">
        <button class="button" disabled><Mic size={16} />{ui.t('common.controls.microphone')}</button>
        <button class="button" disabled><FileAudio size={16} />{ui.t('common.controls.file')}</button>
        <button class="button" disabled><Monitor size={16} />{ui.t('common.controls.capture')}</button>
        <button class="button" disabled><Circle size={14} />{ui.t('common.controls.record')}</button>
      </div>
      <SelectField label={ui.t('common.controls.mic_device')} value={ui.t('common.settings_dialog.unselected')} />
    </div>
    <details class="control-group" open>
      <summary><Volume2 size={17} />{ui.t('common.controls.volume_control')}</summary>
      <div class="control-group-body">
        {#each preview.volume as field (field.key)}<RangeField label={ui.t(field.label)} value={field.value} />{/each}
      </div>
    </details>
    <details class="control-group" open>
      <summary><SlidersHorizontal size={17} />{ui.t('common.controls.voice_control')}</summary>
      <div class="control-group-body">
        {#each preview.voice as field (field.key)}<RangeField label={ui.t(field.label)} value={field.value} min={field.min} max={field.max} step={field.step} />{/each}
        <div class="field-grid">
          <SelectField label={ui.t('common.voice_controls.pitch_estimator')} value="RMVPE" />
          <SelectField label={ui.t('common.voice_controls.embedder')} value="ContentVec" />
          <SelectField label={ui.t('common.controls.chunksec_adjust')} value="0.25 s" />
          <SelectField label={ui.t('common.controls.extraframe_adjust')} value="1.36 s" />
        </div>
      </div>
    </details>
  </section>
</div>
