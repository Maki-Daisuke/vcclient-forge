<script lang="ts">
  import { FolderOpen, Download, Trash2, ArrowRightLeft, Pencil } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import UploadDialog from './UploadDialog.svelte';
  import { useUi } from '../lib/ui.svelte';
  import { preview } from '../lib/preview';
  const ui = useUi();
</script>

<section class="panel models-panel" aria-labelledby="models-title">
  <div class="section-heading">
    <h2 id="models-title">{ui.t('common.model.list_title')} <span class="count">3 / 10</span></h2>
    <div class="button-row">
      <UploadDialog />
      <PreviewDialog title={ui.t('common.model_editor.title')} wide>
        {#snippet trigger()}<FolderOpen size={16} />{ui.t('forge.model_management')}{/snippet}
        <p class="muted">{ui.t('common.model_editor.slots_in_use', { used: 3, total: 10 })}</p>
        <div class="model-table">
          {#each preview.models as model (model.id)}
            <div class="model-table-row">
              <img src={preview.portraitUrl} alt="" />
              <div><strong>{ui.t('common.model_editor.slot', { number: model.slot })}</strong><p>{model.name}</p></div>
              <div class="button-row">
                <button class="icon-button" disabled aria-label={ui.t('common.model_editor.move_model')}><ArrowRightLeft size={17} /></button>
                <button class="icon-button" disabled aria-label={ui.t('common.model_editor.download_model')}><Download size={17} /></button>
                <button class="icon-button" disabled aria-label={ui.t('common.model_editor.delete_model')}><Trash2 size={17} /></button>
              </div>
            </div>
          {/each}
          <div class="empty-slot">{ui.t('common.model_editor.slot', { number: 4 })} · {ui.t('common.model_editor.empty_slot')}</div>
        </div>
        <div class="button-row">
          <UploadDialog />
          <PreviewDialog title={ui.t('common.sample_model_dialog.title')}>
            {#snippet trigger()}<Download size={16} />{ui.t('common.model_editor.sample_model')}{/snippet}
            <div class="sample-model"><img src={preview.portraitUrl} alt="" /><div><h3>{ui.t('forge.sample_model')}</h3><p>{ui.t('forge.sample_description')}</p></div></div>
            <button class="button primary" disabled>{ui.t('common.sample_model_dialog.download_button')}</button>
          </PreviewDialog>
        </div>
      </PreviewDialog>
    </div>
  </div>
  <div class="model-cards">
    {#each preview.models as model, index (model.id)}
      <button class:selected={index === 0} class="model-card" disabled aria-label={model.name}>
        <span class="slot-number">{model.slot}</span>
        <img src={preview.portraitUrl} alt="" />
        <span class="model-name">{model.name}</span><span class="tag">RVC</span>
      </button>
    {/each}
    <button class="model-card empty-card" disabled><span class="empty-plus">+</span><span>{ui.t('common.model_editor.empty_slot')}</span></button>
  </div>
</section>

<div class="model-heading">
  <h2>1. {preview.models[0].name}</h2>
  <div class="tags"><span class="tag">RVC</span><span class="tag">onnx v2</span><span class="tag">f0</span><span class="tag">ContentVec</span></div>
  <PreviewDialog title={ui.t('common.voice_character_editor.title')}>
    {#snippet trigger()}<Pencil size={15} />{ui.t('common.model.edit.button')}{/snippet}
    <label class="select-field"><span>{ui.t('common.voice_character_editor.name')}</span><input disabled value={preview.models[0].name} /></label>
    <label class="select-field"><span>{ui.t('common.voice_character_editor.description')}</span><textarea disabled rows="4" value={ui.t('forge.sample_description')}></textarea></label>
    <label class="select-field"><span>{ui.t('common.voice_character_editor.select_icon')}</span><input type="file" accept="image/*" disabled /></label>
    <button class="button primary" disabled>{ui.t('common.voice_character_editor.save')}</button>
  </PreviewDialog>
</div>
<p class="model-description">{ui.t('forge.sample_description')}</p>
