<script lang="ts">
  import DeviceField from './DeviceField.svelte';
  import CheckField from './CheckField.svelte';
  import PendingIndicator from './PendingIndicator.svelte';
  import { useCatalog } from '../lib/catalog.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
  const catalog = useCatalog();
  const settings = $derived(session.settings);
  let deviceError = $state(false);
  let showLegacy = $state(false);
  const windowsDevices = $derived(catalog.deviceState.status === 'ready' &&
    [...catalog.deviceState.devices.input, ...catalog.deviceState.devices.output]
      .some(device => /^windows\b/i.test(device.host) || /^mme$/i.test(device.host) || /wasapi/i.test(device.host)));

</script>

<fieldset class="mode-field" aria-label={ui.t('forge.mode')} disabled={!session.canConfigure || !settings?.inputMode}>
  <div class="segmented-control">
    <label><input type="radio" name="input-mode" value="server" checked={settings?.inputMode === 'server'}
      onchange={() => session.useServerMode()} /><span>{ui.t('common.controls.server_mode')} {#if !session.error && session.draft.inputMode === 'server'}<PendingIndicator />{/if}</span></label>
    <label><input type="radio" name="input-mode" value="client" checked={settings?.inputMode === 'client'} onchange={() => session.useClientMode()} /><span>{ui.t('common.settings_dialog.client_mode')} {#if !session.error && session.draft.inputMode === 'client'}<PendingIndicator />{/if}</span></label>
  </div>
  {#if !settings?.inputMode}<span class="muted">—</span>{/if}
</fieldset>
{#if settings?.inputMode === 'client'}
<section class="settings-section audio-device-section">
  <label class="select-field"><span>{ui.t('common.settings_dialog.input_device')}</span>
    <select bind:value={session.clientAudio.inputId} disabled={!session.canConfigure}>
      <option value="">{ui.t('forge.browser_default')}</option>
      {#each session.clientAudio.inputs as device (device.deviceId)}
        <option value={device.deviceId}>{device.label || ui.t('forge.browser_device')}</option>
      {/each}
    </select>
  </label>
  <label class="select-field"><span>{ui.t('common.settings_dialog.output_device')}</span>
    <select bind:value={session.clientAudio.outputId} disabled={!session.canConfigure || !session.clientAudio.canSelectOutput}>
      <option value="">{ui.t('forge.browser_default')}</option>
      {#each session.clientAudio.outputs as device (device.deviceId)}
        <option value={device.deviceId}>{device.label || ui.t('forge.browser_device')}</option>
      {/each}
    </select>
  </label>
  <div class="device-actions">
    <button class="button small" disabled={!session.canConfigure} onclick={async () => {
      deviceError = false;
      try { await session.clientAudio.requestDevices(); } catch { deviceError = true; }
    }}>{ui.t('forge.devices_rescan')}</button>
  </div>
  {#if deviceError}<p role="alert">{ui.t('forge.browser_devices_error')}</p>{/if}
  {#if !session.clientAudio.canSelectOutput}<p class="muted">{ui.t('forge.browser_output_default')}</p>{/if}
</section>
{:else}
<section class="settings-section audio-device-section">
  <DeviceField label={ui.t('common.settings_dialog.input_device')} id={settings?.inputDevice} direction="input"
    disabled={!session.canConfigure || settings?.inputMode !== 'server'} pending={!session.error && session.draft.inputDevice !== undefined} wasapiOnly={windowsDevices && !showLegacy} needsSelection={session.devicesNeedingSelection.includes('inputDevice')} onchange={id => session.selectDevice('inputDevice', id)} />
  <DeviceField label={ui.t('common.settings_dialog.output_device')} id={settings?.outputDevice} direction="output"
    disabled={!session.canConfigure || settings?.inputMode !== 'server'} pending={!session.error && session.draft.outputDevice !== undefined} wasapiOnly={windowsDevices && !showLegacy} needsSelection={session.devicesNeedingSelection.includes('outputDevice')} onchange={id => session.selectDevice('outputDevice', id)} />
  <DeviceField label={ui.t('common.settings_dialog.monitor_device')} id={settings?.monitorDevice} direction="output"
    disabled={!session.canConfigure || settings?.inputMode !== 'server'} pending={!session.error && session.draft.monitorDevice !== undefined} wasapiOnly={windowsDevices && !showLegacy} needsSelection={session.devicesNeedingSelection.includes('monitorDevice')} onchange={id => session.selectDevice('monitorDevice', id)} />
  <div class="device-actions">
    {#if windowsDevices}<CheckField label={ui.t('forge.show_legacy_devices')} checked={showLegacy} disabled={false} onchange={value => showLegacy = value} />{/if}
    <button class="button small" disabled={!session.canConfigure} onclick={() => session.rescanAudioDevices()}>{ui.t(session.deviceRescanning ? 'forge.devices_rescanning' : 'forge.devices_rescan')}</button>
  </div>
  {#if session.deviceRescanError}<p class="muted" role="alert">{ui.t('forge.devices_rescan_error')}</p>{/if}
  {#if settings?.wasapiExclusive === true}
    <p class="muted" role="status">{ui.t(session.active ? 'forge.wasapi_saved_running' : 'forge.wasapi_saved_stopped')}</p>
  {/if}
</section>
{/if}
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
  .device-actions { display: flex; flex-wrap: wrap; justify-content: flex-end; align-items: center; gap: 10px; }
  .device-actions :global(.check-field) { margin-block: 0; }
  .audio-device-section { padding-bottom: 0; margin-bottom: 0; }
</style>
