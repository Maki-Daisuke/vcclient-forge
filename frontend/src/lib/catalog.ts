export interface ModelSummary {
  id: number;
  name: string;
  description: string;
  imageUrl: string | null;
  status: 'ready' | 'pending' | 'broken' | 'unsupported';
  tags: string[];
}

export interface ModelCatalog {
  models: ModelSummary[];
  currentModelId: number | null;
}

export type CatalogErrorCode = 'network' | 'http' | 'invalid_response' | 'timeout';

export class CatalogError extends Error {
  constructor(public code: CatalogErrorCode, public status?: number) {
    super(code);
  }
}

export type CatalogLoader = (signal: AbortSignal) => Promise<ModelCatalog>;
