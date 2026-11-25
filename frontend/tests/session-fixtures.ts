import { expect, type Page, type Request } from '@playwright/test';
import {
  LOCKED_SESSION_FIELDS,
  configuration,
  inputDevices,
  outputDevices,
  slots,
  fulfillCatalog,
  mockCatalog,
} from './catalog-fixtures';

export async function readMultipart(request: Request): Promise<FormData> {
  return new Response(new Uint8Array(request.postDataBuffer() ?? []), {
    headers: { 'content-type': request.headers()['content-type'] ?? '' },
  }).formData();
}

export async function mockSession(page: Page) {
  await mockCatalog(page);

  let activeFlag = false;
  let startingFlag = false;
  let snapshotValue: Record<string, unknown> | null = null;
  let settingsRev = 1;
  let sessionRev = 1;
  const modelRevs: Record<string, number> = {};

  const state = {
    config: { ...configuration, future_setting: { keep: [1, 2] } } as Record<string, unknown>,
    models: structuredClone(slots) as Record<string, unknown>[],
    passThrough: false,
    recording: false,
    inputSampleRate: 48000,
    outputSampleRate: 48000,
    monitorSampleRate: null as number | null,
    lastError: null as { code: string; message: string; details: Record<string, unknown> } | null,
    get active() { return activeFlag; },
    set active(value: boolean) {
      activeFlag = value;
      startingFlag = false;
      snapshotValue = value ? {} : null;
      if (value) {
        state.lastError = null;
      } else {
        state.passThrough = false;
        state.recording = false;
      }
    },
    get starting() { return startingFlag; },
    set starting(value: boolean) {
      startingFlag = value;
      if (value) {
        activeFlag = false;
        snapshotValue ??= {};
      }
    },
    infoFail: false,
    putStatus: 200,
    startStatus: 200,
    startErrorCode: 'session_start_failed',
    startErrorMessage: 'Test start failure',
    rollback: false,
    enforceEtag: false,
    gate: null as Promise<void> | null,
    modelGate: null as Promise<void> | null,
    sessionGate: null as Promise<void> | null,
    asyncStartError: null as { code: string; message: string; details?: Record<string, unknown> } | null,
    modelStatus: 200,
    modelRollback: false,
    writes: [] as Record<string, unknown>[],
    sessionWrites: [] as Record<string, unknown>[],
    operations: [] as string[],
    modelWrites: [] as { id: string; data: Record<string, unknown> }[],
    inFlight: 0,
    maxInFlight: 0,
    buildSessionResponse() {
      const status = startingFlag ? 'starting' : activeFlag ? 'running' : 'stopped';
      const activeModelId = (snapshotValue?.model_id as string | undefined) ?? (state.config.model_id as string | undefined);
      const activeModel = state.models.find(item => item.id === activeModelId) ?? state.models[0];
      const snap = status === 'stopped' ? null : {
        ...state.config,
        model_id: activeModelId,
        pitch_shift: activeModel?.pitch_shift ?? 0,
        index_ratio: activeModel?.index_ratio ?? 0,
        chunk_sec: activeModel?.chunk_sec ?? 0.5,
        pitch_estimator: activeModel?.pitch_estimator ?? 'rmvpe',
        ...snapshotValue,
        pass_through: state.passThrough,
        recording: state.recording,
      };
      return {
        status,
        snapshot: snap,
        locked_fields: LOCKED_SESSION_FIELDS,
        input_sample_rate: status === 'running' ? state.inputSampleRate : null,
        output_sample_rate: status === 'running' ? state.outputSampleRate : null,
        monitor_sample_rate: status === 'running'
          ? (state.config.input_mode === 'server' && state.config.audio_monitor_device_index !== -1
            ? (state.monitorSampleRate ?? 48000)
            : null)
          : null,
        last_error: state.lastError,
      };
    },
  };

  const nextSettingsEtag = () => `"settings-${++settingsRev}"`;
  const currentSettingsEtag = () => `"settings-${settingsRev}"`;
  const nextSessionEtag = () => `"session-${++sessionRev}"`;
  const currentSessionEtag = () => `"session-${sessionRev}"`;
  const getModelEtag = (id: string) => `"model-${id}-${modelRevs[id] ?? 1}"`;
  const bumpModelEtag = (id: string) => {
    modelRevs[id] = (modelRevs[id] ?? 1) + 1;
    return getModelEtag(id);
  };

  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    const iconMatch = path.match(/^\/api\/models\/([^/]+)\/icon$/);
    if (iconMatch) {
      const id = decodeURIComponent(iconMatch[1]);
      if (request.method() === 'GET') {
        return route.fulfill({
          contentType: 'image/svg+xml',
          body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="steelblue"/></svg>',
        });
      }
      expect(request.method()).toBe('PUT');
      const model = state.models.find(item => item.id === id);
      const form = await readMultipart(request);
      const nextIcon = form.get('icon_file');
      const iconName = nextIcon instanceof File ? `icon_${state.modelWrites.length + 1}_${nextIcon.name}` : undefined;
      const writeData = { ...(iconName ? { icon_file: iconName } : {}) };
      state.modelWrites.push({ id, data: writeData });
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);
      if (state.modelGate) await state.modelGate;
      const updated = model
        ? { ...model, has_icon: true, icon_revision: Number(model.icon_revision ?? 0) + 1 }
        : undefined;
      if (state.modelStatus === 200 && !state.modelRollback && updated) {
        state.models = state.models.map(item => item.id === id ? updated : item);
      }
      const current = state.models.find(item => item.id === id) ?? model;
      const etag = state.modelStatus === 200 ? bumpModelEtag(id) : getModelEtag(id);
      await route.fulfill({
        status: state.modelStatus,
        headers: { ETag: etag },
        json: state.modelStatus === 200
          ? (state.modelRollback ? current : updated)
          : { code: 'internal_error', message: 'Test icon save failure' },
      });
      --state.inFlight;
      return;
    }

    const modelMatch = path.match(/^\/api\/models\/([^/]+)$/);
    if (modelMatch && modelMatch[1] !== 'order') {
      const id = decodeURIComponent(modelMatch[1]);
      const model = state.models.find(item => item.id === id);
      if (request.method() === 'GET') {
        if (!model) return route.fulfill({ status: 404, json: { code: 'model_not_found', message: 'Not found' } });
        return route.fulfill({ headers: { ETag: getModelEtag(id) }, json: model });
      }
      if (request.method() === 'DELETE') {
        if (!model) return route.fulfill({ status: 404, json: { code: 'model_not_found', message: 'Not found' } });
        if ((activeFlag || startingFlag) && snapshotValue?.model_id === id) {
          return route.fulfill({ status: 409, json: { code: 'model_in_use', message: 'Model is currently active.' } });
        }
        state.models = state.models.filter(item => item.id !== id);
        if (state.config.model_id === id) state.config.model_id = null;
        return route.fulfill({ status: 204 });
      }
      expect(request.method()).toBe('PUT');
      if (state.enforceEtag) {
        const ifMatch = request.headers()['if-match'];
        if (ifMatch && ifMatch !== getModelEtag(id)) {
          return route.fulfill({ status: 409, json: { code: 'etag_mismatch', message: 'ETag mismatch' } });
        }
      }
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.modelWrites.push({ id, data: payload });
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);
      if (state.modelGate) await state.modelGate;
      const updated = model ? { ...model, ...payload } : undefined;
      if (state.modelStatus === 200 && !state.modelRollback && model && updated) {
        Object.assign(model, updated);
      }
      const current = state.models.find(item => item.id === id) ?? model;
      const etag = state.modelStatus === 200 ? bumpModelEtag(id) : getModelEtag(id);
      await route.fulfill({
        status: state.modelStatus,
        headers: { ETag: etag },
        json: state.modelStatus === 200
          ? (state.modelRollback ? current : updated)
          : { code: 'internal_error', message: 'Test model save failure' },
      });
      --state.inFlight;
    } else if (path === '/api/models/order' && request.method() === 'PUT') {
      const payload = request.postDataJSON() as { model_ids: string[] };
      state.models = payload.model_ids.map(id => state.models.find(item => item.id === id)!);
      await route.fulfill({ json: { model_ids: payload.model_ids } });
    } else if (path === '/api/models') {
      expect(request.method()).toBe('GET');
      await route.fulfill({ json: state.models });
    } else if (path === '/api/devices/audio/reload' && request.method() === 'POST') {
      if (activeFlag || startingFlag) {
        return route.fulfill({ status: 409, json: { code: 'session_active', message: 'Session is active.' } });
      }
      await route.fulfill({ json: { inputs: inputDevices, outputs: outputDevices } });
    } else if (path === '/api/settings') {
      if (request.method() === 'GET') {
        return route.fulfill({ headers: { ETag: currentSettingsEtag() }, json: state.config });
      }
      expect(request.method()).toBe('PUT');
      if (state.enforceEtag) {
        const ifMatch = request.headers()['if-match'];
        if (ifMatch && ifMatch !== currentSettingsEtag()) {
          return route.fulfill({ status: 409, json: { code: 'etag_mismatch', message: 'Settings changed' } });
        }
      }
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.writes.push(payload);
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);
      if (state.gate) await state.gate;
      if (state.putStatus === 200 && !state.rollback) state.config = payload;
      const etag = state.putStatus === 200 ? nextSettingsEtag() : currentSettingsEtag();
      await route.fulfill({
        status: state.putStatus,
        headers: { ETag: etag },
        json: state.putStatus === 200
          ? state.config
          : { code: 'internal_error', message: 'Test save failure' },
      });
      --state.inFlight;
    } else if (path === '/api/session') {
      if (request.method() === 'GET') {
        if (state.infoFail) {
          return route.fulfill({ status: 503, json: { code: 'internal_error', message: 'Session status unavailable' } });
        }
        return route.fulfill({
          headers: { ETag: currentSessionEtag() },
          json: state.buildSessionResponse(),
        });
      }
      if (request.method() === 'DELETE') {
        if (startingFlag) {
          return route.fulfill({ status: 409, json: { code: 'session_starting', message: 'Session starting' } });
        }
        if (state.enforceEtag) {
          const ifMatch = request.headers()['if-match'];
          if (ifMatch && ifMatch !== currentSessionEtag()) {
            return route.fulfill({ status: 409, json: { code: 'etag_mismatch', message: 'ETag mismatch' } });
          }
        }
        state.operations.push('stop');
        activeFlag = false;
        startingFlag = false;
        snapshotValue = null;
        state.passThrough = false;
        state.recording = false;
        return route.fulfill({
          headers: { ETag: nextSessionEtag() },
          json: state.buildSessionResponse(),
        });
      }
      expect(request.method()).toBe('PUT');
      if (state.enforceEtag) {
        const ifMatch = request.headers()['if-match'];
        if (ifMatch && ifMatch !== currentSessionEtag()) {
          return route.fulfill({ status: 409, json: { code: 'etag_mismatch', message: 'ETag mismatch' } });
        }
      }
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.sessionWrites.push(payload);
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);

      if (startingFlag) {
        --state.inFlight;
        return route.fulfill({ status: 409, json: { code: 'session_starting', message: 'Session startup in progress' } });
      }

      if (!activeFlag) {
        state.operations.push('start');
        if (state.startStatus !== 200) {
          --state.inFlight;
          return route.fulfill({
            status: state.startStatus,
            json: { code: state.startErrorCode, message: state.startErrorMessage },
          });
        }
        if (state.gate) await state.gate;
        snapshotValue = { ...payload };
        state.passThrough = Boolean(payload.pass_through);
        state.recording = Boolean(payload.recording);
        state.lastError = null;

        if (state.sessionGate) {
          startingFlag = true;
          const gate = state.sessionGate;
          void gate.then(() => {
            startingFlag = false;
            if (state.asyncStartError) {
              activeFlag = false;
              snapshotValue = null;
              state.passThrough = false;
              state.recording = false;
              state.lastError = {
                code: state.asyncStartError.code,
                message: state.asyncStartError.message,
                details: state.asyncStartError.details ?? {},
              };
            } else {
              activeFlag = true;
              state.lastError = null;
            }
            nextSessionEtag();
          });
          --state.inFlight;
          return route.fulfill({
            status: 202,
            headers: { ETag: nextSessionEtag() },
            json: state.buildSessionResponse(),
          });
        }

        activeFlag = true;
        --state.inFlight;
        return route.fulfill({
          status: 202,
          headers: { ETag: nextSessionEtag() },
          json: state.buildSessionResponse(),
        });
      }

      // Live session update while running
      const activeSnap = (state.buildSessionResponse().snapshot ?? {}) as Record<string, unknown>;
      const conflicting = LOCKED_SESSION_FIELDS.filter(field => payload[field] !== activeSnap[field]);
      if (conflicting.length > 0) {
        --state.inFlight;
        return route.fulfill({
          status: 409,
          json: {
            code: 'session_rebuild_required',
            message: 'Session must be stopped before changing rebuild-required fields.',
            details: { conflicting_fields: conflicting },
          },
        });
      }
      if (state.gate) await state.gate;
      if (state.putStatus !== 200) {
        --state.inFlight;
        return route.fulfill({
          status: state.putStatus,
          json: { code: 'internal_error', message: 'Test session update failure' },
        });
      }
      if (!state.rollback) {
        snapshotValue = { ...payload };
        state.passThrough = Boolean(payload.pass_through);
        state.recording = Boolean(payload.recording);
      }
      --state.inFlight;
      return route.fulfill({
        status: 200,
        headers: { ETag: nextSessionEtag() },
        json: state.buildSessionResponse(),
      });
    } else {
      await fulfillCatalog(route);
    }
  });

  return state;
}
