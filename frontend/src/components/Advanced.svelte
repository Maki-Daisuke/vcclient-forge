<script lang="ts">
  import { SlidersHorizontal, Keyboard, ScrollText, Info } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import CheckField from './CheckField.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
</script>

<nav class="advanced-actions" aria-label={ui.t('common.advanced_area.advanced_settings')}>
  <PreviewDialog title={ui.t('common.advanced_settings_dialog.title')}>
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
  <PreviewDialog title={ui.t('common.shortcut_settings.title')} wide>
    {#snippet trigger()}<Keyboard size={16} />{ui.t('common.advanced_area.key_settings')}{/snippet}
    <CheckField label={ui.t('common.shortcut_settings_dialog.enable_shortcuts')} />
    <div class="shortcut-list">
      {#each ['toggleVoiceConversion', 'togglePassthrough', 'nextSlot', 'previousSlot', 'increaseInputVolume', 'decreaseInputVolume', 'increaseOutputVolume', 'decreaseOutputVolume', 'increaseMonitorVolume', 'decreaseMonitorVolume'] as action}
        <div><span>{ui.t(`common.shortcut_settings.actions.${action}.name`)}</span><button class="button small" disabled>{ui.t('common.shortcut_settings_dialog.not_set')}</button></div>
      {/each}
    </div>
  </PreviewDialog>
  <button class="button" onclick={() => {
    const desktop = (window as Window & { vcclientForge?: { openLogWindow?: () => boolean } }).vcclientForge;
    if (!desktop?.openLogWindow?.()) window.open(`${location.pathname}?view=log`, 'vcclient-forge-log');
  }}><ScrollText size={16} />{ui.t('common.advanced_area.log')}</button>
  <PreviewDialog title={ui.t('forge.about')}>
    {#snippet trigger()}<Info size={16} />{ui.t('forge.about')}{/snippet}
    <h3>VCClient Forge</h3>
    <p class="muted">{ui.t('forge.licenses')}</p>
    <h3>{ui.t('common.copyright.disclaimer')}</h3>
    <p class="muted">{ui.t('common.copyright.disclaimer_text')}</p>
  </PreviewDialog>
  <button class="button" disabled>{ui.t('common.advanced_area.clear_site_data_and_restart')}</button>
</nav>
