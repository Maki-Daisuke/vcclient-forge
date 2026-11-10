import { io, type Socket } from 'socket.io-client';
import { readAudioSampleRates } from './api';

type Levels = { input: number; output: number };
export type BufferPoint = { time: number; seconds: number };
type SampleRates = { input: number | null; output: number | null };
type PendingSample = { samples: number; time: number };
export const bufferHistoryDurationMs = 20_000;
const maxHistory = 100;

function recentHistory(history: BufferPoint[], now: number): BufferPoint[] {
  return history.filter(point => point.time >= now - bufferHistoryDurationMs).slice(-maxHistory);
}

function validNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

export class AudioMeters {
  levels = $state<Levels | null>(null);
  status = $state<'idle' | 'connecting' | 'connected' | 'unavailable'>('idle');
  inputBuffer = $state<number | null>(null);
  outputBuffer = $state<number | null>(null);
  conversionTimeSeconds = $state<number | null>(null);
  inputHistory = $state<BufferPoint[]>([]);
  outputHistory = $state<BufferPoint[]>([]);
  private socket: Socket | null = null;
  private levelTimer: ReturnType<typeof setTimeout> | undefined;
  private inputTimer: ReturnType<typeof setTimeout> | undefined;
  private outputTimer: ReturnType<typeof setTimeout> | undefined;
  private conversionTimer: ReturnType<typeof setTimeout> | undefined;
  private rateController: AbortController | null = null;
  private rates: SampleRates = { input: null, output: null };
  private pendingInput: PendingSample | null = null;
  private pendingOutput: PendingSample | null = null;
  private lastRateAttempt = 0;
  private outputEnabled = false;
  private processEnabled = false;
  private outputInterval = 0.2;
  private processInterval = 1;

  setEnabled(active: boolean, outputEnabled: boolean, processEnabled: boolean, outputInterval: number | null, processInterval: number | null, chunkSeconds: number | null) {
    this.outputEnabled = outputEnabled;
    this.processEnabled = processEnabled;
    this.outputInterval = outputInterval !== null && Number.isFinite(outputInterval) && outputInterval > 0 ? outputInterval : 0.2;
    const requestedInterval = processInterval !== null && Number.isFinite(processInterval) && processInterval > 0 ? processInterval : 1;
    this.processInterval = chunkSeconds !== null && Number.isFinite(chunkSeconds) && chunkSeconds > 0
      ? Math.max(requestedInterval, chunkSeconds) : requestedInterval;
    if (!active || (!outputEnabled && !processEnabled)) { this.dispose(); return; }
    if (!outputEnabled) { this.clearLevels(); this.clearOutput(); }
    if (!processEnabled) { this.clearInput(); this.clearConversionTime(); }
    if (this.socket) return;
    this.status = 'connecting';
    const socket = io('/test', { transports: ['websocket'] });
    this.socket = socket;
    socket.on('connect', () => {
      this.status = 'connected';
      if (this.outputEnabled) this.watchLevels(this.outputInterval);
    });
    socket.on('disconnect', () => this.clear('unavailable'));
    socket.on('connect_error', () => this.clear('unavailable'));
    socket.on('data', (message: unknown) => {
      if (this.socket !== socket || !Array.isArray(message) || typeof message[1] !== 'string' || message[1].length > 4096) return;
      if (message[0] !== 'realtime_output_status' && message[0] !== 'realtime_process_status') return;
      let value: unknown;
      try { value = JSON.parse(message[1]); } catch { return; }
      if (!value || typeof value !== 'object' || Array.isArray(value)) return;
      const data = value as Record<string, unknown>;
      if (message[0] === 'realtime_output_status' && this.outputEnabled) {
        const interval = validNumber(data.realtimeOutputStatusSendIntervalSec) && data.realtimeOutputStatusSendIntervalSec > 0
          ? data.realtimeOutputStatusSendIntervalSec : this.outputInterval;
        if (validNumber(data.inputRms) && validNumber(data.outputRms)) {
          this.levels = { input: data.inputRms, output: data.outputRms };
          this.status = 'connected';
          this.watchLevels(interval);
        }
        if (validNumber(data.outputBufferSize)) {
          this.pendingOutput = { samples: data.outputBufferSize, time: Date.now() };
          this.publishOutput();
          this.ensureRates(socket);
          clearTimeout(this.outputTimer);
          this.outputTimer = setTimeout(() => this.clearOutput(), this.timeout(interval));
        }
      } else if (message[0] === 'realtime_process_status' && this.processEnabled) {
        if (validNumber(data.inputBufferSize)) {
          this.pendingInput = { samples: data.inputBufferSize, time: Date.now() };
          this.publishInput();
          this.ensureRates(socket);
          clearTimeout(this.inputTimer);
          this.inputTimer = setTimeout(() => this.clearInput(), this.timeout(this.processInterval));
        }
        if (validNumber(data.elapsedTime)) {
          this.conversionTimeSeconds = data.elapsedTime;
          clearTimeout(this.conversionTimer);
          this.conversionTimer = setTimeout(() => this.clearConversionTime(), this.timeout(this.processInterval));
        }
      }
    });
  }

  private ensureRates(socket: Socket) {
    if (((!this.processEnabled || this.rates.input !== null) && (!this.outputEnabled || this.rates.output !== null))
      || this.rateController || Date.now() - this.lastRateAttempt < 2000) return;
    this.lastRateAttempt = Date.now();
    const controller = new AbortController();
    this.rateController = controller;
    const timeout = setTimeout(() => controller.abort(), 8000);
    void readAudioSampleRates(controller.signal).then(rates => {
      if (this.socket !== socket || controller.signal.aborted) return;
      this.rates = rates;
      this.publishInput();
      this.publishOutput();
    }).catch(() => {
      // Keep values unavailable; a later notification retries the read.
    }).finally(() => {
      clearTimeout(timeout);
      if (this.rateController === controller) this.rateController = null;
    });
  }

  private publishInput() {
    if (!this.pendingInput || !this.rates.input) return;
    const point = { time: this.pendingInput.time, seconds: this.pendingInput.samples / this.rates.input };
    this.inputBuffer = point.seconds;
    const now = Date.now();
    this.inputHistory = recentHistory([...this.inputHistory, point], now);
    this.outputHistory = recentHistory(this.outputHistory, now);
    this.pendingInput = null;
  }

  private publishOutput() {
    if (!this.pendingOutput || !this.rates.output) return;
    const point = { time: this.pendingOutput.time, seconds: this.pendingOutput.samples / this.rates.output };
    this.outputBuffer = point.seconds;
    const now = Date.now();
    this.inputHistory = recentHistory(this.inputHistory, now);
    this.outputHistory = recentHistory([...this.outputHistory, point], now);
    this.pendingOutput = null;
  }

  clearHistory() { this.inputHistory = []; this.outputHistory = []; }
  private timeout(interval: number) { return Math.max(2000, Math.min(interval * 3000, 300_000)); }
  private watchLevels(interval: number) {
    clearTimeout(this.levelTimer);
    this.levelTimer = setTimeout(() => { this.clearLevels(); this.status = 'unavailable'; }, this.timeout(interval));
  }
  private clearLevels() { clearTimeout(this.levelTimer); this.levels = null; }
  private clearInput() { clearTimeout(this.inputTimer); this.inputBuffer = null; this.pendingInput = null; this.inputHistory = []; }
  private clearConversionTime() { clearTimeout(this.conversionTimer); this.conversionTimeSeconds = null; }
  private clearOutput() { clearTimeout(this.outputTimer); this.outputBuffer = null; this.pendingOutput = null; this.outputHistory = []; }

  private clear(status: 'idle' | 'unavailable') {
    this.clearLevels();
    this.clearInput();
    this.clearConversionTime();
    this.clearOutput();
    this.rateController?.abort();
    this.rateController = null;
    this.rates = { input: null, output: null };
    this.lastRateAttempt = 0;
    this.status = status;
  }

  dispose() {
    const socket = this.socket;
    this.socket = null;
    socket?.removeAllListeners();
    socket?.disconnect();
    this.clear('idle');
  }
}
