<script lang="ts">
  import { SlidersHorizontal, Keyboard, ScrollText, Info, RotateCcw } from '@lucide/svelte';
  import { Dialog } from 'bits-ui';
  import PreviewDialog from './PreviewDialog.svelte';
  import CheckField from './CheckField.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
  let advancedOpen = $state(false);
  let resetConfirmOpen = $state(false);
  let resetCancel: HTMLButtonElement | undefined = $state();

  async function confirmResetSettings() {
    if (await session.clearConfiguration(() => ui.resetPreferences())) {
      resetConfirmOpen = false;
      advancedOpen = false;
    }
  }
</script>

<nav class="advanced-actions" aria-label={ui.t('common.advanced_area.advanced_settings')}>
  <PreviewDialog title={ui.t('common.advanced_settings_dialog.title')} preventClose={session.clearing} bind:open={advancedOpen}>
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
    {#snippet footer()}
      <div class="delete-button-wrapper">
        <Dialog.Root bind:open={resetConfirmOpen} onOpenChange={open => { if (open) session.clearError = null; }}>
          <Dialog.Trigger class="button" disabled={!session.canClearConfiguration}>
            <RotateCcw size={16} />{ui.t('forge.reset_settings')}
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay class="dialog-overlay" />
            <Dialog.Content class="dialog-content delete-confirm-dialog"
              escapeKeydownBehavior={session.clearing ? 'ignore' : 'close'}
              interactOutsideBehavior={session.clearing ? 'ignore' : 'close'}
              onOpenAutoFocus={event => { event.preventDefault(); resetCancel?.focus(); }}>
              <header class="dialog-header"><Dialog.Title class="dialog-title">{ui.t('forge.reset_settings_confirm')}</Dialog.Title></header>
              <div class="dialog-body">
                <Dialog.Description>{ui.t('forge.reset_settings_description')}</Dialog.Description>
                {#if session.clearError}
                  <p role="alert">{ui.t('forge.reset_settings_failed')} {ui.t(`forge.write_error_${session.clearError.code}`, { status: session.clearError.status })} {session.clearError.detail ?? ''}</p>
                {/if}
              </div>
              <footer class="dialog-footer">
                <button class="button danger" disabled={!session.canClearConfiguration} onclick={confirmResetSettings}>{ui.t('forge.reset_settings_action')}</button>
                <button class="button" disabled={session.clearing} bind:this={resetCancel} onclick={() => resetConfirmOpen = false}>{ui.t('forge.cancel')}</button>
              </footer>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
      <Dialog.Close class="button" disabled={session.clearing}>{ui.t('forge.close')}</Dialog.Close>
    {/snippet}
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
</nav>
