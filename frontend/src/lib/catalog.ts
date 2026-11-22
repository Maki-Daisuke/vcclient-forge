import type { ConfigurationSnapshot, ModelSettingsSnapshot } from './settings';

export interface ModelSummary {
  id: string;
  name: string;
  imageUrl: string | null;
  status: 'ready' | 'pending' | 'broken' | 'unsupported';
  tags: string[];
  settings: ModelSettingsSnapshot | null;
}

export interface ModelCatalog {
  models: ModelSummary[];
  currentModelId: string | null;
  settings: ConfigurationSnapshot;
}

export type CatalogLoader = (signal: AbortSignal) => Promise<ModelCatalog>;
