<script lang="ts">
  import { useCatalog } from '../lib/catalog.svelte';
  import { useSession } from '../lib/session.svelte';
  import { useUi } from '../lib/ui.svelte';

  const catalog = useCatalog();
  const session = useSession();
  const ui = useUi();
  const id = $derived(session.settings?.gpuDevice ?? null);
  const state = $derived(catalog.computeDeviceState);
  const devices = $derived(state.status === 'ready' ? state.devices : []);
  const value = $derived.by(() => {
    if (id === null) return '—';
    const device = devices.find(item => item.id === id);
    if (device) return device.name;
    const status = state.status === 'ready' ? 'missing' : state.status;
    return ui.t(`forge.device_${status}`, { id });
  });
</script>

<label class="select-field">
  <span>{ui.t('forge.preferred_device')}</span>
  <select value={id === null ? '' : String(id)} title={session.active === true ? undefined : value}
    disabled={!session.canConfigure || !session.settings?.inputMode || id === null || state.status !== 'ready'}
    onchange={event => session.selectComputeDevice(Number(event.currentTarget.value))}>
    {#if id === null}<option value="" disabled>—</option>{/if}
    {#if id !== null && !devices.some(device => device.id === id)}<option value={String(id)} disabled>{value}</option>{/if}
    {#each devices as device (device.id)}<option value={String(device.id)}>{device.name}</option>{/each}
  </select>
</label>
