<script lang="ts">
  import { Upload } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  const ui = useUi();
  const session = useSession();
  let model = $state<File | null>(null);
  let index = $state<File | null>(null);
  const valid = $derived(!!model && model.size > 0 && /\.(onnx|pth)$/i.test(model.name)
    && (!index || (index.size > 0 && /\.index$/i.test(index.name))));
  const percentage = $derived(session.uploadTotal ? Math.floor(100 * session.uploadBytes / session.uploadTotal) : 0);
  function reset() { model = null; index = null; session.resetUpload(); }
  async function review() { await session.reload(); reset(); }
</script>

<PreviewDialog title={ui.t('common.model_upload.title')} disabled={!session.canConfigure && !session.importing}>
  {#snippet trigger()}<Upload size={16} />{ui.t('common.model.upload.button')}{/snippet}
  {#if session.uploadStatus === 'success'}
    <p role="status">{ui.t('forge.upload_success')}</p>
    <button class="button" onclick={reset}>{ui.t('forge.upload_another')}</button>
  {:else if session.uploadStatus === 'refresh_failed' || session.uploadStatus === 'uncertain'}
    <p role="alert">{ui.t(session.uploadStatus === 'uncertain' ? 'forge.upload_uncertain' : 'forge.upload_refresh_failed')}</p>
    <button class="button" onclick={review}>{ui.t('forge.reload_models')}</button>
  {:else}
    <label class="select-field"><span>{ui.t('common.model_upload.select_model_file')}</span><input type="file" accept=".pth,.onnx" disabled={session.importing} onchange={event => { model = event.currentTarget.files?.[0] ?? null; }} /></label>
    <label class="select-field"><span>{ui.t('common.model_upload.select_index_file')} ({ui.t('forge.upload_optional')})</span><input type="file" accept=".index" disabled={session.importing} onchange={event => { index = event.currentTarget.files?.[0] ?? null; }} /></label>
    <p class="muted">{ui.t('forge.upload_hint')}</p>
    {#if session.uploadStatus === 'uploading'}
      <p role="status">{ui.t('forge.upload_progress', { percent: percentage })}</p>
      <progress value={session.uploadBytes} max={session.uploadTotal} aria-label={ui.t('forge.upload_progress_label')}></progress>
    {:else if session.uploadStatus === 'registering'}
      <p role="status">{ui.t('forge.upload_registering')}</p>
    {:else if session.uploadError}
      <p role="alert">{ui.t('forge.upload_failed')} {ui.t(`forge.write_error_${session.uploadError.code}`, { status: session.uploadError.status })} {session.uploadError.detail ?? ''}</p>
    {/if}
    <button class="button primary" disabled={!valid || !session.canConfigure} onclick={() => model && session.uploadModel(model, index)}>{ui.t('common.model_upload.upload_button')}</button>
  {/if}
</PreviewDialog>
