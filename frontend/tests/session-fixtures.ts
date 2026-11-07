import { expect, type Page } from '@playwright/test';
import { configuration, slots, fulfillCatalog, mockCatalog } from './catalog-fixtures';

export async function mockSession(page: Page) {
  await mockCatalog(page);
  const state = {
    config: { ...configuration, pass_through: false, recording_started: false, future_setting: { keep: [1, 2] } } as Record<string, unknown>,
    models: structuredClone(slots) as Record<string, unknown>[],
    active: false, infoFail: false, putStatus: 200, startStatus: 200, rollback: false,
    gate: null as Promise<void> | null,
    modelGate: null as Promise<void> | null,
    modelStatus: 200, modelRollback: false, estimatorMismatch: false,
    writes: [] as Record<string, unknown>[], operations: [] as string[],
    modelWrites: [] as { id: number; data: Record<string, unknown> }[],
    inFlight: 0, maxInFlight: 0,
  };
  await page.route('**/api/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const slotMatch = path.match(/^\/api\/slot-manager\/slots\/(\d+)$/);
    if (slotMatch) {
      const id = Number(slotMatch[1]);
      const model = state.models.find(model => model.slot_index === id);
      if (request.method() === 'GET') return route.fulfill({ json: model });
      expect(request.method()).toBe('PUT');
      const payload = request.postDataJSON();
      state.modelWrites.push({ id, data: payload });
      state.maxInFlight = Math.max(state.maxInFlight, ++state.inFlight);
      if (state.modelGate) await state.modelGate;
      if (state.modelStatus === 200 && !state.modelRollback) {
        state.models = state.models.map(model => model.slot_index === id ? payload : model);
      }
      await route.fulfill({ status: state.modelStatus, json: state.modelStatus === 200 ? null : { detail: 'Test model save failure' } });
      --state.inFlight;
    } else if (path === '/api/slot-manager/slots') {
      expect(request.method()).toBe('GET');
      await route.fulfill({ json: state.models });
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
      const model = state.models.find(item => item.slot_index === state.config.current_slot_index);
      await route.fulfill({ json: { voice_changer_information: { recording_start_flag: state.config.recording_started, slot_index: state.config.current_slot_index, input_sample_rate: state.config.input_sample_rate, output_sample_rate: 48000, pipeline_info: { slot_index: state.config.current_slot_index, pitch_estimator_info: { pitch_estimator_type: state.estimatorMismatch ? 'incorrect' : model?.pitch_estimator } } } } });
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
