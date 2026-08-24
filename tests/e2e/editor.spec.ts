import { expect, test } from '@playwright/test';

test('broken vending machine is repaired live and can execute refund', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => { if (message.type() === 'error') browserErrors.push(message.text()); });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('描いた設計を、')).toBeVisible();
  await page.screenshot({ path: 'artifacts/stateink-home.png', fullPage: true });
  await page.getByRole('button', { name: /サンプルを試す/ }).click();
  await expect(page.getByText('「売り切れ」に入ると、どこにも移動できません')).toBeVisible();
  await expect(page.getByText('coin → select → sold_out', { exact: true })).toBeVisible();

  await page.getByLabel('遷移の移動元').selectOption('sold-out');
  await page.getByLabel('遷移の移動先').selectOption('idle');
  await page.getByLabel('遷移のイベント').fill('refund');
  await page.getByRole('button', { name: '追加', exact: true }).click();
  await expect(page.getByText('問題は見つかりませんでした')).toBeVisible();

  for (const event of ['coin', 'select', 'sold_out', 'refund']) await page.getByRole('button', { name: new RegExp(`^${event}`) }).click();
  await expect(page.locator('.current strong')).toHaveText('待機');
  await page.screenshot({ path: 'artifacts/stateink-editor.png', fullPage: true });
  expect(browserErrors).toEqual([]);
});

test('image recognition can be reviewed, corrected, confirmed, and simulated', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => { if (message.type() === 'error') browserErrors.push(message.text()); });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.route('**/api/recognize', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ processing_ms: 24, warnings: ['読み取りを確認してください。'], states: [{ id: 'state-1', name: 'State 1', geometry: { x: 100, y: 100, width: 120, height: 70 }, confidence: .82, initial: true, final: false }, { id: 'state-2', name: 'State 2', geometry: { x: 400, y: 100, width: 120, height: 70 }, confidence: .65, initial: false, final: false }], transitions: [{ id: 'transition-1', from: 'state-1', to: 'state-2', event: 'event_1', geometry: { x: 220, y: 130, width: 180, height: 0 }, confidence: .62 }] }) }));
  await page.goto('/');
  await page.getByRole('button', { name: /紙から読み取る/ }).click();
  await page.getByLabel('状態遷移図の画像').setInputFiles({ name: 'diagram.png', mimeType: 'image/png', buffer: Buffer.from('fixture') });
  await expect(page.getByText('読み取り結果を確認してください', { exact: true })).toBeVisible();
  await page.screenshot({ path: 'artifacts/stateink-recognition-review.png', fullPage: true });
  const names = page.locator('.review-list').first().locator('input[type="text"], input:not([type])');
  await names.nth(0).fill('待機'); await names.nth(1).fill('実行中');
  await page.locator('.review-list').nth(1).locator('input').fill('start');
  await page.getByRole('button', { name: '向きを反転' }).click();
  await page.getByRole('button', { name: '向きを反転' }).click();
  await page.getByRole('button', { name: '確認してEditorへ' }).click();
  await page.getByRole('button', { name: /^start/ }).click();
  await expect(page.locator('.current strong')).toHaveText('実行中');
  expect(browserErrors).toEqual([]);
});
