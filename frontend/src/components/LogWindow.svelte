<script lang="ts">
  import { onMount, tick } from 'svelte';
  import { provideUi } from '../lib/ui.svelte';
  const ui = provideUi();
  let content = $state('');
  let loading = $state(false);
  let error = $state(false);
  let controller: AbortController | undefined;
  let logContent: HTMLPreElement | undefined = $state();
  let inFlight = $state(false);
  let loaded = false;

  async function refresh(manual = false) {
    if (inFlight) return;
    inFlight = true;
    loading = manual || !loaded;
    controller = new AbortController();
    try {
      const response = await fetch('/vcclient.log', { cache: 'no-store', signal: controller.signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const next = await response.text();
      if (controller.signal.aborted) return;
      const follow = !content || !logContent || logContent.scrollHeight - logContent.scrollTop - logContent.clientHeight <= 8;
      content = next;
      loaded = true;
      error = false;
      if (follow) {
        await tick();
        if (logContent) logContent.scrollTop = logContent.scrollHeight;
      }
    } catch {
      if (!controller.signal.aborted) error = true;
    } finally { loading = false; inFlight = false; }
  }
  onMount(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    return () => { clearInterval(timer); controller?.abort(); };
  });
  $effect(() => {
    document.documentElement.lang = ui.language;
    document.documentElement.dir = ui.language === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.dataset.theme = ui.theme;
    document.title = `${ui.t('common.advanced_area.log')} · VCClient Forge`;
  });
</script>

<main class="log-window">
  <header class="log-header"><h1>{ui.t('common.advanced_area.log')}</h1><button class="button" disabled={inFlight} onclick={() => refresh(true)}>{ui.t('forge.log_refresh')}</button></header>
  {#if loading}<p role="status">{ui.t('forge.log_loading')}</p>{/if}
  {#if error}<p role="alert">{ui.t('forge.log_fetch_error')}</p>{/if}
  <pre class="log-content" bind:this={logContent}>{content || (!loading && !error ? ui.t('forge.log_no_entries') : '')}</pre>
</main>

<style>
  .log-window { padding: 20px; display: flex; flex-direction: column; height: 100dvh; gap: 12px; }
  .log-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .log-content { flex: 1; min-height: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px; border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
</style>
