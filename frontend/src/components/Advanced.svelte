<script lang="ts">
  import { SlidersHorizontal, Keyboard, ScrollText, Info } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import CheckField from './CheckField.svelte';
  import SelectField from './SelectField.svelte';
  import { useUi } from '../lib/ui.svelte';
  const ui = useUi();
</script>

<nav class="advanced-actions" aria-label={ui.t('common.advanced_area.advanced_settings')}>
  <PreviewDialog title={ui.t('common.advanced_settings_dialog.title')}>
    {#snippet trigger()}<SlidersHorizontal size={16} />{ui.t('common.advanced_area.advanced_settings')}{/snippet}
    <section class="settings-section">
      <h3>{ui.t('common.advanced_settings_dialog.realtime_analysis_settings')}</h3>
      <CheckField label={ui.t('common.advanced_settings_dialog.enable_realtime_io_analysis')} />
      <CheckField label={ui.t('common.advanced_settings_dialog.enable_realtime_voice_processing_analysis')} />
      <SelectField label={ui.t('common.advanced_settings_dialog.send_interval_seconds')} value="0.2 s" />
    </section>
    <section class="settings-section">
      <h3>{ui.t('common.advanced_settings.recording_settings')}</h3>
      <CheckField label={ui.t('common.advanced_settings.record_for_analysis')} />
      <p class="muted">{ui.t('common.advanced_settings.record_for_analysis_description')}</p>
    </section>
    <CheckField label={ui.t('common.advanced_settings.show_sample_audio_button')} />
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
  <PreviewDialog title={ui.t('log_viewer.title')} wide>
    {#snippet trigger()}<ScrollText size={16} />{ui.t('common.advanced_area.log')}{/snippet}
    <div class="button-row"><button class="button" disabled>{ui.t('log_viewer.autoload', { status: 'OFF' })}</button><button class="button" disabled>{ui.t('log_viewer.latest')}</button></div>
    <pre class="log-placeholder">{ui.t('forge.log_empty')}</pre>
  </PreviewDialog>
  <PreviewDialog title={ui.t('forge.about')}>
    {#snippet trigger()}<Info size={16} />{ui.t('forge.about')}{/snippet}
    <h3>VCClient Forge</h3>
    <p>{ui.t('forge.preview_description')}</p>
    <p class="muted">{ui.t('forge.licenses')}</p>
    <p class="muted">Copyright (c) 2025 Wataru Okada</p>
    <h3>{ui.t('common.copyright.disclaimer')}</h3>
    <p class="muted">{ui.t('common.copyright.disclaimer_text')}</p>
  </PreviewDialog>
  <button class="button" disabled>{ui.t('common.advanced_area.clear_site_data_and_restart')}</button>
</nav>
