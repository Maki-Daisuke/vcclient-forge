<script lang="ts">
  import { Slider } from 'bits-ui';

  let { label, value, min = 0, max = 10, step = 0.1, unit = '', heading = false, hint, disabled = true, onchange, oncommit }: {
    label: string; value: number | null; min?: number; max?: number; step?: number;
    unit?: string; heading?: boolean; hint?: string;
    disabled?: boolean; onchange?: (value: number) => void; oncommit?: () => void;
  } = $props();
  let keyboardActive = false;
  let interacting = false;
</script>

<div class="range-field">
  <div class="range-label">
    <div class="range-label-text">
      {#if heading}<h3>{label}</h3>{:else}<span>{label}</span>{/if}
      {#if hint}<span class="muted">{hint}</span>{/if}
    </div>
    <output>{value === null ? '—' : `${value.toFixed(step < 1 ? 2 : 0)}${unit}`}</output>
  </div>
  <Slider.Root type="single" value={value ?? 0} {min} {max} {step} disabled={disabled || value === null}
    onValueChange={value => { if (interacting) onchange?.(value); }} class="slider" aria-label={label}
    onValueCommit={() => { if (!keyboardActive) { interacting = false; oncommit?.(); } }}
    onpointerdowncapture={() => { interacting = true; }}
    onkeydowncapture={() => { keyboardActive = true; interacting = true; }}
    onkeyup={() => { keyboardActive = false; interacting = false; oncommit?.(); }}
    onfocusout={() => { keyboardActive = false; interacting = false; oncommit?.(); }}>
    <span class="slider-track"><Slider.Range class="slider-range" /></span>
    <Slider.Thumb index={0} class="slider-thumb" aria-label={label} aria-valuetext={value === null ? '—' : `${value}${unit}`} />
  </Slider.Root>
  <div class="range-limits" aria-hidden="true"><span>{min}</span><span>{max}</span></div>
</div>
