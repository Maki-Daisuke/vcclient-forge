import { CatalogError, type ModelCatalog, type ModelSummary } from './catalog';

function invalidResponse(): never {
  throw new CatalogError('invalid_response');
}

function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalidResponse();
  return value as Record<string, unknown>;
}

function text(value: unknown): string {
  if (value === undefined || value === null) return '';
  if (typeof value !== 'string') invalidResponse();
  return value;
}

function modelImage(id: number, value: unknown): string | null {
  // Backends may serialize Windows paths; static serving uses the slot's basename.
  const filename = text(value).replaceAll('\\', '/').split('/').at(-1);
  if (!filename || filename === '.' || filename === '..') return null;
  return `/model_dir/${id}/${encodeURIComponent(filename)}`;
}

function parseCatalog(slots: unknown, configuration: unknown): ModelCatalog {
  if (!Array.isArray(slots)) invalidResponse();
  const config = object(configuration);
  if (!Number.isSafeInteger(config.current_slot_index)) invalidResponse();
  const currentId = config.current_slot_index as number;
  const ids = new Set<number>();
  const models: ModelSummary[] = [];

  for (const value of slots) {
    const slot = object(value);
    if (!Number.isSafeInteger(slot.slot_index) || (slot.slot_index as number) < 0) invalidResponse();
    const id = slot.slot_index as number;
    if (ids.has(id)) invalidResponse();
    ids.add(id);
    if (slot.voice_changer_type === null) continue;
    if (typeof slot.voice_changer_type !== 'string') invalidResponse();

    const type = slot.voice_changer_type;
    const tags = type === 'RVC' ? [type] : [];
    if (type === 'RVC') {
      if (typeof slot.is_onnx !== 'boolean' || typeof slot.is_f0 !== 'boolean') invalidResponse();
      tags.push(`${slot.is_onnx ? 'onnx' : 'pth'} ${text(slot.version)}`.trim());
      tags.push(slot.is_f0 ? 'f0' : 'non-f0');
      const embedder = text(slot.embedder);
      if (embedder) tags.push(embedder);
    }
    models.push({
      id,
      name: text(slot.name),
      description: text(slot.description),
      imageUrl: modelImage(id, slot.icon_file),
      status: type === 'RVC' ? 'ready' : type === 'RESERVED_FOR_SAMPLE' ? 'pending' : type === 'BROKEN' ? 'broken' : 'unsupported',
      tags,
    });
  }

  return {
    models: models.sort((a, b) => a.id - b.id),
    currentModelId: currentId >= 0 ? currentId : null,
  };
}

async function getJson(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(path, { method: 'GET', signal, cache: 'no-store' });
  if (!response.ok) throw new CatalogError('http', response.status);
  try {
    return await response.json();
  } catch (error) {
    if (signal.aborted) throw error;
    invalidResponse();
  }
}

export async function loadModelCatalog(signal: AbortSignal): Promise<ModelCatalog> {
  const [slots, configuration] = await Promise.all([
    getJson('/api/slot-manager/slots', signal),
    getJson('/api/configuration-manager/configuration', signal),
  ]);
  return parseCatalog(slots, configuration);
}
