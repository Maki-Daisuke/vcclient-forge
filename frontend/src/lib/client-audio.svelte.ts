import { io, type Socket } from 'socket.io-client';
import captureUrl from './audio-capture.worklet.js?url';

type SinkAudioContext = AudioContext & { setSinkId?: (id: string) => Promise<void> };
type BrowserAudioOption = 'echoCancellation' | 'noiseSuppression' | 'autoGainControl';
const browserAudioStorageKey = 'vcclient-forge.browser-audio.v1';
const clientGainStorageKey = 'vcclient-forge.client-gain.v1';

function loadClientGains(): { inputGain: number; outputGain: number } {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(clientGainStorageKey) ?? 'null');
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const stored = value as Record<string, unknown>;
      const gain = (v: unknown) => typeof v === 'number' && Number.isFinite(v) && v >= 0 && v <= 10 ? v : 1;
      return { inputGain: gain(stored.inputGain), outputGain: gain(stored.outputGain) };
    }
  } catch { /* Use defaults if storage is unavailable or invalid. */ }
  return { inputGain: 1, outputGain: 1 };
}

function loadBrowserAudioOptions(): Record<BrowserAudioOption, boolean> {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(browserAudioStorageKey) ?? 'null');
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const stored = value as Record<string, unknown>;
      return { echoCancellation: stored.echoCancellation === true, noiseSuppression: stored.noiseSuppression === true, autoGainControl: stored.autoGainControl === true };
    }
  } catch { /* Storage may be unavailable or contain invalid data. */ }
  return { echoCancellation: false, noiseSuppression: false, autoGainControl: false };
}

export class ClientAudio {
  inputs = $state<MediaDeviceInfo[]>([]);
  outputs = $state<MediaDeviceInfo[]>([]);
  inputId = $state('');
  outputId = $state('');
  private options = $state(loadBrowserAudioOptions());
  private gains = $state(loadClientGains());
  private inputGainNode: GainNode | null = null;
  private outputGainNode: GainNode | null = null;
  private context: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private socket: Socket | null = null;
  private capture: AudioWorkletNode | null = null;
  private inputAnalyser: AnalyserNode | null = null;
  private outputAnalyser: AnalyserNode | null = null;
  private readonly inputSamples = new Float32Array(2048);
  private readonly outputSamples = new Float32Array(2048);
  private sources = new Set<AudioBufferSourceNode>();
  private nextPlayback = 0;
  private generation = 0;

  get canSelectOutput() { return typeof AudioContext !== 'undefined' && 'setSinkId' in AudioContext.prototype; }

  get echoCancellation() { return this.options.echoCancellation; }
  get noiseSuppression() { return this.options.noiseSuppression; }
  get autoGainControl() { return this.options.autoGainControl; }
  get inputGain() { return this.gains.inputGain; }
  get outputGain() { return this.gains.outputGain; }
  setGain(key: 'inputGain' | 'outputGain', value: number) {
    if (!Number.isFinite(value) || value < 0 || value > 10 || (key === 'inputGain' && this.autoGainControl)) return;
    this.gains = { ...this.gains, [key]: value };
    const node = key === 'inputGain' ? this.inputGainNode : this.outputGainNode;
    if (node) node.gain.value = value;
    try { localStorage.setItem(clientGainStorageKey, JSON.stringify(this.gains)); }
    catch { /* Keep the current page usable if browser storage is unavailable. */ }
  }
  supportsOption(option: BrowserAudioOption) {
    return navigator.mediaDevices?.getSupportedConstraints?.()[option] === true;
  }
  setOption(option: BrowserAudioOption, value: boolean) {
    if (value && !this.supportsOption(option)) return;
    this.options = { ...this.options, [option]: value };
    try { localStorage.setItem(browserAudioStorageKey, JSON.stringify(this.options)); }
    catch { /* Keep the current page usable if browser storage is unavailable. */ }
  }

  async refreshDevices() {
    if (!navigator.mediaDevices?.enumerateDevices) return;
    const devices = await navigator.mediaDevices.enumerateDevices();
    this.inputs = devices.filter(device => device.kind === 'audioinput' && device.deviceId);
    this.outputs = devices.filter(device => device.kind === 'audiooutput' && device.deviceId);
  }

  async requestDevices() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Audio capture is unavailable in this browser.');
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    try { await this.refreshDevices(); }
    finally { stream.getTracks().forEach(track => track.stop()); }
  }

  readMeters(): { input: number; output: number; outputBuffer: number } | null {
    const context = this.context;
    if (!context || context.state !== 'running' || !this.inputAnalyser || !this.outputAnalyser) return null;
    const rms = (analyser: AnalyserNode, samples: Float32Array<ArrayBuffer>) => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) sum += sample * sample;
      return Math.sqrt(sum / samples.length);
    };
    return {
      input: rms(this.inputAnalyser, this.inputSamples),
      output: rms(this.outputAnalyser, this.outputSamples),
      outputBuffer: Math.max(0, this.nextPlayback - context.currentTime),
    };
  }

  async start(inputRate: number, outputRate: number, onFailure: (error: Error) => void) {
    if (!navigator.mediaDevices?.getUserMedia || typeof AudioContext === 'undefined') throw new Error('Audio capture is unavailable in this browser.');
    if ((this.options.echoCancellation && !this.supportsOption('echoCancellation'))
      || (this.options.noiseSuppression && !this.supportsOption('noiseSuppression'))
      || (this.options.autoGainControl && !this.supportsOption('autoGainControl'))) {
      throw new Error('The browser does not support the selected audio processing.');
    }
    const generation = ++this.generation;
    const context = new AudioContext({ sampleRate: inputRate, latencyHint: 'interactive' });
    this.context = context;
    try {
      if (context.sampleRate !== inputRate) throw new Error('The browser does not support the required input sample rate.');
      if (this.outputId) {
        const setSinkId = (context as SinkAudioContext).setSinkId;
        if (!setSinkId) throw new Error('Selecting an output device is not supported by this browser.');
        await setSinkId.call(context, this.outputId);
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: {
        ...(this.inputId ? { deviceId: { exact: this.inputId } } : {}), channelCount: 1,
        echoCancellation: this.options.echoCancellation ? { exact: true } : false,
        noiseSuppression: this.options.noiseSuppression ? { exact: true } : false,
        autoGainControl: this.options.autoGainControl ? { exact: true } : false,
      } });
      if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); return; }
      this.stream = stream;
      const trackSettings = stream.getAudioTracks()[0]?.getSettings();
      if ((this.options.echoCancellation && trackSettings?.echoCancellation === false)
        || (this.options.noiseSuppression && trackSettings?.noiseSuppression === false)
        || (this.options.autoGainControl && trackSettings?.autoGainControl === false)) {
        throw new Error('The microphone could not enable the requested audio processing.');
      }
      await this.refreshDevices();
      await context.audioWorklet.addModule(captureUrl);
      await context.resume();
      if (generation !== this.generation) return;
      const inputAnalyser = context.createAnalyser();
      const outputAnalyser = context.createAnalyser();
      const inputGainNode = context.createGain();
      const outputGainNode = context.createGain();
      inputGainNode.gain.value = this.autoGainControl ? 1 : this.inputGain;
      outputGainNode.gain.value = this.outputGain;
      this.inputGainNode = inputGainNode;
      this.outputGainNode = outputGainNode;
      inputAnalyser.fftSize = this.inputSamples.length;
      outputAnalyser.fftSize = this.outputSamples.length;
      this.inputAnalyser = inputAnalyser;
      this.outputAnalyser = outputAnalyser;
      outputGainNode.connect(outputAnalyser);
      outputAnalyser.connect(context.destination);
      const socket = io('/test', { transports: ['websocket'], reconnection: false, autoConnect: false });
      this.socket = socket;
      await new Promise<void>((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('Audio connection timed out.')), 10000);
        socket.once('connect', () => { clearTimeout(timeout); resolve(); });
        socket.once('connect_error', error => { clearTimeout(timeout); reject(error); });
        socket.connect();
      });
      if (generation !== this.generation) return;
      socket.on('disconnect', () => { if (generation === this.generation) onFailure(new Error('Audio connection disconnected.')); });
      stream.getAudioTracks()[0]?.addEventListener('ended', () => { if (generation === this.generation) onFailure(new Error('Microphone disconnected.')); });
      socket.on('response', (message: unknown, audio: unknown) => {
        const data = Array.isArray(message) ? message[1] : audio;
        if (generation !== this.generation || !(data instanceof ArrayBuffer) || data.byteLength % 4) return;
        const samples = new Float32Array(data);
        if (!samples.length) return;
        if (this.nextPlayback - context.currentTime > 1) {
          for (const source of this.sources) source.stop();
          this.sources.clear();
          this.nextPlayback = 0;
        }
        const buffer = context.createBuffer(1, samples.length, outputRate);
        buffer.copyToChannel(samples, 0);
        const source = context.createBufferSource();
        source.buffer = buffer;
        source.connect(outputGainNode);
        source.onended = () => this.sources.delete(source);
        this.sources.add(source);
        this.nextPlayback = Math.max(this.nextPlayback, context.currentTime);
        source.start(this.nextPlayback);
        this.nextPlayback += buffer.duration;
      });
      const capture = new AudioWorkletNode(context, 'audio-capture');
      this.capture = capture;
      capture.port.onmessage = event => {
        if (generation === this.generation && socket.connected && event.data instanceof Float32Array) {
          socket.emit('request_message', [Date.now(), true, event.data.buffer]);
        }
      };
      context.createMediaStreamSource(stream).connect(inputGainNode);
      inputGainNode.connect(inputAnalyser);
      inputAnalyser.connect(capture);
      capture.connect(context.destination);
    } catch (error) {
      this.stop();
      throw error;
    }
  }

  stop() {
    ++this.generation;
    this.capture?.disconnect();
    this.capture = null;
    this.inputGainNode?.disconnect();
    this.outputGainNode?.disconnect();
    this.inputGainNode = null;
    this.outputGainNode = null;
    this.inputAnalyser?.disconnect();
    this.outputAnalyser?.disconnect();
    this.inputAnalyser = null;
    this.outputAnalyser = null;
    this.stream?.getTracks().forEach(track => track.stop());
    this.stream = null;
    this.socket?.disconnect();
    this.socket = null;
    for (const source of this.sources) source.stop();
    this.sources.clear();
    this.nextPlayback = 0;
    if (this.context) void this.context.close();
    this.context = null;
  }
}
