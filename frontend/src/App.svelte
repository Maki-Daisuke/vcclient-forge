<script lang="ts">
  import { Sun, Moon, AudioLines } from '@lucide/svelte';
  import { onMount } from 'svelte';
  import Models from './components/Models.svelte';
  import Controls from './components/Controls.svelte';
  import Advanced from './components/Advanced.svelte';
  import ConfigurationStatus from './components/ConfigurationStatus.svelte';
  import { provideUi, languages } from './lib/ui.svelte';
  import { provideCatalog } from './lib/catalog.svelte';
  import { provideSession } from './lib/session.svelte';
  const ui = provideUi();
  const catalog = provideCatalog();
  const session = provideSession(catalog);

  onMount(() => {
    void session.mount();
    return () => session.dispose();
  });

  $effect(() => {
    document.documentElement.lang = ui.language;
    document.documentElement.dir = ui.language === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.dataset.theme = ui.theme;
  });
</script>

<div class="app-shell">
  <header class="app-header">
    <div class="brand"><AudioLines size={29} /><h1>VCClient <span>Forge</span></h1><span class="preview-badge">{ui.t('forge.preview')}</span></div>
    <div class="header-actions">
      <select aria-label={ui.t('forge.language')} bind:value={ui.language}>
        {#each languages as [code, name]}<option value={code}>{name}</option>{/each}
      </select>
      <button class="icon-button" aria-label={ui.t('forge.theme')} onclick={() => ui.theme = ui.theme === 'light' ? 'dark' : 'light'}>
        {#if ui.theme === 'light'}<Moon size={20} />{:else}<Sun size={20} />{/if}
      </button>
    </div>
  </header>
  <main>
    <ConfigurationStatus />
    <Models />
    <section class="panel conversion-panel"><Controls /></section>
    <Advanced />
  </main>
</div>
