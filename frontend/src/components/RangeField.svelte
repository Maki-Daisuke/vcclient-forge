<script lang="ts">
  import { Slider } from 'bits-ui';

  let { label, value, min = 0, max = 10, step = 0.1, disabled = true, onchange, oncommit }: {
    label: string; value: number | null; min?: number; max?: number; step?: number;
    disabled?: boolean; onchange?: (value: number) => void; oncommit?: () => void;
  } = $props();
  let keyboardActive = false;
</script>

<div class="range-field">
  <div class="range-label"><span>{label}</span><output>{value === null ? '—' : value.toFixed(step < 1 ? 2 : 0)}</output></div>
  <Slider.Root type="single" value={value ?? 0} {min} {max} {step} disabled={disabled || value === null}
    onValueChange={onchange} class="slider" aria-label={label}
    onValueCommit={() => { if (!keyboardActive) oncommit?.(); }}
    onkeydowncapture={() => { keyboardActive = true; }}
    onkeyup={() => { keyboardActive = false; oncommit?.(); }}
    onfocusout={() => { keyboardActive = false; oncommit?.(); }}>
    <span class="slider-track"><Slider.Range class="slider-range" /></span>
    <Slider.Thumb index={0} class="slider-thumb" aria-label={label} aria-valuetext={value === null ? '—' : String(value)} />
  </Slider.Root>
  <div class="range-limits" aria-hidden="true"><span>{min}</span><span>{max}</span></div>
</div>
