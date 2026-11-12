import { expect, test } from '@playwright/test';
import { mockSession } from './session-fixtures';

test('explains why model selection is disabled during conversion', async ({ page }) => {
  const state = await mockSession(page);
  state.active = true;
  await page.goto('/');
  const card = page.getByRole('group', { name: 'Test model A', exact: true });
  await expect(card.getByRole('button', { name: 'Test model A' })).toBeDisabled();
  await card.hover();
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip).toHaveText('モデルは音声の停止中に切り替えられます。');
  await expect(tooltip).toBeVisible();
  const box = await tooltip.boundingBox();
  const viewport = page.viewportSize();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(viewport!.width);
  await page.mouse.move(0, 0);
  await expect(tooltip).toHaveCount(0);
  await card.focus();
  await expect(tooltip).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(tooltip).toHaveCount(0);
});

test('does not show the stop explanation while conversion is stopped', async ({ page }) => {
  await mockSession(page);
  await page.goto('/');
  const card = page.getByRole('group', { name: 'Test model A', exact: true });
  await expect(card.getByRole('button', { name: 'Test model A' })).toBeEnabled();
  await card.hover();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
});
