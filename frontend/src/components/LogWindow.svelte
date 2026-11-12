<script lang="ts">
  import { onMount } from 'svelte';
  import { provideUi } from '../lib/ui.svelte';
  const ui = provideUi();
  let content = $state('');
  let loading = $state(false);
  let error = $state(false);
  let controller: AbortController | undefined;

  async function refresh() {
    if (loading) return;
    loading = true;
    error = false;
    controller = new AbortController();
    try {
      const response = await fetch('/vcclient.log', { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      content = await response.text();
    } catch {
      if (!controller.signal.aborted) error = true;
    } finally { loading = false; }
  }
  onMount(() => { void refresh(); return () => controller?.abort(); });
  $effect(() => {
    document.documentElement.lang = ui.language;
    document.documentElement.dir = ui.language === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.dataset.theme = ui.theme;
    document.title = `${ui.t('common.advanced_area.log')} · VCClient Forge`;
  });
</script>

<main class="log-window">
  <header class="log-header"><h1>{ui.t('common.advanced_area.log')}</h1><button class="button" disabled={loading} onclick={refresh}>{ui.t('forge.log_refresh')}</button></header>
  {#if loading}<p role="status">{ui.t('forge.log_loading')}</p>{/if}
  {#if error}<p role="alert">{ui.t('forge.log_fetch_error')}</p>{/if}
  <pre class="log-content">{content || (!loading && !error ? ui.t('forge.log_no_entries') : '')}</pre>
</main>

<style>
  .log-window { padding: 20px; display: flex; flex-direction: column; height: 100dvh; gap: 12px; }
  .log-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .log-content { flex: 1; min-height: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
</style>
