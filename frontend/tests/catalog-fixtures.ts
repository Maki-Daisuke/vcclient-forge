import { expect, type Page, type Route } from '@playwright/test';

// Deliberately sparse and unsorted. UI selection must use IDs, not array positions.
export const slots = [
  {
    slot_index: 7, voice_changer_type: 'RVC', name: 'Test model B',
    description: 'Description of the selected model', icon_file: 'C:\\old\\portrait #1.png',
    is_onnx: false, is_f0: false, version: 'v1', embedder: 'hubert_base_l12',
  },
  { slot_index: 0, voice_changer_type: null },
  {
    slot_index: 2, voice_changer_type: 'RVC', name: 'Test model A',
    description: '', icon_file: null,
    is_onnx: true, is_f0: true, version: 'v2', embedder: 'contentvec',
  },
];

export async function fulfillCatalog(route: Route, data: unknown = slots, currentId = 7) {
  expect(route.request().method()).toBe('GET');
  const path = new URL(route.request().url()).pathname;
  if (path === '/api/slot-manager/slots') {
    await route.fulfill({ json: data });
  } else if (path === '/api/configuration-manager/configuration') {
    await route.fulfill({ json: { current_slot_index: currentId } });
  } else {
    throw new Error(`Unexpected API request: ${path}`);
  }
}

export async function mockCatalog(page: Page) {
  await page.route('**/api/**', route => fulfillCatalog(route));
  await page.route('**/model_dir/**', route => route.fulfill({
    contentType: 'image/svg+xml',
    body: '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><rect width="32" height="32" fill="steelblue"/></svg>',
  }));
}
