import { expect, test } from '@playwright/test';

test('an analyzer issue can be replayed and its reviewed fix can be applied', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => { if (message.type() === 'error') browserErrors.push(message.text()); });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.goto('/');
  await expect(page.getByText('描いた設計を、')).toBeVisible();
  await page.screenshot({ path: 'artifacts/stateink-home.png', fullPage: true });
  await page.getByRole('button', { name: /サンプルを試す/ }).click();
  await expect(page.getByText('「売り切れ」に入ると、どこにも移動できません')).toBeVisible();
  await expect(page.getByText('coin → select → sold_out', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '問題を再現' }).click();
  await expect(page.locator('.current strong')).toHaveText('売り切れ');
  await expect(page.getByText('最短操作列を再現し、経路を図で強調しています。')).toBeVisible();
  await expect(page.locator('.react-flow__edge.replayed-edge')).toHaveCount(3);
  await expect(page.getByText('「待機」へ戻る遷移を追加')).toBeVisible();
  await page.getByRole('button', { name: 'この候補を追加' }).click();
  await expect(page.getByText('問題は見つかりませんでした')).toBeVisible();

  for (const event of ['coin', 'select', 'sold_out', 'return']) await page.getByRole('button', { name: new RegExp(`^${event}`) }).click();
  await expect(page.locator('.current strong')).toHaveText('待機');
  await page.screenshot({ path: 'artifacts/stateink-editor.png', fullPage: true });
  expect(browserErrors).toEqual([]);
});

test('image recognition can be reviewed, corrected, confirmed, and simulated', async ({ page }) => {
  const browserErrors: string[] = [];
  page.on('console', (message) => { if (message.type() === 'error') browserErrors.push(message.text()); });
  page.on('pageerror', (error) => browserErrors.push(error.message));
  await page.route('**/api/recognize', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ processing_ms: 24, warnings: [], states: [{ id: 'state-1', name: '待機', geometry: { x: 100, y: 100, width: 120, height: 70 }, confidence: .86, initial: true, final: false }, { id: 'state-2', name: '入金済み', geometry: { x: 400, y: 100, width: 120, height: 70 }, confidence: .64, initial: false, final: false }], transitions: [{ id: 'transition-1', from: 'state-1', to: 'state-2', event: 'coin', geometry: { x: 220, y: 130, width: 180, height: 0 }, confidence: .52, direction_confirmed: false }] }) }));
  await page.goto('/');
  await page.getByRole('button', { name: /紙から読み取る/ }).click();
  await page.getByLabel('状態遷移図の画像').setInputFiles({ name: 'diagram.png', mimeType: 'image/png', buffer: Buffer.from('fixture') });
  await expect(page.getByText('読み取り結果を確認してください', { exact: true })).toBeVisible();
  await expect(page.getByTestId('recognition-overlay')).toBeVisible();
  await expect(page.getByLabel('確信度の凡例')).toContainText('高 80%以上');
  await expect(page.getByRole('button', { name: '要確認を先に' })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByText('要確認 2件')).toBeVisible();
  await expect(page.getByText('方向未確認 52%')).toBeVisible();
  await expect(page.getByRole('button', { name: '確認してEditorへ' })).toBeDisabled();
  await page.screenshot({ path: 'artifacts/stateink-recognition-review.png', fullPage: true });
  const names = page.locator('.review-list').first().locator('input[type="text"], input:not([type])');
  await expect(names.nth(0)).toHaveValue('入金済み');
  await expect(names.nth(1)).toHaveValue('待機');
  await page.getByRole('button', { name: '次の要確認' }).click();
  await expect(page.locator('[data-candidate-id="transition-1"]')).toHaveClass(/active-review/);
  await expect(page.locator('.review-list').nth(1).locator('input')).toHaveValue('coin');
  await names.nth(0).fill('商品選択');
  await page.locator('.review-list').nth(1).locator('input').fill('select');
  await page.getByRole('button', { name: '向きを反転' }).click();
  await page.getByRole('button', { name: '向きを反転' }).click();
  await expect(page.getByRole('button', { name: '確認してEditorへ' })).toBeEnabled();
  await page.getByRole('button', { name: '確認してEditorへ' }).click();
  await page.getByRole('button', { name: /^select/ }).click();
  await expect(page.locator('.current strong')).toHaveText('商品選択');
  expect(browserErrors).toEqual([]);
});
