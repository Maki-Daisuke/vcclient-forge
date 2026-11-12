<script lang="ts">
  import { useCatalog } from '../lib/catalog.svelte';
  import { useSession } from '../lib/session.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { computeDeviceLabel } from '../lib/compute-device';

  const catalog = useCatalog();
  const session = useSession();
  const ui = useUi();
  const id = $derived(session.settings?.gpuDevice ?? null);
  const state = $derived(catalog.computeDeviceState);
  const devices = $derived(state.status === 'ready' ? state.devices : []);
  const value = $derived(computeDeviceLabel(id, state, (key, options) => ui.t(key, options)));
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
