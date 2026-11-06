<script lang="ts">
  import SelectField from './SelectField.svelte';
  import DeviceField from './DeviceField.svelte';
  import CheckField from './CheckField.svelte';
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

<fieldset class="mode-field" aria-label={ui.t('forge.mode')} disabled={!session.canConfigure || !settings?.inputMode}>
  <div class="segmented-control">
    <label><input type="radio" name="input-mode" value="server" checked={settings?.inputMode === 'server'}
      onchange={() => session.useServerMode()} /><span>{ui.t('common.controls.server_mode')}</span></label>
    <label><input type="radio" name="input-mode" value="client" checked={settings?.inputMode === 'client'} disabled /><span>{ui.t('common.settings_dialog.client_mode')}</span></label>
  </div>
  {#if !settings?.inputMode}<span class="muted">—</span>{/if}
</fieldset>
<p class="muted">{ui.t('forge.client_mode_unavailable')}</p>
<section class="settings-section">
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
<style>
  .mode-field { border: 0; padding: 8px 0; margin: 0; min-width: 0; }
  .segmented-control { display: flex; width: 100%; padding: 4px; border-radius: 7px; background: var(--surface-soft); }
  .segmented-control label { position: relative; flex: 1 1 0; min-width: 0; }
  .segmented-control input { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .segmented-control span { display: block; padding: 10px 12px; border-radius: 5px; color: var(--text); font-size: .9rem; font-weight: 600; text-align: center; overflow-wrap: anywhere; cursor: pointer; }
  .segmented-control input:checked + span { background: var(--segment-selected); color: var(--segment-selected-text); }
  .segmented-control input:disabled + span { color: var(--disabled); cursor: not-allowed; }
  .segmented-control input:checked:disabled + span { background: var(--segment-selected); color: var(--segment-selected-text); }
  .segmented-control input:focus-visible + span { outline: 3px solid var(--accent); outline-offset: 2px; }
  .device-row { display: grid; grid-template-columns: minmax(0, 1fr) 160px; align-items: end; gap: 12px; }
  @media (max-width: 400px) { .device-row { grid-template-columns: 1fr; gap: 0; } }
</style>
