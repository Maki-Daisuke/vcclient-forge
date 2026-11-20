<script lang="ts">
  import { Slider } from 'bits-ui';

  let { label, value, disabled = true, onchange, oncommit }: {
    label: string; value: number | null; disabled?: boolean;
    onchange?: (value: number) => void; oncommit?: () => void;
  } = $props();

  // log1p keeps zero reachable and places unity near the middle of the track.
  const scale = Math.log1p(90);
  const position = $derived(value === null ? 0 : Math.round(1000 * Math.log1p(9 * Math.max(0, Math.min(10, value))) / scale));
  let interacting = false;
  let keyboardActive = false;

  function handleKey(event: KeyboardEvent) {
    if (disabled || value === null) return;
    let next: number;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowUp': next = value + 0.01; break;
      case 'ArrowLeft':
      case 'ArrowDown': next = value - 0.01; break;
      case 'Home': next = 0; break;
      case 'End': next = 10; break;
      default: return;
    }
    event.preventDefault();
    event.stopPropagation();
    keyboardActive = true;
    interacting = true;
    onchange?.(Number(Math.min(10, Math.max(0, next)).toFixed(2)));
  }

  function finish() {
    if (!interacting) return;
    keyboardActive = false;
    interacting = false;
    oncommit?.();
  }
</script>

<div class="range-field">
  <div class="range-label"><span>{label}</span><output>{value === null ? '—' : value.toFixed(2)}</output></div>
  <Slider.Root type="single" value={position} min={0} max={1000} step={1} disabled={disabled || value === null}
    onValueChange={position => { if (interacting && !keyboardActive) onchange?.(Number((Math.expm1(position * scale / 1000) / 9).toFixed(2))); }}
    class="slider" aria-label={label} onValueCommit={() => { if (!keyboardActive) finish(); }}
    onpointerdowncapture={() => { interacting = true; }} onkeydowncapture={handleKey}
    onkeyup={finish} onfocusout={finish}>
    <span class="slider-track"><Slider.Range class="slider-range" /></span>
    <Slider.Thumb index={0}>
      {#snippet child({ props })}
        <span {...props} class="slider-thumb" aria-label={label} aria-valuemin={0} aria-valuemax={10}
          aria-valuenow={value ?? 0} aria-valuetext={value === null ? '—' : value.toFixed(2)}></span>
      {/snippet}
    </Slider.Thumb>
  </Slider.Root>
  <div class="range-limits" aria-hidden="true"><span>0</span><span>10</span></div>
</div>
