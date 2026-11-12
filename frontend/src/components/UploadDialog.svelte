<script lang="ts">
  import { Upload } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useSession } from '../lib/session.svelte';
  import type { ModelArchive } from '../lib/model-archive';
  const ui = useUi();
  const session = useSession();
  let model = $state<File | null>(null);
  let index = $state<File | null>(null);
  let modelInput = $state<HTMLInputElement>();
  let indexInput = $state<HTMLInputElement>();
  let archive = $state<ModelArchive | null>(null);
  let archiveModel = $state('');
  let archiveIndex = $state('');
  let archiveError = $state('');
  let inspecting = $state(false);
  let extracting = $state(false);
  let dragging = $state(false);
  let archiveVersion = 0;
  const valid = $derived(archive ? archiveModel !== '' : !!model && model.size > 0 && /\.(onnx|pth)$/i.test(model.name)
    && (!index || (index.size > 0 && /\.index$/i.test(index.name))));
  const percentage = $derived(session.uploadTotal ? Math.floor(100 * session.uploadBytes / session.uploadTotal) : 0);
  function reset() { ++archiveVersion; model = null; index = null; archive = null; archiveModel = ''; archiveIndex = ''; archiveError = ''; inspecting = false; session.resetUpload(); }
  async function review() { await session.reload(); reset(); }
  async function chooseArchive(file: File | undefined) {
    const version = ++archiveVersion;
    archive = null; archiveModel = ''; archiveIndex = ''; archiveError = ''; model = null; index = null;
    if (modelInput) modelInput.value = '';
    if (indexInput) indexInput.value = '';
    if (!file) return;
    if (!/\.zip$/i.test(file.name)) { archiveError = 'upload_zip_only'; return; }
    inspecting = true;
    try {
      const { inspectModelArchive } = await import('../lib/model-archive');
      const result = await inspectModelArchive(file);
      if (version !== archiveVersion) return;
      archive = result;
      archiveModel = result.models.length === 1 ? String(result.models[0].id) : '';
      archiveIndex = result.indexes.length === 1 ? String(result.indexes[0].id) : '';
      model = null; index = null;
    } catch (error) {
      if (version === archiveVersion) archiveError = error instanceof Error && error.message === 'no_model' ? 'upload_zip_no_model' : 'upload_zip_invalid';
    } finally { if (version === archiveVersion) inspecting = false; }
  }
  async function submit() {
    if (!valid || !session.canConfigure || inspecting || extracting) return;
    if (!archive) { if (model) await session.uploadModel(model, index); return; }
    extracting = true; archiveError = '';
    try {
      const { extractModelArchive } = await import('../lib/model-archive');
      const files = await extractModelArchive(archive, Number(archiveModel), archiveIndex === '' ? null : Number(archiveIndex));
      if (!session.canConfigure) { archiveError = 'upload_not_ready'; return; }
      extracting = false;
      await session.uploadModel(files.model, files.index);
    } catch { archiveError = 'upload_zip_extract_failed'; }
    finally { extracting = false; }
  }
</script>

<PreviewDialog title={ui.t('common.model_upload.title')} disabled={!session.canConfigure && !session.importing} showCloseButton={false}>
  {#snippet trigger()}<Upload size={16} />{ui.t('common.model.upload.button')}{/snippet}
  {#if session.uploadStatus === 'success'}
    <p role="status">{ui.t('forge.upload_success')}</p>
    <button class="button" onclick={reset}>{ui.t('forge.upload_another')}</button>
  {:else if session.uploadStatus === 'refresh_failed' || session.uploadStatus === 'uncertain'}
    <p role="alert">{ui.t(session.uploadStatus === 'uncertain' ? 'forge.upload_uncertain' : 'forge.upload_refresh_failed')}</p>
    <button class="button" onclick={review}>{ui.t('forge.reload_models')}</button>
  {:else}
    {#if !archive}
    <div class="zip-drop" class:dragging role="region" aria-label={ui.t('forge.upload_zip_drop')}
      ondragover={event => { event.preventDefault(); if (!session.importing && !inspecting && !extracting) dragging = true; }}
      ondragleave={() => { dragging = false; }}
      ondrop={event => { event.preventDefault(); dragging = false; if (!session.importing && !inspecting && !extracting) { if (event.dataTransfer?.files.length !== 1) { archiveError = 'upload_zip_only'; } else void chooseArchive(event.dataTransfer.files[0]); } }}>
      <label class="select-field"><span>{ui.t('forge.upload_zip_drop')}</span><input type="file" accept=".zip" disabled={session.importing || inspecting || extracting} onchange={event => { const file = event.currentTarget.files?.[0]; event.currentTarget.value = ''; void chooseArchive(file); }} /></label>
    </div>
    <p class="upload-divider">{ui.t('forge.upload_or')}</p>
    <div class="individual-files">
      <label class="select-field"><span>{ui.t('common.model_upload.select_model_file')}</span><input bind:this={modelInput} type="file" accept=".pth,.onnx" disabled={session.importing || inspecting || extracting} onchange={event => { model = event.currentTarget.files?.[0] ?? null; }} /></label>
      <label class="select-field"><span>{ui.t('common.model_upload.select_index_file')} ({ui.t('forge.upload_optional')})</span><input bind:this={indexInput} type="file" accept=".index" disabled={session.importing || inspecting || extracting} onchange={event => { index = event.currentTarget.files?.[0] ?? null; }} /></label>
    </div>
    {:else}
      <p>{archive.file.name}</p>
      <label class="select-field"><span>{ui.t('forge.upload_zip_model')}</span><select bind:value={archiveModel} disabled={session.importing || extracting}>
        {#if archive.models.length > 1}<option value="">{ui.t('forge.upload_zip_choose')}</option>{/if}
        {#each archive.models as entry}<option value={String(entry.id)}>{entry.name}</option>{/each}
      </select></label>
      <label class="select-field"><span>{ui.t('forge.upload_zip_index')}</span><select bind:value={archiveIndex} disabled={session.importing || extracting}>
        <option value="">{ui.t('forge.upload_no_index')}</option>
        {#each archive.indexes as entry}<option value={String(entry.id)}>{entry.name}</option>{/each}
      </select></label>
      <button class="button small" disabled={session.importing || extracting} onclick={reset}>{ui.t('forge.upload_change_files')}</button>
    {/if}
    <p class="muted">{ui.t('forge.upload_hint')}</p>
    {#if archiveError}<p role="alert">{ui.t(`forge.${archiveError}`)}</p>{/if}
    {#if inspecting || extracting}<p role="status">{ui.t(inspecting ? 'forge.upload_zip_inspecting' : 'forge.upload_zip_extracting')}</p>{/if}
    {#if session.uploadStatus === 'uploading'}
      <p role="status">{ui.t('forge.upload_progress', { percent: percentage })}</p>
      <progress value={session.uploadBytes} max={session.uploadTotal} aria-label={ui.t('forge.upload_progress_label')}></progress>
    {:else if session.uploadStatus === 'registering'}
      <p role="status">{ui.t('forge.upload_registering')}</p>
    {:else if session.uploadError}
      <p role="alert">{ui.t('forge.upload_failed')} {ui.t(`forge.write_error_${session.uploadError.code}`, { status: session.uploadError.status })} {session.uploadError.detail ?? ''}</p>
    {/if}
    <button class="button primary action-primary" disabled={!valid || !session.canConfigure || inspecting || extracting} onclick={submit}>{ui.t('common.model_upload.upload_button')}</button>
  {/if}
</PreviewDialog>
<style>
  .zip-drop { border: 1px dashed var(--border); border-radius: 6px; padding: 0 12px; }
  .zip-drop.dragging { border-color: var(--accent); background: var(--accent-soft); }
  .zip-drop .select-field { margin: 12px 0; }
  .upload-divider { margin: 10px 0; color: var(--muted); text-align: center; font-size: .8rem; }
  .individual-files { border: 1px solid var(--border); border-radius: 6px; padding: 0 12px; }
  .individual-files .select-field { margin: 12px 0; }
</style>
