import { getContext, setContext } from 'svelte';
import { operateNative, readNativeActive, updateConfiguration, updateModelSettings } from './api';
import { ApiError } from './api-error';
import type { ModelCatalogState } from './catalog.svelte';
import type { ConfigurationEdits, ModelEdits } from './settings';

const contextKey = Symbol('native-session');
const updateIntervalMs = 100;
type PendingWrite =
  | { kind: 'configuration'; edits: ConfigurationEdits }
  | { kind: 'model'; id: number; edits: ModelEdits };

export class NativeSession {
  draft = $state<ConfigurationEdits>({});
  modelDraft = $state<{ id: number; edits: ModelEdits } | null>(null);
  isSaving = $state(false);
  saved = $state(false);
  error = $state<ApiError | null>(null);
  active = $state<boolean | null>(null);
  statusError = $state(false);
  operation = $state<'start' | 'stop' | null>(null);
  operationError = $state<ApiError | null>(null);
  private timer: ReturnType<typeof setTimeout> | undefined;
  private poll: ReturnType<typeof setTimeout> | undefined;
  private flight: Promise<void> | null = null;
  private requests = new Set<AbortController>();
  private lastStarted = -Infinity;
  private nextWrite: PendingWrite['kind'] = 'configuration';
  private urgent = false;
  private statusVersion = 0;
  private disposed = false;

  constructor(readonly catalog: ModelCatalogState) {}

  get settings() { return this.catalog.settings ? { ...this.catalog.settings, ...this.draft } : null; }
  get currentModelId() { return this.draft.currentModelId ?? this.catalog.currentModelId; }
  get currentModel() { return this.catalog.models.find(model => model.id === this.currentModelId) ?? null; }
  get modelSettings() {
    const model = this.currentModel;
    if (!model?.settings) return null;
    return this.modelDraft?.id === model.id ? { ...model.settings, ...this.modelDraft.edits } : model.settings;
  }
  get dirty() { return Object.keys(this.draft).length > 0 || this.modelDraft !== null; }
  get canReload() { return !this.isSaving && !this.operation && !this.dirty && this.catalog.state.status !== 'loading'; }
  get canConfigure() {
    return this.catalog.state.status === 'ready' && this.active === false && !this.operation && !this.isSaving && !this.dirty;
  }
  get canAdjustGain() {
    return this.catalog.state.status === 'ready' && this.settings?.inputMode === 'server' && !this.operation;
  }
  get canAdjustModel() {
    return this.canAdjustGain && this.currentModel?.status === 'ready' && this.draft.currentModelId === undefined
      && (this.modelDraft === null || this.modelDraft.id === this.currentModelId);
  }
  get canAdjustFilter() {
    return this.canAdjustGain && this.currentModel?.status === 'ready' && this.draft.currentModelId === undefined;
  }
  get startBlockReason() {
    if (this.operation) return 'operation';
    if (this.catalog.state.status === 'loading') return 'loading';
    if (this.catalog.state.status === 'error') return 'load_error';
    if (this.active === null) return 'unknown';
    if (this.active) return 'running';
    if (this.error) return 'save_error';
    if (this.isSaving || this.dirty) return 'saving';
    const settings = this.settings!;
    if (settings.inputMode !== 'server') return 'mode';
    if (this.currentModel?.status !== 'ready') return 'model';
    const devices = this.catalog.deviceState;
    if (devices.status === 'loading') return 'devices_loading';
    if (devices.status === 'error') return 'devices_error';
    if (!devices.devices.input.some(device => device.id === settings.inputDevice)) return 'input';
    if (!devices.devices.output.some(device => device.id === settings.outputDevice)) return 'output';
    if (settings.monitorDevice !== -1 && !devices.devices.output.some(device => device.id === settings.monitorDevice)) return 'monitor';
    return null;
  }
  get canStart() { return this.startBlockReason === null; }
  get canStop() { return this.active !== false && !this.operation; }

  async mount() {
    await this.reload();
    this.schedulePoll();
  }

  async reload() {
    if (this.disposed || this.isSaving || this.operation || this.dirty) return;
    this.saved = false;
    this.error = null;
    this.operationError = null;
    this.active = null;
    await Promise.all([this.catalog.reload(), this.refreshActive()]);
  }

  setGain(key: 'inputGain' | 'outputGain', value: number) {
    if (!this.canAdjustGain || this.settings?.[key] == null || !Number.isFinite(value) || value < 0 || value > 10) return;
    if (this.settings[key] === value) return;
    this.edit({ [key]: value });
  }

  setNoiseGate(value: number) {
    if (!this.canAdjustGain || this.settings?.noiseGate == null || !Number.isInteger(value) || value < -120 || value > 0) return;
    if (this.settings.noiseGate !== value) this.edit({ noiseGate: value });
  }

  setFilter(key: 'highPassEnabled' | 'lowPassEnabled', value: boolean): void;
  setFilter(key: 'highPassCutoff' | 'lowPassCutoff', value: number): void;
  setFilter(key: 'highPassEnabled' | 'lowPassEnabled' | 'highPassCutoff' | 'lowPassCutoff', value: boolean | number) {
    if (!this.canAdjustFilter || this.settings?.[key] == null || this.settings[key] === value) return;
    if (typeof value === 'number' && (!Number.isInteger(value) || value <= 0 || value > 15000)) return;
    this.edit({ [key]: value }, typeof value === 'boolean');
  }

  setModelValue(key: keyof ModelEdits, value: number) {
    const model = this.currentModel;
    const settings = this.modelSettings;
    if (!this.canAdjustModel || !model || !settings || settings[key] === null || !Number.isFinite(value)) return;
    if (key === 'pitch' && (!settings.supportsPitch || !Number.isInteger(value) || value < -24 || value > 24)) return;
    if (key === 'indexRatio' && (!settings.hasIndex || value < 0 || value > 1)) return;
    if (settings[key] === value) return;
    this.modelDraft = { id: model.id, edits: { ...this.modelDraft?.edits, [key]: value } };
    this.saved = false;
    this.schedule();
  }

  selectModel(id: number) {
    if (!this.canConfigure || !this.catalog.models.some(model => model.id === id && model.status === 'ready')) return;
    if (id !== this.currentModelId) this.edit({ currentModelId: id }, true);
  }

  selectDevice(key: 'inputDevice' | 'outputDevice' | 'monitorDevice', id: number) {
    if (!this.canConfigure || this.settings?.inputMode !== 'server') return;
    const state = this.catalog.deviceState;
    if (state.status !== 'ready' || !Number.isSafeInteger(id)) return;
    const devices = key === 'inputDevice' ? state.devices.input : state.devices.output;
    if (id !== -1 && !devices.some(device => device.id === id)) return;
    if (id === this.settings[key]) return;
    // A different device may not support the previous device's fixed sample rate.
    const rateKey = `${key}Rate` as 'inputDeviceRate' | 'outputDeviceRate' | 'monitorDeviceRate';
    this.edit({ [key]: id, [rateKey]: -1 }, true);
  }

  useServerMode() {
    if (this.canConfigure && this.settings?.inputMode !== 'server') this.edit({ inputMode: 'server' }, true);
  }

  private edit(edits: ConfigurationEdits, immediate = false) {
    this.draft = { ...this.draft, ...edits };
    this.saved = false;
    this.schedule(immediate);
  }

  flush() { this.schedule(true); }

  retry() {
    if (this.isSaving || this.operation || !this.dirty) return;
    this.error = null;
    this.schedule(true);
  }

  async discard() {
    if (this.isSaving || this.operation) return;
    clearTimeout(this.timer);
    this.draft = {};
    this.modelDraft = null;
    await this.reload();
  }

  private schedule(immediate = false) {
    if (!this.dirty) return;
    this.urgent ||= immediate;
    if (this.disposed || this.isSaving || this.operation || this.error) return;
    clearTimeout(this.timer);
    const delay = this.urgent ? 0 : Math.max(0, updateIntervalMs - (performance.now() - this.lastStarted));
    this.timer = setTimeout(() => { void this.save(); }, delay);
  }

  private save(): Promise<void> {
    if (this.flight) return this.flight;
    if (this.disposed || !this.dirty || this.error || this.operation) return Promise.resolve();
    this.isSaving = true;
    this.urgent = false;
    this.lastStarted = performance.now();
    // Alternate when both have edits so a continuous volume drag cannot starve model settings.
    const sent: PendingWrite = this.modelDraft && (this.nextWrite === 'model' || Object.keys(this.draft).length === 0)
      ? { kind: 'model', id: this.modelDraft.id, edits: { ...this.modelDraft.edits } }
      : { kind: 'configuration', edits: { ...this.draft } };
    this.nextWrite = sent.kind === 'model' ? 'configuration' : 'model';
    this.flight = this.persist(sent);
    return this.flight;
  }

  private async persist(sent: PendingWrite) {
    try {
      if (sent.kind === 'configuration') {
        const confirmed = await this.request(signal => updateConfiguration(sent.edits, signal));
        if (this.disposed) return;
        this.catalog.applyConfiguration(confirmed);
        // A response acknowledges only the values it sent, never newer interactions.
        this.draft = Object.fromEntries(Object.entries(this.draft).filter(
          ([key, value]) => sent.edits[key as keyof ConfigurationEdits] !== value,
        ));
      } else {
        const confirmed = await this.request(signal => updateModelSettings(sent.id, sent.edits, signal));
        if (this.disposed) return;
        this.catalog.applyModel(confirmed);
        if (this.modelDraft?.id === sent.id) {
          const edits = Object.fromEntries(Object.entries(this.modelDraft.edits).filter(
            ([key, value]) => sent.edits[key as keyof ModelEdits] !== value,
          ));
          this.modelDraft = Object.keys(edits).length ? { id: sent.id, edits } : null;
        }
      }
      this.saved = !this.dirty;
    } catch (error) {
      if (!this.disposed) this.error = this.apiError(error);
    } finally {
      this.isSaving = false;
      this.flight = null;
      this.schedule();
    }
  }

  async operate(operation: 'start' | 'stop') {
    if (this.disposed || (operation === 'start' ? !this.canStart : !this.canStop)) return;
    this.operation = operation;
    this.operationError = null;
    ++this.statusVersion;
    clearTimeout(this.timer);
    try {
      // Stop also waits for the current PUT, but is not blocked by a failed save.
      await this.flight;
      if (this.disposed) return;
      this.active = await this.request(async signal => {
        if (operation === 'start') {
          // Reapply/confirm the selected model through the existing PUT before starting.
          // This also initializes a pipeline when a previous startup load failed.
          const confirmed = await updateConfiguration({ currentModelId: this.currentModelId! }, signal);
          if (!this.disposed) this.catalog.applyConfiguration(confirmed);
          if (confirmed.settings.inputMode !== 'server') throw new ApiError('not_applied');
        }
        return operateNative(operation, signal);
      });
      this.statusError = false;
    } catch (error) {
      if (!this.disposed) {
        this.operationError = this.apiError(error);
        this.active = null;
      }
    } finally {
      this.operation = null;
      if (!this.disposed) {
        await this.refreshActive();
        this.schedule();
      }
    }
  }

  private async refreshActive() {
    const version = ++this.statusVersion;
    try {
      const active = await this.request(readNativeActive, 8_000);
      if (!this.disposed && version === this.statusVersion) {
        this.active = active;
        this.statusError = false;
      }
    } catch {
      if (!this.disposed && version === this.statusVersion) {
        this.active = null;
        this.statusError = true;
      }
    }
  }

  private schedulePoll() {
    if (this.disposed) return;
    this.poll = setTimeout(async () => {
      if (!this.operation && !this.isSaving) await this.refreshActive();
      this.schedulePoll();
    }, 2_000);
  }

  private async request<T>(task: (signal: AbortSignal) => Promise<T>, timeoutMs = 30_000): Promise<T> {
    const controller = new AbortController();
    this.requests.add(controller);
    const timeout = setTimeout(() => controller.abort('timeout'), timeoutMs);
    try { return await task(controller.signal); }
    catch (error) { throw controller.signal.reason === 'timeout' ? new ApiError('timeout') : error; }
    finally { clearTimeout(timeout); this.requests.delete(controller); }
  }

  private apiError(error: unknown) { return error instanceof ApiError ? error : new ApiError('network'); }

  dispose() {
    this.disposed = true;
    ++this.statusVersion;
    clearTimeout(this.timer);
    clearTimeout(this.poll);
    for (const request of this.requests) request.abort();
    this.catalog.dispose();
  }
}

export function provideSession(catalog: ModelCatalogState) {
  return setContext(contextKey, new NativeSession(catalog));
}

export function useSession(): NativeSession { return getContext(contextKey); }
