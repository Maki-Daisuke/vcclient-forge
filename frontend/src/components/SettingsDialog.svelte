<script lang="ts">
  import { Settings } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import SelectField from './SelectField.svelte';
  import RangeField from './RangeField.svelte';
  import DeviceField from './DeviceField.svelte';
  import CheckField from './CheckField.svelte';
  import SettingsStatus from './SettingsStatus.svelte';
  import ConfigurationStatus from './ConfigurationStatus.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  import { displayNumber } from '../lib/settings';
  const ui = useUi();
  const session = useSession();
  const settings = $derived(session.settings);

  function rateLabel(rate: number | null | undefined) {
    return rate === null || rate === undefined ? '—' : rate < 0
      ? ui.t('common.settings_dialog.auto') : displayNumber(rate, ' Hz');
  }
</script>

<PreviewDialog title={ui.t('common.settings_dialog.title')} description={ui.t('forge.settings_readonly')}>
  {#snippet trigger()}<Settings size={16} />{ui.t('common.controls.settings')}{/snippet}
  <SettingsStatus />
  <ConfigurationStatus />
  <SelectField label={ui.t('common.settings_dialog.voice_changer_input_mode')} value={settings?.inputMode ? ui.t(`common.settings_dialog.${settings.inputMode}_mode`) : '—'} />
  {#if settings?.inputMode === 'client'}
    <button class="button" disabled={!session.canConfigure} onclick={() => session.useServerMode()}>{ui.t('forge.use_server_mode')}</button>
  {/if}
  <p class="muted">{ui.t('forge.device_edit_hint')}</p>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.audio_device_settings')}</h3>
    <div class="device-row">
      <DeviceField label={ui.t('common.settings_dialog.input_device')} id={settings?.inputDevice} direction="input"
        disabled={!session.canConfigure || settings?.inputMode !== 'server'} onchange={id => session.selectDevice('inputDevice', id)} />
      <SelectField label={ui.t('forge.sample_rate')} ariaLabel={ui.t('forge.input_device_rate')} value={rateLabel(settings?.inputDeviceRate)} />
    </div>
    <div class="device-row">
      <DeviceField label={ui.t('common.settings_dialog.output_device')} id={settings?.outputDevice} direction="output"
        disabled={!session.canConfigure || settings?.inputMode !== 'server'} onchange={id => session.selectDevice('outputDevice', id)} />
      <SelectField label={ui.t('forge.sample_rate')} ariaLabel={ui.t('forge.output_device_rate')} value={rateLabel(settings?.outputDeviceRate)} />
    </div>
    <div class="device-row">
      <DeviceField label={ui.t('common.settings_dialog.monitor_device')} id={settings?.monitorDevice} direction="output"
        disabled={!session.canConfigure || settings?.inputMode !== 'server'} onchange={id => session.selectDevice('monitorDevice', id)} />
      <SelectField label={ui.t('forge.sample_rate')} ariaLabel={ui.t('forge.monitor_device_rate')} value={rateLabel(settings?.monitorDeviceRate)} />
    </div>
    <CheckField label={ui.t('common.settings_dialog.wasapi_exclusive_mode')} checked={settings?.wasapiExclusive ?? null} />
  </section>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.gpu_settings')}</h3>
    <SelectField label={ui.t('common.settings_dialog.gpu_settings')} value={settings?.gpuDevice === null || settings?.gpuDevice === undefined ? '—' : settings.gpuDevice < 0 ? 'CPU' : ui.t('forge.gpu_id', { id: settings.gpuDevice })} />
  </section>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.noise_suppression')}</h3>
    {#each ['enable_echo_cancellation', 'enable_noise_suppression', 'enable_noise_suppression2'] as key}
      <CheckField label={ui.t(`common.settings_dialog.${key}`)} />
    {/each}
    <p class="muted">{ui.t('forge.browser_settings_unavailable')}</p>
  </section>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.noise_gate')}</h3>
    <RangeField label={ui.t('forge.noise_gate_threshold')} value={settings?.noiseGate ?? null} min={-120} max={0} step={1} unit=" dB"
      disabled={!session.canAdjustGain} onchange={value => session.setNoiseGate(value)} oncommit={() => session.flush()} />
    <p class="muted">{ui.t('forge.noise_gate_disabled_hint')}</p>
    <CheckField label={ui.t('common.settings_dialog.enable_high_pass_filter')} checked={settings?.highPassEnabled ?? null} />
    <SelectField label={ui.t('forge.high_pass_cutoff')} value={displayNumber(settings?.highPassCutoff, ' Hz')} />
    <CheckField label={ui.t('common.settings_dialog.enable_low_pass_filter')} checked={settings?.lowPassEnabled ?? null} />
    <SelectField label={ui.t('forge.low_pass_cutoff')} value={displayNumber(settings?.lowPassCutoff, ' Hz')} />
  </section>
</PreviewDialog>

<style>
  .device-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 160px;
    align-items: end;
    gap: 12px;
  }

  @media (max-width: 400px) {
    .device-row { grid-template-columns: 1fr; gap: 0; }
  }
</style>
