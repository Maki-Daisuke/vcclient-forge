<script lang="ts">
  let { label, value }: { label: string; value: string } = $props();
</script>

<label class="select-field"><span>{label}</span><select disabled><option>{value}</option></select></label>
