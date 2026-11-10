<script lang="ts">
  import RangeField from './RangeField.svelte';
  import CheckField from './CheckField.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
  const settings = $derived(session.settings);
</script>

<section class="settings-section">
  <div class="filter-heading">
    <h3>{ui.t('common.settings_dialog.noise_gate')}</h3>
    <CheckField label={ui.t('forge.enable')} ariaLabel={ui.t('forge.enable_noise_gate')}
      checked={settings?.noiseGate == null ? null : settings.noiseGate > -100}
      disabled={!session.canAdjustNoiseGate} onchange={value => session.setNoiseGateEnabled(value)} />
  </div>
  <RangeField label={ui.t('forge.noise_gate_threshold')} value={settings?.noiseGate == null ? null : Math.max(-100, settings.noiseGate)} min={-100} max={0} step={1} unit=" dB"
    disabled={!session.canAdjustNoiseGate || settings?.noiseGate == null || settings.noiseGate <= -100} onchange={value => session.setNoiseGate(value)} oncommit={() => session.flush()} />
  {#if !session.currentModel}<p class="muted">{ui.t('forge.filter_requires_model')}</p>{/if}
  <div class="filter-heading">
    <h3>{ui.t('forge.high_pass_filter')}</h3>
    <CheckField label={ui.t('forge.enable')} ariaLabel={ui.t('common.settings_dialog.enable_high_pass_filter')} checked={settings?.highPassEnabled ?? null}
      disabled={!session.canAdjustFilter} onchange={value => session.setFilter('highPassEnabled', value)} />
  </div>
  <RangeField label={ui.t('forge.high_pass_cutoff')} value={settings?.highPassCutoff ?? null} min={20} max={200} step={1} unit=" Hz"
    disabled={!session.canAdjustFilter || settings?.highPassEnabled !== true} onchange={value => session.setFilter('highPassCutoff', value)} oncommit={() => session.flush()} />
  <div class="filter-heading">
    <h3>{ui.t('forge.low_pass_filter')}</h3>
    <CheckField label={ui.t('forge.enable')} ariaLabel={ui.t('common.settings_dialog.enable_low_pass_filter')} checked={settings?.lowPassEnabled ?? null}
      disabled={!session.canAdjustFilter} onchange={value => session.setFilter('lowPassEnabled', value)} />
  </div>
  <RangeField label={ui.t('forge.low_pass_cutoff')} value={settings?.lowPassCutoff ?? null} min={3500} max={15000} step={1} unit=" Hz"
    disabled={!session.canAdjustFilter || settings?.lowPassEnabled !== true} onchange={value => session.setFilter('lowPassCutoff', value)} oncommit={() => session.flush()} />
</section>
<section class="settings-section client-noise-settings">
  <h3>{ui.t('forge.client_only_settings')}</h3>
  <div class="client-noise-options">
    <CheckField label={ui.language === 'ja' ? ui.t('forge.echo_cancellation') : ui.t('common.settings_dialog.enable_echo_cancellation')} checked={session.clientAudio.echoCancellation}
      disabled={settings?.inputMode !== 'client' || !session.canConfigure || (!session.clientAudio.supportsOption('echoCancellation') && !session.clientAudio.echoCancellation)}
      onchange={value => session.clientAudio.setOption('echoCancellation', value)} />
    <CheckField label={ui.language === 'ja' ? ui.t('forge.client_noise_suppression') : ui.t('common.settings_dialog.enable_noise_suppression')} checked={session.clientAudio.noiseSuppression}
      disabled={settings?.inputMode !== 'client' || !session.canConfigure || (!session.clientAudio.supportsOption('noiseSuppression') && !session.clientAudio.noiseSuppression)}
      onchange={value => session.clientAudio.setOption('noiseSuppression', value)} />
    <CheckField label={ui.t('forge.auto_gain_control')} checked={session.clientAudio.autoGainControl}
      disabled={settings?.inputMode !== 'client' || !session.canConfigure || (!session.clientAudio.supportsOption('autoGainControl') && !session.clientAudio.autoGainControl)}
      onchange={value => session.clientAudio.setOption('autoGainControl', value)} />
  </div>
</section>
<style>
  .client-noise-settings { padding-bottom: 0; margin-bottom: 0; }
  .client-noise-options { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; }
  .client-noise-options :global(.check-field) { margin: 0; }
</style>
