<script lang="ts">
  import { Slider } from 'bits-ui';
  import { useUi } from '../lib/ui.svelte';
  import { displayNumber } from '../lib/settings';

  let { label, value, min, max, allowZero = false, disabled = true, oncommit }: { label: string; value: number | null; min: number; max: number; allowZero?: boolean; disabled?: boolean; oncommit?: (value: number) => void } = $props();
  const ui = useUi();
  let preview = $state<number | null>(null);
  let interacting = false;
  let keyboardActive = false;
  const displayed = $derived(preview ?? value);
  const clamped = $derived(displayed === null ? min : Math.min(max, Math.max(min, displayed)));
  const position = $derived(allowZero && displayed === 0 ? 0 : Math.round((allowZero ? 1 : 0) + (allowZero ? 999 : 1000) * Math.log(clamped / min) / Math.log(max / min)));
  const outOfRange = $derived(displayed !== null && !(allowZero && displayed === 0) && (displayed < min || displayed > max));
  function commit() {
    interacting = false;
    keyboardActive = false;
    if (preview !== null) oncommit?.(preview);
    preview = null;
  }
</script>

<div class="range-field log-slider">
  <div class="range-label"><span>{label}</span><output>{displayNumber(displayed, ' s')}</output></div>
  <Slider.Root type="single" value={position} min={0} max={1000} step={1} disabled={disabled || value === null} class="slider"
    onValueChange={value => { if (interacting) preview = allowZero && value === 0 ? 0 : Number((min * (max / min) ** ((value - (allowZero ? 1 : 0)) / (allowZero ? 999 : 1000))).toFixed(3)); }}
    onValueCommit={() => { if (!keyboardActive) commit(); }}
    onpointerdowncapture={() => { interacting = true; }} onkeydowncapture={() => { keyboardActive = true; interacting = true; }}
    onkeyup={commit} onfocusout={commit}>
    <span class="slider-track"><Slider.Range class="slider-range" /></span>
    <Slider.Thumb index={0}>
      {#snippet child({ props })}
        <span {...props} class="slider-thumb" aria-label={label}
          aria-valuemin={allowZero ? 0 : min} aria-valuemax={max} aria-valuenow={allowZero && displayed === 0 ? 0 : clamped} aria-valuetext={displayNumber(displayed, ' s')}></span>
      {/snippet}
    </Slider.Thumb>
  </Slider.Root>
  <div class="range-limits" aria-hidden="true"><span>{allowZero ? 0 : min}</span><span>{max}</span></div>
  {#if outOfRange}<p class="muted">{ui.t('forge.slider_range_hint')}</p>{/if}
</div>
