<script lang="ts">
  import { Trash2, Pencil, RefreshCw } from '@lucide/svelte';
  import { Dialog } from 'bits-ui';
  import { untrack } from 'svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import UploadDialog from './UploadDialog.svelte';
  import CatalogStatus from './CatalogStatus.svelte';
  import ModelImage from './ModelImage.svelte';
  import PendingIndicator from './PendingIndicator.svelte';
  import VoiceControls from './VoiceControls.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useCatalog } from '../lib/catalog.svelte';
  import { useSession } from '../lib/session.svelte';
  import type { ModelSummary } from '../lib/catalog';
  const ui = useUi();
  const catalog = useCatalog();
  const session = useSession();
  const currentModel = $derived(session.currentModel);
  let editOpen = $state(false);
  let editModelId = $state<number | null>(null);
  let editName = $state('');
  let editIcon = $state<File | null>(null);
  let iconPreviewUrl = $state<string | null>(null);
  let confirmOpen = $state(false);
  let reordering = $state(false);
  let order = $state<number[]>([]);
  let dragged = $state<number | null>(null);
  const displayedModels = $derived(reordering
    ? order.map(id => catalog.models.find(model => model.id === id)).filter((model): model is ModelSummary => model !== undefined)
    : catalog.models);
  const deleteReason = $derived(session.active === true ? ui.t('forge.delete_stop_first') : ui.t('forge.model_operation_wait'));
  const validIcon = $derived(!editIcon || (editIcon.size > 0 && /\.(png|jpe?g|webp|gif|avif|bmp)$/i.test(editIcon.name)
    && (!editIcon.type || editIcon.type.startsWith('image/'))));
  const editChanged = $derived(editName !== (currentModel?.name ?? '') || editIcon !== null);

  $effect(() => {
    if (editOpen) {
      const model = untrack(() => session.currentModel);
      editModelId = model?.id ?? null;
      editName = model?.name ?? '';
      editIcon = null;
      session.modelInfoError = null;
    }
  });

  $effect(() => {
    const file = editOpen && validIcon ? editIcon : null;
    const url = file ? URL.createObjectURL(file) : null;
    iconPreviewUrl = url;
    return () => { if (url) URL.revokeObjectURL(url); };
  });

  async function saveModelInfo() {
    if (editModelId === null || !validIcon || !editChanged || !editName.trim()) return;
    if (await session.saveModelInfo(editModelId, editName, editIcon)) editOpen = false;
  }

  function beginReorder() {
    if (!session.canConfigure) return;
    session.modelOperationError = null;
    order = catalog.models.map(model => model.id);
    reordering = true;
  }

  function moveModel(from: number, to: number) {
    if (from < 0 || to < 0 || from >= order.length || to >= order.length || from === to) return;
    const next = [...order];
    const [id] = next.splice(from, 1);
    next.splice(to, 0, id);
    order = next;
  }

  async function applyOrder() {
    if (await session.organizeModels(order)) reordering = false;
  }

  async function deleteModel() {
    if (!currentModel || !session.canConfigure) return;
    const remaining = catalog.models.filter(model => model.id !== currentModel.id).map(model => model.id);
    if (await session.organizeModels(remaining, true)) {
      confirmOpen = false;
      editOpen = false;
    }
  }

  function modelName(model: ModelSummary) {
    return model.name || ui.t('common.model_editor.slot', { number: model.id + 1 });
  }
</script>

<section class="panel models-panel" aria-labelledby="models-title" aria-busy={catalog.state.status === 'loading'}>
  <div class="section-heading">
    <h2 id="models-title">{ui.t('forge.model_selection')}</h2>
    <div class="button-row">
      {#if reordering}
        <span class="reorder-hint">{ui.t('forge.reorder_hint')}</span>
        <button class="button primary action-primary" disabled={!session.canConfigure} onclick={applyOrder}>{ui.t('forge.reorder_confirm')}</button>
        <button class="button" disabled={session.organizing} onclick={() => { reordering = false; session.modelOperationError = null; }}>{ui.t('forge.cancel')}</button>
      {:else}
        <button class="button" disabled={!session.canReload} onclick={() => session.reload()}>
          <RefreshCw size={16} />{ui.t('forge.reload_models')}
        </button>
        <UploadDialog />
        <button class="button" disabled={!session.canConfigure || catalog.models.length < 2} onclick={beginReorder}>{ui.t('forge.reorder')}</button>
      {/if}
    </div>
  </div>
  <CatalogStatus />
  {#if session.modelOperationError}
    <p role="alert">{session.modelOperationError.status === 404 ? ui.t('forge.model_operation_restart') : `${ui.t('forge.model_operation_failed')} ${session.modelOperationError.detail ?? ''}`}</p>
  {/if}
  {#if catalog.models.length > 0}
    <div class="model-cards">
      {#each displayedModels as model, position (model.id)}
        <div class="model-card-wrapper" class:draggable-model={reordering} draggable={reordering} role="group" aria-label={modelName(model)}
          ondragstart={(event) => { if (reordering) { dragged = position; event.dataTransfer?.setData('text/plain', String(model.id)); } }}
          ondragend={() => dragged = null}
          ondragover={(event) => { if (reordering) event.preventDefault(); }}
          ondrop={(event) => { event.preventDefault(); if (reordering && dragged !== null) moveModel(dragged, position); dragged = null; }}>
        <button
          class:selected={model.id === session.currentModelId}
          class="model-card"
          disabled={!session.canConfigure || model.status !== 'ready'}
          aria-disabled={reordering ? 'true' : undefined}
          onclick={() => { if (!reordering) session.selectModel(model.id); }}
          aria-label={modelName(model)}
          aria-current={model.id === session.currentModelId ? 'true' : undefined}
          aria-busy={!session.error && session.draft.currentModelId === model.id}
        >
          <span class="slot-number">{model.id + 1}</span>
          {#if !session.error && session.draft.currentModelId === model.id}<span class="model-pending"><PendingIndicator /></span>{/if}
          <ModelImage src={model.imageUrl} />
          <span class="model-name" title={modelName(model)}>{modelName(model)}</span>
          {#if model.status !== 'ready'}
            <span class="tag">{ui.t(`forge.model_status_${model.status}`)}</span>
          {/if}
        </button>
        </div>
      {/each}
    </div>
  {/if}
<div class="model-heading">
  <h2>{currentModel ? `${currentModel.id + 1}. ${modelName(currentModel)}` : ui.t('common.model.not_selected')}</h2>
  {#if currentModel}
    <div class="tags">
      {#each currentModel.tags as tag}<span class="tag">{tag}</span>{/each}
      {#if currentModel.status !== 'ready'}<span class="tag">{ui.t(`forge.model_status_${currentModel.status}`)}</span>{/if}
    </div>
  {/if}
  <PreviewDialog title={ui.t('forge.edit_model_info')} disabled={!currentModel} showCloseButton={false} preventClose={session.modelInfoSaving} bind:open={editOpen}>
    {#snippet trigger()}<Pencil size={15} />{ui.t('common.model.edit.button')}{/snippet}
    <label class="select-field"><span>{ui.t('common.voice_character_editor.name')}</span><input bind:value={editName} disabled={!session.canConfigure || currentModel?.status !== 'ready'} /></label>
    <label class="select-field"><span>{ui.t('common.voice_character_editor.select_icon')}</span><input type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.avif,.bmp" disabled={!session.canConfigure || currentModel?.status !== 'ready'} onchange={event => { editIcon = event.currentTarget.files?.[0] ?? null; }} /></label>
    {#if iconPreviewUrl}<img class="model-icon-preview" src={iconPreviewUrl} alt={ui.t('common.voice_character_edit_dialog.new_icon')} />{/if}
    {#if !validIcon}<p role="alert">{ui.t('forge.model_icon_invalid')}</p>{/if}
    {#if !session.modelInfoSaving && session.active === true}<p class="muted">{ui.t('forge.model_edit_stop_first')}</p>{/if}
    {#if session.modelInfoError}<p role="alert">{ui.t('forge.model_info_save_failed')}</p>{/if}
    {#if session.modelInfoSaving}<p role="status">{ui.t('forge.model_info_saving')}</p>{/if}
    {#snippet footer()}
    <Dialog.Root bind:open={confirmOpen}>
      <span class="start-button-wrapper delete-button-wrapper">
        <Dialog.Trigger class="button danger" aria-disabled={!session.canConfigure} aria-describedby={!session.canConfigure ? 'delete-reason' : undefined}
          onclick={(event: MouseEvent) => { if (!session.canConfigure) event.preventDefault(); }}>
          <Trash2 size={16} />{ui.t('forge.delete_model')}
        </Dialog.Trigger>
        {#if !session.canConfigure}<span id="delete-reason" class="start-tooltip" role="tooltip">{deleteReason}</span>{/if}
      </span>
      <Dialog.Portal>
        <Dialog.Overlay class="dialog-overlay" />
        <Dialog.Content class="dialog-content delete-confirm-dialog">
          <header class="dialog-header"><Dialog.Title class="dialog-title">{ui.t('forge.delete_confirm')}</Dialog.Title></header>
          <div class="dialog-body">
            <Dialog.Description>{ui.t('forge.delete_confirm_description')}</Dialog.Description>
            {#if session.modelOperationError}<p role="alert">{ui.t('forge.model_operation_failed')}</p>{/if}
          </div>
          <footer class="dialog-footer">
            <button class="button danger" disabled={!session.canConfigure} onclick={deleteModel}>{ui.t('forge.delete_action')}</button>
            <Dialog.Close class="button" disabled={session.organizing}>{ui.t('forge.cancel')}</Dialog.Close>
          </footer>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
    <button class="button primary action-primary" disabled={!session.canConfigure || currentModel?.status !== 'ready' || !editChanged || !editName.trim() || !validIcon} onclick={saveModelInfo}>{ui.t('common.voice_character_editor.save')}</button>
    <Dialog.Close class="button" disabled={session.modelInfoSaving}>{ui.t('forge.cancel')}</Dialog.Close>
    {/snippet}
  </PreviewDialog>
</div>
<div class="selected-model-layout">
  <div class="selected-model-info">
    <div class="portrait">
      {#if currentModel}
        <ModelImage src={currentModel.imageUrl} alt={modelName(currentModel)} />
      {:else}
        <span class="muted">{ui.t('common.model.not_selected')}</span>
      {/if}
    </div>
    {#if !currentModel && catalog.state.status === 'ready' && catalog.models.length > 0 && catalog.currentModelId !== null}
      <p class="model-message">{ui.t('forge.current_model_unavailable', { slot: catalog.currentModelId + 1 })}</p>
    {/if}
  </div>
  <VoiceControls />
</div>
</section>
