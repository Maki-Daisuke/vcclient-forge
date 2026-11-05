<script lang="ts">
  import SelectField from './SelectField.svelte';
  import { useCatalog } from '../lib/catalog.svelte';
  import { useUi } from '../lib/ui.svelte';
  let { label, id, direction }: {
    label: string;
    id: number | null | undefined;
    direction: 'input' | 'output';
  } = $props();
  const catalog = useCatalog();
  const ui = useUi();
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

<SelectField {label} {value} />
