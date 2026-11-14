import { test as base, expect } from '@playwright/test';

export { expect };
export type { Page, Route, WebSocketRoute } from '@playwright/test';

export const test = base.extend({
  context: async ({ context }, use) => {
    const unmocked: string[] = [];
    const backendPath = /^\/(?:api|model_dir|tmp|upload_dir|socket\.io)(?:\/|$)|^\/(?:input|output|monitor)\.wav$|^\/vcclient\.log$/;
    await context.route(url => backendPath.test(url.pathname), async route => {
      unmocked.push(`${route.request().method()} ${new URL(route.request().url()).pathname}`);
      await route.abort('blockedbyclient');
    });
    await context.routeWebSocket(/\/socket\.io\//, socket => socket.close());
    await use(context);
    expect(unmocked, 'Backend requests must be mocked').toEqual([]);
  },
});
