import { getContext, setContext } from 'svelte';
import { operateNative, organizeModels, readAudioSampleRates, readModel, readNativeActive, setModelIcon, setModelName, updateConfiguration, updateModelSettings } from './api';
import { ClientAudio } from './client-audio.svelte';
import { ApiError } from './api-error';
import { importModel, uploadFile } from './model-upload';
import type { ModelCatalogState } from './catalog.svelte';
import type { ConfigurationEdits, ModelEdits } from './settings';

const contextKey = Symbol('native-session');
const updateIntervalMs = 100;
type PendingWrite =
  | { kind: 'configuration'; edits: ConfigurationEdits }
  | { kind: 'model'; id: number; edits: ModelEdits };

export class NativeSession {
  readonly clientAudio = new ClientAudio();
  private clientActive = false;
  draft = $state<ConfigurationEdits>({});
  modelDraft = $state<{ id: number; edits: ModelEdits } | null>(null);
  isSaving = $state(false);
  saved = $state(false);
  error = $state<ApiError | null>(null);
  active = $state<boolean | null>(null);
  statusError = $state(false);
  recordingCompleted = $state(false);
  recordingArmed = $state(false);
  uploadStatus = $state<'idle' | 'uploading' | 'registering' | 'success' | 'refresh_failed' | 'error' | 'uncertain'>('idle');
  uploadError = $state<ApiError | null>(null);
  uploadBytes = $state(0);
  uploadTotal = $state(0);
  operation = $state<'start' | 'stop' | null>(null);
  organizing = $state(false);
  modelInfoSaving = $state(false);
  modelInfoError = $state<ApiError | null>(null);
  modelOperationError = $state<ApiError | null>(null);
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
  get importing() { return this.uploadStatus === 'uploading' || this.uploadStatus === 'registering'; }
  get canReload() { return !this.modelInfoSaving && !this.organizing && !this.importing && !this.isSaving && !this.operation && !this.dirty && this.catalog.state.status !== 'loading'; }
  get canConfigure() {
    return this.catalog.state.status === 'ready' && this.active === false && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation && !this.isSaving && !this.dirty;
  }
  get canAdjustGain() {
    return this.catalog.state.status === 'ready' && this.settings?.inputMode === 'server' && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation;
  }
  get canAdjustModel() {
    return this.catalog.state.status === 'ready' && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation
      && this.currentModel?.status === 'ready' && this.draft.currentModelId === undefined
      && (this.modelDraft === null || this.modelDraft.id === this.currentModelId);
  }
  get canAdjustFilter() {
    return this.canAdjustGain && this.currentModel?.status === 'ready' && this.draft.currentModelId === undefined;
  }
  get startBlockReason() {
    if (this.importing || this.organizing || this.modelInfoSaving) return 'saving';
    if (this.operation) return 'operation';
    if (this.catalog.state.status === 'loading') return 'loading';
    if (this.catalog.state.status === 'error') return 'load_error';
    if (this.active === null) return 'unknown';
    if (this.active) return 'running';
    if (this.error) return 'save_error';
    if (this.isSaving || this.dirty) return 'saving';
    const settings = this.settings!;
    if (!settings.inputMode) return 'mode';
    if (settings.inputMode === 'client') return this.currentModel?.status === 'ready' ? null : 'model';
    const devices = this.catalog.deviceState;
    if (devices.status === 'loading') return 'devices_loading';
    if (devices.status === 'error') return 'devices_error';
    if (!devices.devices.input.some(device => device.id === settings.inputDevice)) return 'input';
    if (!devices.devices.output.some(device => device.id === settings.outputDevice)) return 'output';
    if (settings.monitorDevice !== -1 && !devices.devices.output.some(device => device.id === settings.monitorDevice)) return 'monitor';
    if (this.currentModel?.status !== 'ready') return 'model';
    return null;
  }
  get canStart() { return this.startBlockReason === null; }
  get canStop() { return this.active !== false && !this.operation; }

  async mount() {
    await this.reload();
    if (this.settings?.inputMode === 'client') await this.clientAudio.refreshDevices().catch(() => {});
    this.schedulePoll();
  }

  async organizeModels(order: number[], deleteSelected = false): Promise<boolean> {
    if (!this.canConfigure) return false;
    this.organizing = true;
    this.modelOperationError = null;
    try {
      await this.request(signal => organizeModels(order, deleteSelected, signal), 120_000);
      await this.catalog.reload();
      if (this.catalog.state.status !== 'ready') throw new ApiError('invalid_response');
      return true;
    } catch (error) {
      this.modelOperationError = this.apiError(error);
      return false;
    } finally {
      this.organizing = false;
    }
  }

  async saveModelInfo(id: number, name: string, icon: File | null): Promise<boolean> {
    const model = this.currentModel;
    if (!this.canConfigure || !model || model.id !== id || model.status !== 'ready' || !name.trim()) return false;
    const extension = icon ? /\.(png|jpe?g|webp|gif|avif|bmp)$/i.exec(icon.name)?.[0].toLowerCase() : null;
    if (icon && (!extension || !icon.size || (icon.type && !icon.type.startsWith('image/')))) return false;
    this.modelInfoSaving = true;
    this.modelInfoError = null;
    try {
      await this.request(async signal => {
        if (await readNativeActive(signal)) throw new ApiError('active');
        if (icon && extension) {
          const filename = await uploadFile(icon, extension, signal, () => {});
          this.catalog.applyModel(await setModelIcon(id, filename, signal));
        }
        if (name !== model.name) this.catalog.applyModel(await setModelName(id, name, signal));
      }, 120_000);
      return true;
    } catch (error) {
      this.modelInfoError = this.apiError(error);
      try { this.catalog.applyModel(await this.request(signal => readModel(id, signal))); } catch { /* Keep the draft for retry. */ }
      return false;
    } finally {
      this.modelInfoSaving = false;
    }
  }

  async uploadModel(model: File, index: File | null) {
    if (!this.canConfigure) return;
    this.uploadStatus = 'uploading';
    this.uploadError = null;
    this.uploadBytes = 0;
    this.uploadTotal = model.size + (index?.size ?? 0);
    const phase = { registering: false };
    try {
      await this.request(signal => importModel(model, index, signal,
        bytes => { this.uploadBytes += bytes; }, () => { phase.registering = true; this.uploadStatus = 'registering'; }), 30 * 60_000);
      if (this.disposed) return;
      await this.catalog.reload();
      if (!this.disposed) this.uploadStatus = this.catalog.state.status === 'ready' ? 'success' : 'refresh_failed';
    } catch (error) {
      if (!this.disposed) {
        this.uploadError = this.apiError(error);
        this.uploadStatus = phase.registering && (this.uploadError.code === 'network' || this.uploadError.code === 'timeout' || this.uploadError.code === 'invalid_response') ? 'uncertain' : 'error';
      }
    }
  }

  resetUpload() {
    if (!this.importing) { this.uploadStatus = 'idle'; this.uploadError = null; }
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

  get canTogglePassThrough() {
    return this.catalog.state.status === 'ready' && this.settings?.inputMode != null
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation
      && this.settings.passThrough != null && this.settings.recording === false && !this.recordingArmed;
  }

  togglePassThrough() {
    if (!this.canTogglePassThrough || !this.settings) return;
    this.edit({ passThrough: !this.settings.passThrough }, true);
  }

  get canToggleRecording() {
    const settings = this.settings;
    return this.catalog.state.status === 'ready' && settings?.inputMode === 'server' && settings.recording !== null
      && !this.modelInfoSaving && !this.organizing && !this.importing && !this.operation && !this.isSaving && !this.dirty
      && this.active !== null && (settings.recording === true || settings.passThrough === false);
  }

  toggleRecording() {
    if (!this.canToggleRecording || !this.settings) return;
    this.recordingCompleted = false;
    if (this.settings.recording === false && this.active === false) {
      this.recordingArmed = !this.recordingArmed;
      return;
    }
    if (this.settings.recording === false && this.recordingArmed) {
      this.recordingArmed = false;
      return;
    }
    this.recordingArmed = !this.settings.recording;
    this.edit({ recording: !this.settings.recording }, true);
  }

  setFilter(key: 'highPassEnabled' | 'lowPassEnabled', value: boolean): void;
  setFilter(key: 'highPassCutoff' | 'lowPassCutoff', value: number): void;
  setFilter(key: 'highPassEnabled' | 'lowPassEnabled' | 'highPassCutoff' | 'lowPassCutoff', value: boolean | number) {
    if (!this.canAdjustFilter || this.settings?.[key] == null || this.settings[key] === value) return;
    if (typeof value === 'number' && (!Number.isInteger(value) || value <= 0 || value > 15000)) return;
    this.edit({ [key]: value }, typeof value === 'boolean');
  }

  setModelValue(key: 'pitch' | 'indexRatio', value: number) {
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

  setPitchEstimator(value: 'rmvpe' | 'fcpe') {
    const model = this.currentModel;
    if (!this.canConfigure || this.settings?.inputMode !== 'server' || model?.status !== 'ready'
      || !model.settings?.supportsPitch || !model.settings.pitchEstimator || model.settings.pitchEstimator === value) return;
    this.modelDraft = { id: model.id, edits: { pitchEstimator: value } };
    this.saved = false;
    this.schedule(true);
  }

  selectModel(id: number) {
    if (!this.canConfigure || !this.catalog.models.some(model => model.id === id && model.status === 'ready')) return;
    if (id !== this.currentModelId) this.edit({ currentModelId: id }, true);
  }

  selectComputeDevice(id: number) {
    const devices = this.catalog.computeDeviceState;
    if (!this.canConfigure || this.settings?.inputMode !== 'server' || this.settings.gpuDevice === null
      || devices.status !== 'ready' || !Number.isSafeInteger(id) || !devices.devices.some(device => device.id === id)
      || id === this.settings.gpuDevice) return;
    this.edit({ gpuDevice: id }, true);
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

  useClientMode() {
    if (this.canConfigure && this.settings?.inputMode !== 'client') {
      this.recordingArmed = false;
      this.edit({ inputMode: 'client' }, true);
      void this.clientAudio.refreshDevices().catch(() => {});
    }
  }

  setWasapiExclusive(value: boolean) {
    if (!this.canConfigure || this.settings?.inputMode !== 'server' || this.settings.wasapiExclusive == null
      || this.settings.wasapiExclusive === value) return;
    this.edit({ wasapiExclusive: value }, true);
  }

  setExtraSeconds(value: number) {
    if (!this.canConfigure || this.settings?.inputMode !== 'server' || this.settings.extraSeconds == null
      || !Number.isFinite(value) || value < 0.01 || value > 10 || value === this.settings.extraSeconds) return;
    this.edit({ extraSeconds: value }, true);
  }

  setCrossfadeSeconds(value: number) {
    if (!this.canConfigure || this.settings?.inputMode !== 'server' || this.settings.crossfadeSeconds == null
      || !Number.isFinite(value) || (value !== 0 && (value < 0.01 || value > 0.15)) || value === this.settings.crossfadeSeconds) return;
    this.edit({ crossfadeSeconds: value }, true);
  }

  setChunkSeconds(value: number) {
    const model = this.currentModel;
    if (!this.canConfigure || this.settings?.inputMode !== 'server' || model?.status !== 'ready'
      || model.settings?.chunkSeconds == null || !Number.isFinite(value) || value < 0.05 || value > 5
      || value === model.settings.chunkSeconds) return;
    this.modelDraft = { id: model.id, edits: { chunkSeconds: value } };
    this.saved = false;
    this.schedule(true);
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
        const confirmed = await this.request(signal => updateConfiguration(sent.edits, signal), sent.edits.gpuDevice !== undefined ? 120_000 : 30_000);
        if (this.disposed) return;
        this.catalog.applyConfiguration(confirmed);
        if (sent.edits.recording === false) this.recordingCompleted = true;
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
      if (this.settings?.inputMode === 'client') {
        if (operation === 'start') {
          await this.request(signal => operateNative('stop', signal));
          const confirmed = await this.request(signal => updateConfiguration({ currentModelId: this.currentModelId! }, signal));
          this.catalog.applyConfiguration(confirmed);
          if (confirmed.settings.inputMode !== 'client') throw new ApiError('not_applied');
          const rates = await this.request(readAudioSampleRates);
          if (!rates.input || !rates.output) throw new ApiError('invalid_response');
          await this.clientAudio.start(rates.input, rates.output, error => {
            this.clientAudio.stop();
            this.clientActive = false;
            this.active = false;
            this.operationError = new ApiError('client_audio', undefined, error.message);
            void this.request(signal => operateNative('stop', signal)).catch(error => {
              if (!this.disposed) this.operationError = this.apiError(error);
            });
          });
          if (this.disposed) return;
          this.clientActive = true;
          this.active = true;
        } else {
          this.clientAudio.stop();
          this.clientActive = false;
          this.active = false;
          await this.request(signal => operateNative('stop', signal));
        }
        this.statusError = false;
        return;
      }
      this.active = await this.request(async signal => {
        if (operation === 'start') {
          // Reapply/confirm the selected model through the existing PUT before starting.
          // This also initializes a pipeline when a previous startup load failed.
          const confirmed = await updateConfiguration({ currentModelId: this.currentModelId! }, signal);
          if (!this.disposed) this.catalog.applyConfiguration(confirmed);
          if (confirmed.settings.inputMode !== 'server') throw new ApiError('not_applied');
          const active = await operateNative('start', signal);
          if (this.recordingArmed) {
            this.recordingCompleted = false;
            const recording = await updateConfiguration({ recording: true }, signal);
            if (!this.disposed) this.catalog.applyConfiguration(recording);
          }
          return active;
        }
        let recordingError: unknown;
        if (this.settings?.recording === true) {
          try {
            const recording = await updateConfiguration({ recording: false }, signal);
            if (!this.disposed) {
              this.catalog.applyConfiguration(recording);
              this.recordingArmed = true;
              this.recordingCompleted = false;
              this.recordingCompleted = true;
            }
          } catch (error) { recordingError = error; }
        }
        const active = await operateNative('stop', signal);
        if (recordingError) throw recordingError;
        return active;
      });
      this.statusError = false;
    } catch (error) {
      if (!this.disposed) {
        this.operationError = error instanceof ApiError ? error : this.settings?.inputMode === 'client'
          ? new ApiError('client_audio', undefined, error instanceof Error ? error.message : undefined) : this.apiError(error);
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
        this.active = active || this.clientActive;
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
    this.clientAudio.stop();
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
