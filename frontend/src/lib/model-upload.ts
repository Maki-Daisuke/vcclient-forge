import { ApiError } from './api-error';
import { readNativeActive, sendMultipart } from './api';

export async function importModel(
  model: File,
  index: File | null,
  signal: AbortSignal,
  progress: (bytes: number) => void,
  registering: () => void,
): Promise<void> {
  const ext = /\.(onnx|pth)$/i.exec(model.name)?.[0].toLowerCase();
  if (!ext || model.size === 0 || (index && (!/\.index$/i.test(index.name) || index.size === 0))) {
    throw new ApiError('invalid_response');
  }
  if (await readNativeActive(signal)) throw new ApiError('active');
  const name = model.name.slice(0, -ext.length).trim() || model.name;
  const form = new FormData();
  form.append('name', name);
  form.append('model_file', model, model.name);
  if (index) form.append('index_file', index, index.name);
  await sendMultipart({
    method: 'POST',
    url: '/api/models',
    body: form,
    signal,
    onProgress: loaded => progress(loaded),
    onUploaded: registering,
  });
}
