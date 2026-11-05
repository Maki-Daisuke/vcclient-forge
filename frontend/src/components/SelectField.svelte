<script lang="ts">
  let { label, value, ariaLabel }: { label: string; value: string; ariaLabel?: string } = $props();
</script>

<label class="select-field"><span>{label}</span><select disabled title={value} aria-label={ariaLabel}><option>{value}</option></select></label>
