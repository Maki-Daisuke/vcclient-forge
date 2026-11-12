<script lang="ts">
  import { Play, Square, Circle, Repeat2, Volume2, AudioLines, Cpu, AudioWaveform } from '@lucide/svelte';
  import { Dialog } from 'bits-ui';
  import AudioSettings from './AudioSettings.svelte';
  import NoiseSettings from './NoiseSettings.svelte';
  import RangeField from './RangeField.svelte';
  import CheckField from './CheckField.svelte';
  import LogSlider from './LogSlider.svelte';
  import ComputeDeviceField from './ComputeDeviceField.svelte';
  import InferenceSetting from './InferenceSetting.svelte';
  import SettingsStatus from './SettingsStatus.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  import { useCatalog } from '../lib/catalog.svelte';
  import { computeDeviceLabel } from '../lib/compute-device';
  import { displayNumber } from '../lib/settings';
  import { onDestroy } from 'svelte';
  import { AudioMeters, bufferHistoryDurationMs, levelMeterFraction, type BufferPoint } from '../lib/audio-meters.svelte';
  import BufferChart from './BufferChart.svelte';
  function accessibleLevel(value: number | undefined): string {
    if (value === undefined) return '—';
    if (value === 0) return '−∞ dBFS';
    return `${(20 * Math.log10(value)).toFixed(1)} dBFS`;
  }
  const sectionNames = ['input', 'noise', 'volume', 'inference'] as const;
  type SectionName = typeof sectionNames[number];
  const storageKey = 'vcclient-forge.control-sections.v1';
  function loadSections(): Record<SectionName, boolean> {
    const closed = Object.fromEntries(sectionNames.map(name => [name, false])) as Record<SectionName, boolean>;
    try {
      const value: unknown = JSON.parse(localStorage.getItem(storageKey) ?? 'null');
      if (!value || typeof value !== 'object' || Array.isArray(value)) return closed;
      for (const name of sectionNames) {
        if (typeof (value as Record<string, unknown>)[name] === 'boolean') closed[name] = (value as Record<string, boolean>)[name];
      }
    } catch {
      // Storage may be unavailable or contain invalid data; start with all sections closed.
    }
    return closed;
  }
  const sections = loadSections();
  function initializeSection(node: HTMLDetailsElement, name: SectionName) {
    node.open = sections[name];
  }
  function saveSection(name: SectionName, event: Event) {
    sections[name] = (event.currentTarget as HTMLDetailsElement).open;
    try {
      localStorage.setItem(storageKey, JSON.stringify(sections));
    } catch {
      // Keep the current page usable when browser storage is unavailable.
    }
  }
  const ui = useUi();
  const session = useSession();
  const catalog = useCatalog();
  let passthroughConfirmOpen = $state(false);
  let passthroughCancel: HTMLButtonElement | undefined = $state();
  const meters = new AudioMeters();
  let clientLevels = $state<{ input: number; output: number } | null>(null);
  let clientOutputBuffer = $state<number | null>(null);
  let clientOutputHistory = $state<BufferPoint[]>([]);
  const settings = $derived(session.settings);
  const computeDevice = $derived(computeDeviceLabel(settings?.gpuDevice ?? null, catalog.computeDeviceState,
    (key, options) => ui.t(key, options)));
  const outputBuffer = $derived(settings?.inputMode === 'client' ? clientOutputBuffer : meters.outputBuffer);
  const modelSettings = $derived(session.modelSettings);
  const showStop = $derived(session.active === true || (session.active === null && session.statusError));
  const startMessage = $derived(session.startBlockReason ? ui.t(`forge.start_block_${session.startBlockReason}`) : undefined);
  const showStartMessage = $derived(!showStop && !session.canStart && !!startMessage);
  $effect(() => {
    meters.setEnabled(session.active === true, settings?.inputMode === 'server' && settings?.ioAnalysisEnabled === true,
      settings?.processAnalysisEnabled === true && settings?.performanceMonitorEnabled === true, settings?.ioAnalysisInterval ?? null,
      settings?.processAnalysisInterval ?? null, modelSettings?.chunkSeconds ?? null);
  });
  $effect(() => {
    if (session.active !== true || settings?.inputMode !== 'client' || session.realtimeDisplayEnabled !== true) {
      clientLevels = null;
      clientOutputBuffer = null;
      clientOutputHistory = [];
      return;
    }
    const sample = () => {
      const value = session.clientAudio.readMeters();
      if (!value) {
        clientLevels = null;
        clientOutputBuffer = null;
        clientOutputHistory = [];
        return;
      }
      clientLevels = { input: value.input, output: value.output };
      clientOutputBuffer = value.outputBuffer;
      const now = Date.now();
      clientOutputHistory = [...clientOutputHistory.filter(point => point.time >= now - bufferHistoryDurationMs),
        { time: now, seconds: value.outputBuffer }].slice(-200);
    };
    const timer = setInterval(sample, 100);
    return () => clearInterval(timer);
  });
  onDestroy(() => meters.dispose());
  $effect(() => {
    if (session.recordingCompleted) {
      const link = document.createElement('a');
      const url = URL.createObjectURL(session.recordingCompleted);
      link.href = url;
      link.download = 'output.wav';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 60_000);
    }
  });
</script>

<div class="conversion-layout">
  <aside class="monitor-column">
    <div class="transport-block">
      <div class="transport-row">
        <span class="start-button-wrapper">
          <button class="button" class:primary={!showStop} class:running={session.active === true} aria-disabled={showStop ? !session.canStop : !session.canStart}
            aria-describedby={showStartMessage ? 'start-reason' : undefined}
            onclick={() => session.operate(showStop ? 'stop' : 'start')}>
            {#if showStop}<Square size={16} fill="currentColor" />{ui.t('common.controls.stop')}{:else}<Play size={17} />{ui.t('common.controls.start')}{/if}
          </button>
          {#if showStartMessage}<span id="start-reason" class="start-tooltip" role="tooltip">{startMessage}</span>{/if}
        </span>
        <Dialog.Root bind:open={passthroughConfirmOpen}>
          <Dialog.Trigger class="button" aria-pressed={settings?.passThrough === true} disabled={!session.canTogglePassThrough}
            onclick={(event: MouseEvent) => { if (settings?.passThrough === true || !ui.confirmPassthrough) { event.preventDefault(); session.togglePassThrough(); } }}>
            <Repeat2 size={16} />{ui.t('common.controls.passthrough')}
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay class="dialog-overlay" />
            <Dialog.Content class="dialog-content delete-confirm-dialog" onOpenAutoFocus={event => { event.preventDefault(); passthroughCancel?.focus(); }}>
              <header class="dialog-header"><Dialog.Title class="dialog-title">{ui.t('forge.passthrough_confirm')}</Dialog.Title></header>
              <div class="dialog-body"><Dialog.Description>{ui.t('forge.passthrough_confirm_description')}</Dialog.Description></div>
              <footer class="dialog-footer">
                <button class="button primary action-primary" disabled={!session.canTogglePassThrough || settings?.passThrough !== false}
                  onclick={() => { if (session.canTogglePassThrough && settings?.passThrough === false) session.togglePassThrough(); passthroughConfirmOpen = false; }}>{ui.t('forge.enable')}</button>
                <button class="button" bind:this={passthroughCancel} onclick={() => passthroughConfirmOpen = false}>{ui.t('forge.cancel')}</button>
              </footer>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        <button class="button recording-button" class:recording-armed={session.recordingArmed && settings?.recording !== true}
          aria-label={ui.t('common.controls.record')} aria-pressed={settings?.recording === true || session.recordingArmed} disabled={!session.canToggleRecording} onclick={() => session.toggleRecording()}>
          {#if settings?.recording}<Square size={14} fill="currentColor" />{:else}<Circle size={14} />{/if}{ui.t(settings?.recording ? 'forge.recording_active' : session.recordingArmed ? 'forge.recording_armed' : 'common.controls.record')}
        </button>
      </div>
      {#if session.operation}<p class="operation-status" role="status">{ui.t(`forge.audio_${session.operation}`)}</p>{/if}
      {#if session.operationError}
        <p class="catalog-message" role="alert">{ui.t('forge.operation_failed')} {ui.t(`forge.write_error_${session.operationError.code}`, { status: session.operationError.status })} {session.operationError.detail ?? ''}</p>
      {/if}
      {#if session.statusError}<p class="catalog-message" role="status">{ui.t('forge.audio_status_error')}</p>{/if}
    </div>
    <section class="performance" aria-label={ui.t('common.advanced_settings_dialog.realtime_analysis_settings')}>
      {#each [{ key: 'input_volume', value: settings?.inputMode === 'client' ? clientLevels?.input : meters.levels?.input }, { key: 'output_volume', value: settings?.inputMode === 'client' ? clientLevels?.output : meters.levels?.output }] as meter}
        <div class="meter-label">{ui.t(`common.controls.${meter.key}`)}<span class="visually-hidden">{accessibleLevel(meter.value)}</span></div>
        <div class="meter" aria-hidden="true"><span style:--empty={`${(1 - levelMeterFraction(meter.value ?? 0)) * 100}%`}></span></div>
        <div class="meter-scale" aria-hidden="true"><span>−60</span><span>−40</span><span>−20</span><span>0 dBFS</span></div>
      {/each}
      {#if session.active && settings?.inputMode === 'server' && settings?.ioAnalysisEnabled === true && meters.status === 'unavailable'}<p class="muted">{ui.t('forge.meters_disconnected')}</p>{/if}
      <BufferChart input={meters.inputHistory} output={settings?.inputMode === 'client' ? clientOutputHistory : meters.outputHistory} chunkSeconds={modelSettings?.chunkSeconds ?? null} />
      <dl>
        <div><dt>{ui.t('common.performance.input_buffer')}</dt><dd>{meters.inputBuffer === null ? '—' : `${meters.inputBuffer.toFixed(3)} s`}</dd></div>
        <div><dt>{ui.t('common.performance.output_buffer')}</dt><dd>{outputBuffer === null ? '—' : `${outputBuffer.toFixed(3)} s`}</dd></div>
        <div><dt>{ui.t('forge.conversion_time')}</dt><dd>{meters.conversionTimeSeconds === null ? '—' : `${meters.conversionTimeSeconds.toFixed(3)} s`}</dd></div>
      </dl>
      <button class="button small" disabled={!meters.inputHistory.length && !meters.outputHistory.length && !clientOutputHistory.length} onclick={() => { meters.clearHistory(); clientOutputHistory = []; }}>{ui.t('common.performance.clear')}</button>
    </section>
  </aside>
  <section class="controls-column" aria-label={ui.t('common.controls.title')}>
    <SettingsStatus />
    <details class="control-group inference-section" use:initializeSection={'inference'} ontoggle={event => saveSection('inference', event)}>
      <summary><Cpu size={17} />{ui.t('forge.inference_settings')}<span class="control-group-summary-value" title={computeDevice}>{computeDevice}</span></summary>
      <div class="control-group-body">
        <InferenceSetting label={ui.t('forge.preferred_device')}><ComputeDeviceField /></InferenceSetting>
        <div class="field-grid">
          <InferenceSetting label={ui.t('forge.chunk_frames')}><LogSlider label={ui.t('forge.chunk_frames')} value={modelSettings?.chunkSeconds ?? null} min={0.05} max={5}
            disabled={!session.canConfigure || !settings?.inputMode || session.currentModel?.status !== 'ready'} oncommit={value => session.setChunkSeconds(value)} /></InferenceSetting>
          <InferenceSetting label={ui.t('forge.extra_frames')}><LogSlider label={ui.t('forge.extra_frames')} value={settings?.extraSeconds ?? null} min={0.01} max={10}
            disabled={!session.canConfigure || !settings?.inputMode} oncommit={value => session.setExtraSeconds(value)} /></InferenceSetting>
        </div>
      </div>
    </details>
    <details class="control-group input-section" use:initializeSection={'input'} ontoggle={event => saveSection('input', event)}>
      <summary><AudioLines size={17} />{ui.t('forge.input_output')}<span class="control-group-summary-value">{settings?.inputMode === 'server' ? ui.t('common.controls.server_mode') : settings?.inputMode === 'client' ? ui.t('common.settings_dialog.client_mode') : '—'}</span></summary>
      <div class="control-group-body"><AudioSettings /></div>
    </details>
    <details class="control-group" use:initializeSection={'volume'} ontoggle={event => saveSection('volume', event)}>
      <summary><Volume2 size={17} />{ui.t('common.controls.volume_control')}</summary>
      <div class="control-group-body">
        {#if settings?.inputMode === 'client'}
          <CheckField label={ui.t('forge.auto_gain_control')} checked={session.clientAudio.autoGainControl}
            disabled={!session.canConfigure || (!session.clientAudio.supportsOption('autoGainControl') && !session.clientAudio.autoGainControl)}
            tooltip={session.active === true ? ui.t('forge.client_processing_stopped') : undefined}
            onchange={value => session.clientAudio.setOption('autoGainControl', value)} />
        {/if}
        <RangeField label={ui.t('common.controls.input_volume')} value={settings?.inputMode === 'client' ? session.clientAudio.inputGain : settings?.inputGain ?? null} step={0.01}
          disabled={!session.canAdjustGain || (settings?.inputMode === 'client' && session.clientAudio.autoGainControl)} onchange={value => session.setGain('inputGain', value)} oncommit={() => session.flush()} />
        <RangeField label={ui.t('common.controls.output_volume')} value={settings?.inputMode === 'client' ? session.clientAudio.outputGain : settings?.outputGain ?? null} step={0.01}
          disabled={!session.canAdjustGain} onchange={value => session.setGain('outputGain', value)} oncommit={() => session.flush()} />
      </div>
    </details>
    <details class="control-group noise-section" use:initializeSection={'noise'} ontoggle={event => saveSection('noise', event)}>
      <summary><AudioWaveform size={17} />{ui.t('common.settings_dialog.noise_suppression')}</summary>
      <div class="control-group-body"><NoiseSettings /></div>
    </details>
  </section>
</div>
