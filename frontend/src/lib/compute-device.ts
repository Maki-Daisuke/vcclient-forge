import type { ComputeDeviceState } from './catalog.svelte';

export function computeDeviceLabel(
  id: number | null,
  state: ComputeDeviceState,
  translate: (key: string, options: { id: number }) => string,
): string {
  if (id === null) return '—';
  const device = state.status === 'ready' ? state.devices.find(item => item.id === id) : undefined;
  if (device) return device.name;
  const status = state.status === 'ready' ? 'missing' : state.status;
  return translate(`forge.device_${status}`, { id });
}
