import { expect, type Page, type Request } from '@playwright/test';
import { configuration, inputDevices, outputDevices, slots, fulfillCatalog, mockCatalog } from './catalog-fixtures';

export async function readMultipart(request: Request): Promise<FormData> {
  return new Response(new Uint8Array(request.postDataBuffer() ?? []), {
    headers: { 'content-type': request.headers()['content-type'] ?? '' },
  }).formData();
}

export async function mockSession(page: Page) {
  await mockCatalog(page);
  const state = {
    config: { ...configuration, pass_through: false, recording_started: false, future_setting: { keep: [1, 2] } } as Record<string, unknown>,
    models: structuredClone(slots) as Record<string, unknown>[],
    active: false, infoFail: false, putStatus: 200, startStatus: 200, rollback: false,
    gate: null as Promise<void> | null,
    modelGate: null as Promise<void> | null,
    modelStatus: 200, modelRollback: false, estimatorMismatch: false, gpuMismatch: false,
    writes: [] as Record<string, unknown>[], operations: [] as string[],
    modelWrites: [] as { id: string; data: Record<string, unknown> }[],
    inFlight: 0, maxInFlight: 0,
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
      await route.fulfill({
        status: state.modelStatus,
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
        return route.fulfill({ json: model });
      }
      if (request.method() === 'DELETE') {
        if (!model) return route.fulfill({ status: 404, json: { code: 'model_not_found', message: 'Not found' } });
        state.models = state.models.filter(item => item.id !== id);
        if (state.config.model_id === id) state.config.model_id = null;
        return route.fulfill({ status: 204 });
      }
      expect(request.method()).toBe('PUT');
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.modelWrites.push({ id, data: payload });
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);
      if (state.modelGate) await state.modelGate;
      const updated = model ? { ...model, ...payload } : undefined;
      if (state.modelStatus === 200 && !state.modelRollback && model && updated) {
        Object.assign(model, updated);
      }
      const current = state.models.find(item => item.id === id) ?? model;
      await route.fulfill({
        status: state.modelStatus,
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
      await route.fulfill({ json: { inputs: inputDevices, outputs: outputDevices } });
    } else if (path.endsWith('/configuration')) {
      if (request.method() === 'GET') return route.fulfill({ json: state.config });
      expect(request.method()).toBe('PUT');
      const payload = request.postDataJSON();
      state.writes.push(payload);
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);
      if (state.gate) await state.gate;
      if (state.putStatus === 200 && !state.rollback) state.config = payload;
      await route.fulfill({ status: state.putStatus, json: state.putStatus === 200 ? null : { detail: 'Test save failure' } });
      --state.inFlight;
    } else if (path === '/api/voice-changer-manager/information') {
      const model = state.models.find(item => item.id === state.config.model_id);
      await route.fulfill({
        json: {
          voice_changer_information: {
            recording_start_flag: state.config.recording_started,
            model_id: state.config.model_id,
            gpu_device_index: state.gpuMismatch ? -1 : state.config.gpu_device_id_int,
            input_sample_rate: state.config.input_sample_rate,
            output_sample_rate: 48000,
            pipeline_info: {
              model_id: state.config.model_id,
              pitch_estimator_info: { pitch_estimator_type: state.estimatorMismatch ? 'incorrect' : model?.pitch_estimator },
            },
          },
        },
      });
    } else if (path.endsWith('/information')) {
      expect(request.method()).toBe('GET');
      await route.fulfill({ status: state.infoFail ? 503 : 200, json: { local_voice_changer_interface_active: state.active } });
    } else if (path.includes('/operation/')) {
      expect(request.method()).toBe('POST');
      const operation = path.split('/').at(-1)!;
      state.operations.push(operation);
      const status = operation === 'start' ? state.startStatus : 200;
      if (status === 200) state.active = operation === 'start';
      await route.fulfill({ status, json: status === 200 ? null : { detail: 'Test start failure' } });
    } else await fulfillCatalog(route);
  });
  return state;
}
