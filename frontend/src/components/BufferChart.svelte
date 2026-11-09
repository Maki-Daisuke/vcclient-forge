<script lang="ts">
  import { bufferHistoryDurationMs, type BufferPoint } from '../lib/audio-meters.svelte';
  import { useUi } from '../lib/ui.svelte';

  let { input, output }: { input: BufferPoint[]; output: BufferPoint[] } = $props();
  const ui = useUi();
  const points = $derived([...input, ...output]);
  const last = $derived(points.length ? Math.max(...points.map(point => point.time)) : 0);
  const maximum = $derived(Math.max(0.05, ...points.map(point => point.seconds)) * 1.1);
  function coordinates(history: BufferPoint[]) {
    return history.map(point => `${(1 - (last - point.time) / bufferHistoryDurationMs) * 300},${80 - (point.seconds / maximum) * 80}`).join(' ');
  }
  function position(point: BufferPoint) {
    return { x: (1 - (last - point.time) / bufferHistoryDurationMs) * 300, y: 80 - (point.seconds / maximum) * 80 };
  }
</script>

<div class="buffer-chart" aria-hidden="true">
  {#if points.length}
    <svg viewBox="0 0 300 80" preserveAspectRatio="none">
      {#if input.length}<polyline class="buffer-input" points={coordinates(input)} /><circle class="buffer-input-point" cx={position(input[input.length - 1]).x} cy={position(input[input.length - 1]).y} r="2" />{/if}
      {#if output.length}<polyline class="buffer-output" points={coordinates(output)} /><circle class="buffer-output-point" cx={position(output[output.length - 1]).x} cy={position(output[output.length - 1]).y} r="2" />{/if}
    </svg>
    <span>{maximum.toFixed(3)} s</span>
  {:else}
    <span>—</span>
  {/if}
</div>
<div class="buffer-legend" aria-hidden="true">
  <span class="input-label">{ui.t('common.performance.input_buffer')}</span>
  <span class="output-label">{ui.t('common.performance.output_buffer')}</span>
</div>
