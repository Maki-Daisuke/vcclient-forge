<script lang="ts">
  import { Settings } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import SelectField from './SelectField.svelte';
  import CheckField from './CheckField.svelte';
  import { useUi } from '../lib/ui.svelte';
  const ui = useUi();
</script>

<PreviewDialog title={ui.t('common.settings_dialog.title')}>
  {#snippet trigger()}<Settings size={16} />{ui.t('common.controls.settings')}{/snippet}
  <SelectField label={ui.t('common.settings_dialog.voice_changer_input_mode')} value={ui.t('common.settings_dialog.server_mode')} />
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.audio_device_settings')}</h3>
    <div class="field-grid">
      <SelectField label={ui.t('forge.host')} value="WASAPI" />
      <SelectField label={ui.t('forge.sample_rate')} value="48,000 Hz" />
    </div>
    {#each ['input_device', 'output_device', 'monitor_device'] as device}
      <SelectField label={ui.t(`common.settings_dialog.${device}`)} value={ui.t('common.settings_dialog.unselected')} />
    {/each}
    <CheckField label={ui.t('common.settings_dialog.wasapi_exclusive_mode')} />
  </section>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.gpu_settings')}</h3>
    <SelectField label={ui.t('common.settings_dialog.gpu_settings')} value="CPU (Sample)" />
  </section>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.noise_suppression')}</h3>
    {#each ['enable_echo_cancellation', 'enable_noise_suppression', 'enable_noise_suppression2'] as key}
      <CheckField label={ui.t(`common.settings_dialog.${key}`)} />
    {/each}
  </section>
  <section class="settings-section">
    <h3>{ui.t('common.settings_dialog.noise_gate')}</h3>
    <CheckField label={ui.t('common.settings_dialog.enable_high_pass_filter')} />
    <CheckField label={ui.t('common.settings_dialog.enable_low_pass_filter')} />
    <SelectField label={ui.t('common.settings_dialog.cutoff')} value="80 Hz" />
  </section>
</PreviewDialog>
