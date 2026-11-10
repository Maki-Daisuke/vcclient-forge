<script lang="ts">
  let { label, ariaLabel, checked = null, disabled = true, tooltip, onchange }: { label: string; ariaLabel?: string; checked?: boolean | null; disabled?: boolean; tooltip?: string; onchange?: (value: boolean) => void } = $props();
  const tooltipId = $props.id();
</script>

{#snippet field()}
  <label class="check-field"><input type="checkbox" aria-label={ariaLabel} disabled={disabled || checked === null} checked={checked === true} indeterminate={checked === null} onchange={event => onchange?.(event.currentTarget.checked)} /><span>{label}</span></label>
{/snippet}
{#if tooltip}
  <!-- svelte-ignore a11y_no_noninteractive_tabindex: The disabled control's explanation must be keyboard accessible. -->
  <span class="start-button-wrapper" role="group" aria-label={ariaLabel ?? label} aria-describedby={tooltipId} tabindex="0">
    {@render field()}
    <span id={tooltipId} class="start-tooltip" role="tooltip">{tooltip}</span>
  </span>
{:else}
  {@render field()}
{/if}
