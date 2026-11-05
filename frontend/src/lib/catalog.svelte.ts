import { getContext, setContext } from 'svelte';
import { loadModelCatalog } from './api';
import { CatalogError, type CatalogLoader, type ModelCatalog } from './catalog';

type CatalogState =
  | { status: 'loading' }
  | { status: 'ready'; catalog: ModelCatalog }
  | { status: 'error'; error: CatalogError };

const contextKey = Symbol('catalog');

export class ModelCatalogState {
  state = $state<CatalogState>({ status: 'loading' });
  private request: AbortController | null = null;

  constructor(private load: CatalogLoader = loadModelCatalog) {}

  get models() {
    return this.state.status === 'ready' ? this.state.catalog.models : [];
  }

  get currentModelId() {
    return this.state.status === 'ready' ? this.state.catalog.currentModelId : null;
  }

  get currentModel() {
    return this.models.find(model => model.id === this.currentModelId) ?? null;
  }

  async reload() {
    this.request?.abort();
    const request = new AbortController();
    this.request = request;
    this.state = { status: 'loading' };
    const timeout = setTimeout(() => request.abort('timeout'), 8_000);
    try {
      const catalog = await this.load(request.signal);
      if (this.request === request && !request.signal.aborted) {
        this.state = { status: 'ready', catalog };
      }
    } catch (error) {
      if (this.request !== request) return;
      this.state = {
        status: 'error',
        error: request.signal.reason === 'timeout'
          ? new CatalogError('timeout')
          : error instanceof CatalogError ? error : new CatalogError('network'),
      };
    } finally {
      clearTimeout(timeout);
      request.abort();
      if (this.request === request) this.request = null;
    }
  }

  dispose() {
    this.request?.abort();
    this.request = null;
  }
}

export function provideCatalog() {
  return setContext(contextKey, new ModelCatalogState());
}

export function useCatalog(): ModelCatalogState {
  return getContext(contextKey);
}
