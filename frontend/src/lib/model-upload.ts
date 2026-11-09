import { ApiError } from './api-error';
import { readNativeActive } from './api';

const chunkSize = 4 * 1024 * 1024;

async function checkedJson(response: Response): Promise<unknown> {
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError('http', response.status, typeof body?.detail === 'string' ? body.detail : undefined);
  }
  try { return await response.json(); } catch { throw new ApiError('invalid_response'); }
}

export async function uploadFile(file: File, extension: string, signal: AbortSignal, progress: (bytes: number) => void): Promise<string> {
  // A unique, short name prevents collisions and satisfies the importer's filename limit.
  const filename = `${crypto.randomUUID()}${extension}`;
  const count = Math.ceil(file.size / chunkSize);
  for (let index = 0; index < count; index++) {
    const chunk = file.slice(index * chunkSize, Math.min(file.size, (index + 1) * chunkSize));
    const form = new FormData();
    form.append('file', chunk, filename);
    form.append('filename', filename);
    form.append('index', String(index));
    const result = await checkedJson(await fetch('/api/uploader/upload_file_chunk', { method: 'POST', body: form, signal }));
    if (!result || typeof result !== 'object' || typeof (result as Record<string, unknown>).uploaded_filename !== 'string') throw new ApiError('invalid_response');
    progress(chunk.size);
  }
  const form = new FormData();
  form.append('filename', filename);
  form.append('filename_chunk_num', String(count));
  const result = await checkedJson(await fetch('/api/uploader/concat_uploaded_file_chunk', { method: 'POST', body: form, signal }));
  if (!result || typeof result !== 'object' || typeof (result as Record<string, unknown>).generated_filename !== 'string') throw new ApiError('invalid_response');
  return filename;
}

export async function importModel(model: File, index: File | null, signal: AbortSignal, progress: (bytes: number) => void, registering: () => void): Promise<void> {
  const ext = /\.(onnx|pth)$/i.exec(model.name)?.[0].toLowerCase();
  if (!ext || model.size === 0 || (index && (!/\.index$/i.test(index.name) || index.size === 0))) throw new ApiError('invalid_response');
  if (await readNativeActive(signal)) throw new ApiError('active');
  const modelFile = await uploadFile(model, ext, signal, progress);
  const indexFile = index ? await uploadFile(index, '.index', signal, progress) : null;
  if (await readNativeActive(signal)) throw new ApiError('active');
  registering();
  await checkedJson(await fetch('/api/slot-manager/slots', {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ voice_changer_type: 'RVC', name: model.name.slice(0, -ext.length), slot_index: null, model_file: modelFile, index_file: indexFile }),
  }));
}
