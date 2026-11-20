import { BlobReader, BlobWriter, ZipReader } from '@zip.js/zip.js';

export interface ArchiveEntry { id: number; name: string; }
export interface ModelArchive { file: File; models: ArchiveEntry[]; indexes: ArchiveEntry[]; }

export async function inspectModelArchive(file: File): Promise<ModelArchive> {
  const reader = new ZipReader(new BlobReader(file));
  try {
    const entries = await reader.getEntries();
    const usable = entries.map((entry, id) => ({ entry, id }))
      .filter(({ entry }) => !entry.directory && !entry.symlink && !entry.filename.startsWith('__MACOSX/')
        && !entry.filename.split('/').at(-1)?.startsWith('._') && entry.uncompressedSize > 0);
    const convert = ({ entry, id }: typeof usable[number]) => ({ id, name: entry.filename });
    const models = usable.filter(({ entry }) => /\.(pth|onnx)$/i.test(entry.filename)).map(convert);
    const indexes = usable.filter(({ entry }) => /\.index$/i.test(entry.filename)).map(convert);
    if (!models.length) throw new Error('no_model');
    return { file, models, indexes };
  } finally { await reader.close(); }
}

export async function extractModelArchive(archive: ModelArchive, modelId: number, indexId: number | null): Promise<{ model: File; index: File | null }> {
  const reader = new ZipReader(new BlobReader(archive.file));
  try {
    const entries = await reader.getEntries();
    async function extract(id: number, allowed: ArchiveEntry[]): Promise<File> {
      const chosen = allowed.find(item => item.id === id);
      const entry = entries[id];
      if (!chosen || !entry || entry.filename !== chosen.name || entry.encrypted || entry.directory || !entry.getData) throw new Error('invalid_entry');
      const blob = await entry.getData(new BlobWriter(), { checkSignature: true });
      const name = entry.filename.replaceAll('\\', '/').split('/').at(-1);
      if (!name || blob.size === 0 || blob.size !== entry.uncompressedSize) throw new Error('invalid_entry');
      return new File([blob], name, { type: 'application/octet-stream' });
    }
    return { model: await extract(modelId, archive.models), index: indexId === null ? null : await extract(indexId, archive.indexes) };
  } finally { await reader.close(); }
}
