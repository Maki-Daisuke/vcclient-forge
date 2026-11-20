<script lang="ts">
  import { SlidersHorizontal, ScrollText, Info, ExternalLink, MessageSquarePlus } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import CheckField from './CheckField.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  import lucideLicense from '../../public/lucide-LICENSE.txt?raw';
  const ui = useUi();
  const session = useSession();
  let advancedOpen = $state(false);

  function openExternal(event: MouseEvent) {
    const href = (event.currentTarget as HTMLAnchorElement).href;
    const desktop = window as Window & { vcclientForge?: unknown; wails?: { Browser?: { OpenURL?: (url: string) => void } } };
    if (desktop.wails?.Browser?.OpenURL || desktop.vcclientForge) {
      event.preventDefault();
      window.open(href, '_blank', 'noopener,noreferrer');
    }
  }
</script>

<nav class="advanced-actions" aria-label={ui.t('common.advanced_area.advanced_settings')}>
  <PreviewDialog title={ui.t('common.advanced_settings_dialog.title')} bind:open={advancedOpen}>
    {#snippet trigger()}<SlidersHorizontal size={16} />{ui.t('common.advanced_area.advanced_settings')}{/snippet}
    <CheckField label={ui.t('forge.confirm_passthrough_setting')} checked={ui.confirmPassthrough} disabled={false}
      onchange={value => ui.confirmPassthrough = value} />
    <CheckField label={ui.t('forge.realtime_display')} checked={session.realtimeDisplayEnabled ?? false}
      mixed={session.realtimeDisplayEnabled === null} disabled={!session.canAdjustRealtimeDisplay}
      onchange={value => session.setRealtimeDisplay(value)} />
    {#if session.error}
      <p role="alert">{ui.t('forge.save_failed')} {ui.t(`forge.write_error_${session.error.code}`, { status: session.error.status })} {session.error.detail ?? ''}</p>
      <div class="button-row">
        <button class="button small" disabled={!!session.operation} onclick={() => session.retry()}>{ui.t('forge.retry_save')}</button>
        <button class="button small" disabled={!!session.operation} onclick={() => session.discard()}>{ui.t('forge.discard_changes')}</button>
      </div>
    {/if}
  </PreviewDialog>
  <button class="button" onclick={() => {
    const desktop = (window as Window & { vcclientForge?: { openLogWindow?: () => boolean } }).vcclientForge;
    if (!desktop?.openLogWindow?.()) window.open(`${location.pathname}?view=log`, 'vcclient-forge-log');
  }}><ScrollText size={16} />{ui.t('common.advanced_area.log')}</button>
  <PreviewDialog title={ui.t('forge.about')}>
    {#snippet trigger()}<Info size={16} />{ui.t('forge.about')}{/snippet}
    <h3>VCClient Forge <span class="about-version">v{__APP_VERSION__}</span></h3>
    <p class="muted">
      Forked from
      <a class="inline-link" href="https://github.com/w-okada/voice-changer" target="_blank" rel="noopener noreferrer"
        onclick={openExternal}>w-okada/voice-changer</a>
    </p>
    <div class="about-links">
      <a class="repo-link-card" href="https://github.com/Maki-Daisuke/vcclient-forge" target="_blank" rel="noopener noreferrer"
        onclick={openExternal}>
        <svg class="repo-link-icon" width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0 1 12 6.844a9.59 9.59 0 0 1 2.504.337c1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.02 10.02 0 0 0 22 12.017C22 6.484 17.522 2 12 2Z" />
        </svg>
        <span class="repo-link-text">
          <span class="repo-link-title">Project Page</span>
          <span class="repo-link-url">Maki-Daisuke/vcclient-forge</span>
        </span>
        <ExternalLink class="repo-link-external" size={16} aria-hidden="true" />
      </a>
      <a class="repo-link-card" href="https://github.com/Maki-Daisuke/vcclient-forge/issues" target="_blank" rel="noopener noreferrer"
        onclick={openExternal}>
        <MessageSquarePlus class="repo-link-icon" size={20} aria-hidden="true" />
        <span class="repo-link-text">
          <span class="repo-link-title">GitHub Issues</span>
          <span class="repo-link-url">{ui.t('forge.issue_description')}</span>
        </span>
        <ExternalLink class="repo-link-external" size={16} aria-hidden="true" />
      </a>
    </div>
    <h3>{ui.t('common.copyright.disclaimer')}</h3>
    <p class="muted">{ui.t('common.copyright.disclaimer_text')}</p>
    <details class="license-details">
      <summary>Lucide Icons — ISC License</summary>
      <pre>{lucideLicense}</pre>
    </details>
  </PreviewDialog>
</nav>

<style>
  .license-details { margin-top: 16px; }
  .license-details summary { cursor: pointer; }
  .license-details pre { max-height: 200px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; font-size: 0.8rem; }
</style>
