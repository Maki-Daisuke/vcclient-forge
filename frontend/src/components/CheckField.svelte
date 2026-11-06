<script lang="ts">
  let { label, checked = null, disabled = true, onchange }: { label: string; checked?: boolean | null; disabled?: boolean; onchange?: (value: boolean) => void } = $props();
</script>

<label class="check-field"><input type="checkbox" disabled={disabled || checked === null} checked={checked === true} indeterminate={checked === null} onchange={event => onchange?.(event.currentTarget.checked)} /><span>{label}</span></label>
