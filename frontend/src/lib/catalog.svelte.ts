import { getContext, setContext } from 'svelte';
import { loadAudioDevices, loadComputeDevices, loadModelCatalog, type ComputeDevice } from './api';
import type { CatalogLoader, ModelCatalog, ModelSummary } from './catalog';
import type { AudioDevices } from './audio-devices';
import { ApiError } from './api-error';
import type { ConfirmedConfiguration } from './settings';

type CatalogState =
  | { status: 'loading' }
  | { status: 'ready'; catalog: ModelCatalog }
  | { status: 'error'; error: ApiError };

type DeviceState =
  | { status: 'loading' }
  | { status: 'ready'; devices: AudioDevices }
  | { status: 'error' };

type ComputeDeviceState =
  | { status: 'loading' }
  | { status: 'ready'; devices: ComputeDevice[] }
  | { status: 'error' };

const contextKey = Symbol('catalog');

export class ModelCatalogState {
  state = $state<CatalogState>({ status: 'loading' });
  deviceState = $state<DeviceState>({ status: 'loading' });
  computeDeviceState = $state<ComputeDeviceState>({ status: 'loading' });
  private request: AbortController | null = null;

  constructor(
    private load: CatalogLoader = loadModelCatalog,
    private loadDevices = loadAudioDevices,
    private loadCompute = loadComputeDevices,
  ) {}

  get models() {
    return this.state.status === 'ready' ? this.state.catalog.models : [];
  }

  get currentModelId() {
    return this.state.status === 'ready' ? this.state.catalog.currentModelId : null;
  }

  get currentModel() {
    return this.models.find(model => model.id === this.currentModelId) ?? null;
  }

  get settings() {
    return this.state.status === 'ready' ? this.state.catalog.settings : null;
  }

  applyConfiguration(configuration: ConfirmedConfiguration) {
    if (this.state.status === 'ready') {
      this.state = { status: 'ready', catalog: { ...this.state.catalog, ...configuration } };
    }
  }

  applyModel(model: ModelSummary) {
    if (this.state.status === 'ready') {
      this.state = { status: 'ready', catalog: {
        ...this.state.catalog,
        models: this.state.catalog.models.map(current => current.id === model.id ? model : current),
      } };
    }
  }

  async reload() {
    this.request?.abort();
    const request = new AbortController();
    this.request = request;
    this.state = { status: 'loading' };
    this.deviceState = { status: 'loading' };
    this.computeDeviceState = { status: 'loading' };
    const timeout = setTimeout(() => request.abort('timeout'), 8_000);
    const devicesRequest = this.reloadDevices(request);
    const computeRequest = this.reloadComputeDevices(request);
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
          ? new ApiError('timeout')
          : error instanceof ApiError ? error : new ApiError('network'),
      };
    } finally {
      await Promise.all([devicesRequest, computeRequest]);
      clearTimeout(timeout);
      request.abort();
      if (this.request === request) this.request = null;
    }
  }

  private async reloadDevices(request: AbortController) {
    try {
      const devices = await this.loadDevices(request.signal);
      if (this.request === request && !request.signal.aborted) {
        this.deviceState = { status: 'ready', devices };
      }
    } catch {
      if (this.request === request) this.deviceState = { status: 'error' };
    }
  }

  private async reloadComputeDevices(request: AbortController) {
    try {
      const devices = await this.loadCompute(request.signal);
      if (this.request === request && !request.signal.aborted) this.computeDeviceState = { status: 'ready', devices };
    } catch {
      if (this.request === request) this.computeDeviceState = { status: 'error' };
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
