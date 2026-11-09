import { io, type Socket } from 'socket.io-client';

type Levels = { input: number; output: number };

export class AudioMeters {
  levels = $state<Levels | null>(null);
  status = $state<'idle' | 'connecting' | 'connected' | 'unavailable'>('idle');
  private socket: Socket | null = null;
  private staleTimer: ReturnType<typeof setTimeout> | undefined;
  private interval = 0.2;

  setEnabled(enabled: boolean, interval: number | null) {
    this.interval = interval !== null && Number.isFinite(interval) && interval > 0 ? interval : 0.2;
    if (!enabled) {
      this.dispose();
      return;
    }
    if (this.socket) return;
    this.status = 'connecting';
    const socket = io('/test', { transports: ['websocket'] });
    this.socket = socket;
    socket.on('connect', () => { this.status = 'connected'; this.watchForStale(this.interval); });
    socket.on('disconnect', () => this.clear('unavailable'));
    socket.on('connect_error', () => this.clear('unavailable'));
    socket.on('data', (message: unknown) => {
      if (this.socket !== socket || !Array.isArray(message) || message[0] !== 'realtime_output_status' || typeof message[1] !== 'string' || message[1].length > 4096) return;
      let value: unknown;
      try { value = JSON.parse(message[1]); } catch { return; }
      if (!value || typeof value !== 'object' || Array.isArray(value)) return;
      const data = value as Record<string, unknown>;
      if (typeof data.inputRms !== 'number' || !Number.isFinite(data.inputRms) || data.inputRms < 0
        || typeof data.outputRms !== 'number' || !Number.isFinite(data.outputRms) || data.outputRms < 0) return;
      this.levels = { input: data.inputRms, output: data.outputRms };
      this.status = 'connected';
      const sentInterval = typeof data.realtimeOutputStatusSendIntervalSec === 'number'
        && Number.isFinite(data.realtimeOutputStatusSendIntervalSec) && data.realtimeOutputStatusSendIntervalSec > 0
        ? data.realtimeOutputStatusSendIntervalSec : this.interval;
      this.watchForStale(sentInterval);
    });
  }

  private watchForStale(interval: number) {
    clearTimeout(this.staleTimer);
    this.staleTimer = setTimeout(() => this.clear('unavailable'), Math.max(2000, Math.min(interval * 3000, 300_000)));
  }

  private clear(status: 'idle' | 'unavailable') {
    clearTimeout(this.staleTimer);
    this.levels = null;
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
