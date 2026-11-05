<script lang="ts">
  import { useCatalog } from '../lib/catalog.svelte';
  import { useUi } from '../lib/ui.svelte';
  const catalog = useCatalog();
  const ui = useUi();
</script>

{#if catalog.state.status === 'loading'}
  <p class="catalog-message" role="status">{ui.t('forge.settings_loading')}</p>
{:else if catalog.state.status === 'error'}
  <p class="catalog-message" role="status">{ui.t('forge.settings_unavailable')}</p>
{/if}
