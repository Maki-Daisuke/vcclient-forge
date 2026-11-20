<script lang="ts">
  import { useUi } from '../lib/ui.svelte';
  const ui = useUi();
</script>

<span class="pending-indicator" role="status" title={ui.t('forge.applying')}>
  <span class="pending-spinner" aria-hidden="true"></span>
  <span class="visually-hidden">{ui.t('forge.applying')}</span>
</span>
