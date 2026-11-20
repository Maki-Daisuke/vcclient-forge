<script lang="ts">
  import { useCatalog } from '../lib/catalog.svelte';
  import { useUi } from '../lib/ui.svelte';
  import PendingIndicator from './PendingIndicator.svelte';
  let { label, id, direction, disabled = true, wasapiOnly = false, needsSelection = false, pending = false, onchange }: {
    label: string;
    id: number | null | undefined;
    direction: 'input' | 'output';
    disabled?: boolean;
    wasapiOnly?: boolean;
    needsSelection?: boolean;
    pending?: boolean;
    onchange?: (id: number) => void;
  } = $props();
  const catalog = useCatalog();
  const ui = useUi();
  const devices = $derived(catalog.deviceState.status === 'ready' ? catalog.deviceState.devices[direction] : []);
  const visibleDevices = $derived(wasapiOnly ? devices.filter(device => /wasapi/i.test(device.host)) : devices);
  const value = $derived.by(() => {
    if (id === null || id === undefined) return '—';
    if (id < 0) return ui.t('common.settings_dialog.unselected');
    const state = catalog.deviceState;
    if (state.status === 'ready') {
      const device = state.devices[direction].find(device => device.id === id);
      if (device) return device.host ? `${device.name} (${device.host})` : device.name;
    }
    const status = state.status === 'ready' ? 'missing' : state.status;
    return ui.t(`forge.device_${status}`, { id });
  });
</script>

<label class="select-field">
  <span>{label} {#if pending}<PendingIndicator />{/if}</span>
  <select value={id == null || needsSelection ? '' : String(id)} title={needsSelection ? ui.t('forge.device_reselect') : value}
    disabled={disabled || catalog.deviceState.status !== 'ready'}
    onchange={event => onchange?.(Number(event.currentTarget.value))}>
    {#if id == null || needsSelection}<option value="" disabled hidden>{needsSelection ? ui.t('common.settings_dialog.unselected') : '—'}</option>{/if}
    <option value="-1">{ui.t('common.settings_dialog.unselected')}</option>
    {#if id != null && id !== -1 && !visibleDevices.some(device => device.id === id)}
      <option value={String(id)} disabled>{value}</option>
    {/if}
    {#each visibleDevices as device (device.id)}
      <option value={String(device.id)}>{device.name}{device.host ? ` (${device.host})` : ''}</option>
    {/each}
  </select>
</label>
