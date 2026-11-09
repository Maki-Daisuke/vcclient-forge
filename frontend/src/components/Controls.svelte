<script lang="ts">
  import { Play, Square, Circle, Repeat2, Volume2, AudioLines, Cpu, AudioWaveform } from '@lucide/svelte';
  import AudioSettings from './AudioSettings.svelte';
  import NoiseSettings from './NoiseSettings.svelte';
  import RangeField from './RangeField.svelte';
  import LogSlider from './LogSlider.svelte';
  import SelectField from './SelectField.svelte';
  import SettingsStatus from './SettingsStatus.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  import { displayNumber } from '../lib/settings';
  import { onDestroy } from 'svelte';
  import { AudioMeters } from '../lib/audio-meters.svelte';
  import BufferChart from './BufferChart.svelte';
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
  const meters = new AudioMeters();
  const settings = $derived(session.settings);
  const modelSettings = $derived(session.modelSettings);
  const showStop = $derived(session.active === true || (session.active === null && session.statusError));
  const startMessage = $derived(session.startBlockReason ? ui.t(`forge.start_block_${session.startBlockReason}`) : undefined);
  const showStartMessage = $derived(!showStop && !session.canStart && !!startMessage);
  $effect(() => {
    meters.setEnabled(session.active === true && settings?.inputMode === 'server', settings?.ioAnalysisEnabled === true,
      settings?.processAnalysisEnabled === true, settings?.ioAnalysisInterval ?? null, settings?.processAnalysisInterval ?? null);
  });
  onDestroy(() => meters.dispose());
  $effect(() => {
    if (session.recordingCompleted) {
      const link = document.createElement('a');
      link.href = '/output.wav';
      link.download = 'output.wav';
      link.click();
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
        <button class="button" aria-pressed={settings?.passThrough === true}
          disabled={!session.canAdjustGain || settings?.passThrough == null || settings.recording !== false || session.recordingArmed} onclick={() => session.togglePassThrough()}>
          <Repeat2 size={16} />{ui.t('common.controls.passthrough')}
        </button>
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
      {#each [{ key: 'input_volume', value: meters.levels?.input }, { key: 'output_volume', value: meters.levels?.output }] as meter}
        <div class="meter-label"><span>{ui.t(`common.controls.${meter.key}`)}</span><span>{meter.value === undefined ? '—' : meter.value.toFixed(3)}</span></div>
        <div class="meter" aria-hidden="true"><span style:transform={`scaleX(${Math.min(1, meter.value ?? 0)})`}></span></div>
      {/each}
      {#if session.active && settings?.ioAnalysisEnabled === false}<p class="muted">{ui.t('forge.meters_disabled')}</p>
      {:else if session.active && meters.status === 'unavailable'}<p class="muted">{ui.t('forge.meters_disconnected')}</p>{/if}
      <BufferChart input={meters.inputHistory} output={meters.outputHistory} />
      <dl>
        <div><dt>{ui.t('common.performance.input_buffer')}</dt><dd>{meters.inputBuffer === null ? '—' : `${meters.inputBuffer.toFixed(3)} s`}</dd></div>
        <div><dt>{ui.t('common.performance.output_buffer')}</dt><dd>{meters.outputBuffer === null ? '—' : `${meters.outputBuffer.toFixed(3)} s`}</dd></div>
      </dl>
      <button class="button small" disabled={!meters.inputHistory.length && !meters.outputHistory.length} onclick={() => meters.clearHistory()}>{ui.t('common.performance.clear')}</button>
      {#if session.active && (settings?.processAnalysisEnabled === false || settings?.performanceMonitorEnabled === false)}<p class="muted">{ui.t('forge.input_buffer_disabled')}</p>{/if}
    </section>
  </aside>
  <section class="controls-column" aria-label={ui.t('common.controls.title')}>
    <SettingsStatus />
    <details class="control-group input-section" use:initializeSection={'input'} ontoggle={event => saveSection('input', event)}>
      <summary><AudioLines size={17} />{ui.t('forge.input_output')}</summary>
      <div class="control-group-body"><AudioSettings /></div>
    </details>
    <details class="control-group" use:initializeSection={'volume'} ontoggle={event => saveSection('volume', event)}>
      <summary><Volume2 size={17} />{ui.t('common.controls.volume_control')}</summary>
      <div class="control-group-body">
        <RangeField label={ui.t('common.controls.input_volume')} value={settings?.inputGain ?? null} step={0.01}
          disabled={!session.canAdjustGain} onchange={value => session.setGain('inputGain', value)} oncommit={() => session.flush()} />
        <RangeField label={ui.t('common.controls.output_volume')} value={settings?.outputGain ?? null} step={0.01}
          disabled={!session.canAdjustGain} onchange={value => session.setGain('outputGain', value)} oncommit={() => session.flush()} />
      </div>
    </details>
    <details class="control-group noise-section" use:initializeSection={'noise'} ontoggle={event => saveSection('noise', event)}>
      <summary><AudioWaveform size={17} />{ui.t('common.settings_dialog.noise_suppression')}</summary>
      <div class="control-group-body"><NoiseSettings /></div>
    </details>
    <details class="control-group" use:initializeSection={'inference'} ontoggle={event => saveSection('inference', event)}>
      <summary><Cpu size={17} />{ui.t('forge.inference_settings')}</summary>
      <div class="control-group-body">
        <SelectField label={ui.t('forge.preferred_device')} value={settings?.gpuDevice === null || settings?.gpuDevice === undefined ? '—' : settings.gpuDevice < 0 ? 'CPU' : ui.t('forge.gpu_id', { id: settings.gpuDevice })} />
        <div class="field-grid">
          <LogSlider label={ui.t('forge.chunk_frames')} value={modelSettings?.chunkSeconds ?? null} min={0.05} max={5}
            disabled={!session.canConfigure || settings?.inputMode !== 'server' || session.currentModel?.status !== 'ready'} oncommit={value => session.setChunkSeconds(value)} />
          <LogSlider label={ui.t('forge.extra_frames')} value={settings?.extraSeconds ?? null} min={0.01} max={10}
            disabled={!session.canConfigure || settings?.inputMode !== 'server'} oncommit={value => session.setExtraSeconds(value)} />
          <LogSlider label={ui.t('forge.crossfade')} value={settings?.crossfadeSeconds ?? null} min={0.01} max={0.15} allowZero
            disabled={!session.canConfigure || settings?.inputMode !== 'server'} oncommit={value => session.setCrossfadeSeconds(value)} />
        </div>
      </div>
    </details>
  </section>
</div>
