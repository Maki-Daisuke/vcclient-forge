<script lang="ts">
  import { Slider } from 'bits-ui';
  import { useUi } from '../lib/ui.svelte';
  import { displayNumber } from '../lib/settings';

  let { label, value, min, max }: { label: string; value: number | null; min: number; max: number } = $props();
  const ui = useUi();
  const clamped = $derived(value === null ? min : Math.min(max, Math.max(min, value)));
  const position = $derived(Math.round(1000 * Math.log(clamped / min) / Math.log(max / min)));
  const outOfRange = $derived(value !== null && (value < min || value > max));
</script>

<div class="range-field log-slider">
  <div class="range-label"><span>{label}</span><output>{displayNumber(value, ' s')}</output></div>
  <Slider.Root type="single" value={position} min={0} max={1000} step={1} disabled class="slider">
    <span class="slider-track"><Slider.Range class="slider-range" /></span>
    <Slider.Thumb index={0}>
      {#snippet child({ props })}
        <span {...props} class="slider-thumb" aria-label={label}
          aria-valuemin={min} aria-valuemax={max} aria-valuenow={clamped} aria-valuetext={displayNumber(value, ' s')}></span>
      {/snippet}
    </Slider.Thumb>
  </Slider.Root>
  <div class="range-limits" aria-hidden="true"><span>{min}</span><span>{max}</span></div>
  {#if outOfRange}<p class="muted">{ui.t('forge.slider_range_hint')}</p>{/if}
</div>
