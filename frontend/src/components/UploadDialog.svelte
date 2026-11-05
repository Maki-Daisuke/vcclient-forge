<script lang="ts">
  import { Upload } from '@lucide/svelte';
  import PreviewDialog from './PreviewDialog.svelte';
  import SelectField from './SelectField.svelte';
  import { useUi } from '../lib/ui.svelte';
  const ui = useUi();
</script>

<PreviewDialog title={ui.t('common.model_upload.title')}>
  {#snippet trigger()}<Upload size={16} />{ui.t('common.model.upload.button')}{/snippet}
  <SelectField label={ui.t('common.model_upload.voice_changer_type')} value="RVC" />
  <SelectField label={ui.t('common.sample_model.select_slot')} value={ui.t('forge.not_connected')} />
  <label class="select-field"><span>{ui.t('common.model_upload.select_model_file')}</span><input type="file" accept=".pth,.onnx,.zip" disabled /></label>
  <label class="select-field"><span>{ui.t('common.model_upload.select_index_file')}</span><input type="file" accept=".index" disabled /></label>
  <button class="button primary" disabled>{ui.t('common.model_upload.upload_button')}</button>
</PreviewDialog>
