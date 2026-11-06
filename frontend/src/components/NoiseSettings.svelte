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
  <h3>{ui.t('common.settings_dialog.noise_gate')}</h3>
  <RangeField label={ui.t('forge.noise_gate_threshold')} value={settings?.noiseGate ?? null} min={-120} max={0} step={1} unit=" dB"
    disabled={!session.canAdjustGain} onchange={value => session.setNoiseGate(value)} oncommit={() => session.flush()} />
  <p class="muted">{ui.t('forge.noise_gate_disabled_hint')}</p>
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
<section class="settings-section">
  <h3>{ui.t('forge.client_only_settings')}</h3>
  {#each ['enable_echo_cancellation', 'enable_noise_suppression', 'enable_noise_suppression2'] as key}
    <CheckField label={ui.t(`common.settings_dialog.${key}`)} />
  {/each}
  <p class="muted">{ui.t('forge.browser_settings_unavailable')}</p>
</section>
