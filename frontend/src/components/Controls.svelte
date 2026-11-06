<script lang="ts">
  import { Play, Square, Mic, FileAudio, Monitor, Circle, Repeat2, Volume2, SlidersHorizontal } from '@lucide/svelte';
  import SettingsDialog from './SettingsDialog.svelte';
  import RangeField from './RangeField.svelte';
  import SelectField from './SelectField.svelte';
  import DeviceField from './DeviceField.svelte';
  import ModelImage from './ModelImage.svelte';
  import SettingsStatus from './SettingsStatus.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  import { displayNumber } from '../lib/settings';
  const ui = useUi();
  const session = useSession();
  const settings = $derived(session.settings);
  const modelSettings = $derived(session.currentModel?.settings);
  const startMessage = $derived(session.startBlockReason ? ui.t(`forge.start_block_${session.startBlockReason}`) : undefined);
</script>

<div class="conversion-layout">
  <aside class="portrait-column" aria-label={ui.t('common.voice.character')}>
    <div class="portrait">
      {#if session.currentModel}
        <ModelImage src={session.currentModel.imageUrl} alt={session.currentModel.name} />
      {:else}
        <span class="muted">{ui.t('common.model.not_selected')}</span>
      {/if}
    </div>
    <span class="status" role="status"><span class="status-dot" class:active={session.active === true}></span>{ui.t(`forge.audio_${session.operation ?? (session.active === null ? 'unknown' : session.active ? 'running' : 'stopped')}`)}</span>
    <section class="performance" aria-label={ui.t('common.advanced_settings_dialog.realtime_analysis_settings')}>
      {#each ['input_volume', 'output_volume'] as key}
        <div class="meter-label"><span>{ui.t(`common.controls.${key}`)}</span><span>—</span></div>
        <div class="meter" aria-hidden="true"><span></span></div>
      {/each}
      <div class="buffer-chart" aria-hidden="true"><span>—</span></div>
      <dl>
        <div><dt>{ui.t('common.performance.input_buffer')}</dt><dd>—</dd></div>
        <div><dt>{ui.t('common.performance.output_buffer')}</dt><dd>—</dd></div>
      </dl>
      <button class="button small" disabled>{ui.t('common.performance.clear')}</button>
      <p class="muted">{ui.t('forge.telemetry_unavailable')}</p>
    </section>
  </aside>
  <section class="controls-column" aria-label={ui.t('common.controls.title')}>
    <SettingsStatus />
    <div class="transport-row">
      <button class="button primary" disabled={!session.canStart} title={startMessage}
        aria-describedby={startMessage && session.active !== true ? 'start-reason' : undefined}
        onclick={() => session.operate('start')}><Play size={17} />{ui.t('common.controls.start')}</button>
      <button class="button" disabled={!session.canStop} onclick={() => session.operate('stop')}><Square size={16} />{ui.t('common.controls.stop')}</button>
      <button class="button" disabled><Repeat2 size={16} />{ui.t('common.controls.passthrough')}</button>
      <span class="spacer"></span><SettingsDialog />
    </div>
    {#if session.operationError}
      <p class="catalog-message" role="alert">{ui.t('forge.operation_failed')} {ui.t(`forge.write_error_${session.operationError.code}`, { status: session.operationError.status })} {session.operationError.detail ?? ''}</p>
    {/if}
    {#if session.statusError}<p class="catalog-message" role="status">{ui.t('forge.audio_status_error')}</p>{/if}
    {#if startMessage && session.active !== true}<p id="start-reason" class="muted" role="status">{startMessage}</p>{/if}
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
      <DeviceField label={ui.t('common.controls.mic_device')} id={settings?.inputDevice} direction="input"
        disabled={!session.canConfigure || settings?.inputMode !== 'server'} onchange={id => session.selectDevice('inputDevice', id)} />
    </div>
    <details class="control-group" open>
      <summary><Volume2 size={17} />{ui.t('common.controls.volume_control')}</summary>
      <div class="control-group-body">
        <RangeField label={ui.t('common.controls.input_volume')} value={settings?.inputGain ?? null} step={0.01}
          disabled={!session.canAdjustGain} onchange={value => session.setGain('inputGain', value)} oncommit={() => session.flush()} />
        <RangeField label={ui.t('common.controls.output_volume')} value={settings?.outputGain ?? null} step={0.01}
          disabled={!session.canAdjustGain} onchange={value => session.setGain('outputGain', value)} oncommit={() => session.flush()} />
        <RangeField label={ui.t('common.controls.monitor_volume')} value={settings?.inputMode === 'server' ? settings.outputGain : settings?.monitorGain ?? null} step={0.01} />
        <p class="muted">{ui.t('forge.monitor_follows_output')}</p>
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
