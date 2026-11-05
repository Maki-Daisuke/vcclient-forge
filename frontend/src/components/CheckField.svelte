<script lang="ts">
  let { label, checked = false }: { label: string; checked?: boolean } = $props();
</script>

<label class="check-field"><input type="checkbox" disabled {checked} /><span>{label}</span></label>
