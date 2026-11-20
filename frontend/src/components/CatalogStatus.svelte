<script lang="ts">
  import { useCatalog } from '../lib/catalog.svelte';
  import { useUi } from '../lib/ui.svelte';
  const catalog = useCatalog();
  const ui = useUi();
</script>

{#if catalog.state.status === 'loading'}
  <p class="catalog-message" role="status">{ui.t('forge.models_loading')}</p>
{:else if catalog.state.status === 'error'}
  <p class="catalog-message catalog-error" role="alert">
    {ui.t(`forge.catalog_error_${catalog.state.error.code}`, { status: catalog.state.error.status })}
  </p>
{:else if catalog.models.length === 0}
  <p class="catalog-message" role="status">{ui.t('forge.models_empty')}</p>
{/if}
