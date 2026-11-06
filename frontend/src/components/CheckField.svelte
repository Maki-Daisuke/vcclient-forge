<script lang="ts">
  let { label, ariaLabel, checked = null, disabled = true, onchange }: { label: string; ariaLabel?: string; checked?: boolean | null; disabled?: boolean; onchange?: (value: boolean) => void } = $props();
</script>

<label class="check-field"><input type="checkbox" aria-label={ariaLabel} disabled={disabled || checked === null} checked={checked === true} indeterminate={checked === null} onchange={event => onchange?.(event.currentTarget.checked)} /><span>{label}</span></label>
