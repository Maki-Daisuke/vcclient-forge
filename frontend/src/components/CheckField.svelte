<script lang="ts">
  let { label, checked = null }: { label: string; checked?: boolean | null } = $props();
</script>

<label class="check-field"><input type="checkbox" disabled checked={checked === true} indeterminate={checked === null} /><span>{label}</span></label>
