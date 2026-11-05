<script lang="ts">
  import { Sun, Moon, AudioLines, Info } from '@lucide/svelte';
  import Models from './components/Models.svelte';
  import Controls from './components/Controls.svelte';
  import Advanced from './components/Advanced.svelte';
  import { provideUi, languages } from './lib/ui.svelte';
  const ui = provideUi();

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
    <p class="preview-banner"><Info size={17} />{ui.t('forge.preview_description')}</p>
    <Models />
    <section class="panel conversion-panel"><Controls /></section>
    <Advanced />
  </main>
  <footer class="app-footer"><span>VCClient Forge</span><span>Based on w-okada/voice-changer · v2.1.4 UI</span></footer>
</div>
