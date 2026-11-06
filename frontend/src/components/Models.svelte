<script lang="ts">
  import { FolderOpen, Download, Trash2, ArrowRightLeft, Pencil, RefreshCw } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import UploadDialog from './UploadDialog.svelte';
  import CatalogStatus from './CatalogStatus.svelte';
  import ModelImage from './ModelImage.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { useCatalog } from '../lib/catalog.svelte';
  import { useSession } from '../lib/session.svelte';
  import type { ModelSummary } from '../lib/catalog';
  const ui = useUi();
  const catalog = useCatalog();
  const session = useSession();
  const currentModel = $derived(session.currentModel);

  function modelName(model: ModelSummary) {
    return model.name || ui.t('common.model_editor.slot', { number: model.id + 1 });
  }
</script>

<section class="panel models-panel" aria-labelledby="models-title" aria-busy={catalog.state.status === 'loading'}>
  <div class="section-heading">
    <h2 id="models-title">
      {ui.t('common.model.list_title')}
      {#if catalog.state.status === 'ready'}
        <span class="count">{ui.t('forge.models_count', { count: catalog.models.length })}</span>
      {/if}
    </h2>
    <div class="button-row">
      <button class="button" disabled={!session.canReload} onclick={() => session.reload()}>
        <RefreshCw size={16} />{ui.t('forge.reload_models')}
      </button>
      <UploadDialog />
      <PreviewDialog title={ui.t('common.model_editor.title')} description={ui.t('forge.models_readonly')} wide>
        {#snippet trigger()}<FolderOpen size={16} />{ui.t('forge.model_management')}{/snippet}
        <CatalogStatus />
        <div class="model-table">
          {#each catalog.models as model (model.id)}
            <div class="model-table-row">
              <ModelImage src={model.imageUrl} />
              <div>
                <strong>{ui.t('common.model_editor.slot', { number: model.id + 1 })}</strong>
                <p>{modelName(model)}</p>
                {#if model.status !== 'ready'}<span class="tag">{ui.t(`forge.model_status_${model.status}`)}</span>{/if}
              </div>
              <div class="button-row">
                <button class="icon-button" disabled aria-label={ui.t('common.model_editor.move_model')}><ArrowRightLeft size={17} /></button>
                <button class="icon-button" disabled aria-label={ui.t('common.model_editor.download_model')}><Download size={17} /></button>
                <button class="icon-button" disabled aria-label={ui.t('common.model_editor.delete_model')}><Trash2 size={17} /></button>
              </div>
            </div>
          {/each}
        </div>
        <div class="button-row">
          <UploadDialog />
          <PreviewDialog title={ui.t('common.sample_model_dialog.title')}>
            {#snippet trigger()}<Download size={16} />{ui.t('common.model_editor.sample_model')}{/snippet}
            <p>{ui.t('forge.sample_models_preview')}</p>
            <button class="button primary" disabled>{ui.t('common.sample_model_dialog.download_button')}</button>
          </PreviewDialog>
        </div>
      </PreviewDialog>
    </div>
  </div>
  <CatalogStatus />
  {#if catalog.models.length > 0}
    <div class="model-cards">
      {#each catalog.models as model (model.id)}
        <button
          class:selected={model.id === session.currentModelId}
          class="model-card"
          disabled={!session.canConfigure || model.status !== 'ready'}
          onclick={() => session.selectModel(model.id)}
          aria-label={modelName(model)}
          aria-current={model.id === session.currentModelId ? 'true' : undefined}
        >
          <span class="slot-number">{model.id + 1}</span>
          <ModelImage src={model.imageUrl} />
          <span class="model-name" title={modelName(model)}>{modelName(model)}</span>
          {#if model.status !== 'ready'}
            <span class="tag">{ui.t(`forge.model_status_${model.status}`)}</span>
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</section>

<div class="model-heading">
  <h2>{currentModel ? `${currentModel.id + 1}. ${modelName(currentModel)}` : ui.t('common.model.not_selected')}</h2>
  {#if currentModel}
    <div class="tags">
      {#each currentModel.tags as tag}<span class="tag">{tag}</span>{/each}
      {#if currentModel.status !== 'ready'}<span class="tag">{ui.t(`forge.model_status_${currentModel.status}`)}</span>{/if}
    </div>
  {/if}
  <PreviewDialog title={ui.t('common.voice_character_editor.title')} description={ui.t('forge.models_readonly')} disabled={!currentModel}>
    {#snippet trigger()}<Pencil size={15} />{ui.t('common.model.edit.button')}{/snippet}
    <label class="select-field"><span>{ui.t('common.voice_character_editor.name')}</span><input disabled value={currentModel?.name ?? ''} /></label>
    <label class="select-field"><span>{ui.t('common.voice_character_editor.description')}</span><textarea disabled rows="4" value={currentModel?.description ?? ''}></textarea></label>
    <label class="select-field"><span>{ui.t('common.voice_character_editor.select_icon')}</span><input type="file" accept="image/*" disabled /></label>
    <button class="button primary" disabled>{ui.t('common.voice_character_editor.save')}</button>
  </PreviewDialog>
</div>
{#if currentModel}
  <p class="model-description">{currentModel.description || ui.t('common.voice.no_description')}</p>
{:else if catalog.state.status === 'ready' && catalog.models.length > 0 && catalog.currentModelId !== null}
  <p class="model-description">{ui.t('forge.current_model_unavailable', { slot: catalog.currentModelId + 1 })}</p>
{/if}
