<script lang="ts">
  import { Slider } from 'bits-ui';

  let { label, value, min = 0, max = 10, step = 0.1 }: {
    label: string; value: number; min?: number; max?: number; step?: number;
  } = $props();
</script>

<div class="range-field">
  <div class="range-label"><span>{label}</span><output>{value.toFixed(step < 1 ? 2 : 0)}</output></div>
  <Slider.Root type="single" {value} {min} {max} {step} disabled class="slider" aria-label={label}>
    <span class="slider-track"><Slider.Range class="slider-range" /></span>
    <Slider.Thumb index={0} class="slider-thumb" aria-label={label} />
  </Slider.Root>
  <div class="range-limits" aria-hidden="true"><span>{min}</span><span>{max}</span></div>
</div>
