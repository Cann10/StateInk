import { afterEach, describe, expect, it, vi } from 'vitest';
import { describeRecognitionError, parseRecognitionResponse, refineRecognition } from './api';

const validResult = { states: [], transitions: [], warnings: [], processing_ms: 12 };

describe('describeRecognitionError', () => {
  it('reports a timeout for an aborted request', () => {
    const message = describeRecognitionError(new DOMException('aborted', 'AbortError'), 25000);
    expect(message).toContain('25秒以内に応答しませんでした');
  });

  it('reports a connection failure for a network error', () => {
    expect(describeRecognitionError(new TypeError('Failed to fetch'), 25000)).toContain('接続できませんでした');
  });

  it('passes through a backend error message', () => {
    expect(describeRecognitionError(new Error('画像は10MB以下にしてください'), 25000)).toBe('画像は10MB以下にしてください');
  });

  it('falls back to a generic message for anything else', () => {
    expect(describeRecognitionError('boom', 25000)).toContain('画像を読み取れませんでした');
  });
});

describe('parseRecognitionResponse', () => {
  it('accepts a successful recognition JSON response', async () => {
    const response = new Response(JSON.stringify(validResult), { headers: { 'content-type': 'application/json' } });
    await expect(parseRecognitionResponse(response)).resolves.toEqual(validResult);
  });

  it('keeps low-confidence legacy directions unconfirmed', async () => {
    const body = { ...validResult, transitions: [{ id: 'edge', from: 'a', to: 'b', event: 'go', geometry: { x: 0, y: 0, width: 10, height: 0 }, confidence: .45 }] };
    const response = new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });
    await expect(parseRecognitionResponse(response)).resolves.toMatchObject({ transitions: [{ direction_confirmed: false }] });
  });

  it('shows a configuration error instead of parsing an HTML error page as JSON', async () => {
    const response = new Response('The page could not be found', { status: 404, headers: { 'content-type': 'text/plain' } });
    await expect(parseRecognitionResponse(response)).rejects.toThrow('VITE_API_BASE_URLとRenderのURL');
  });

  it('uses FastAPI detail for JSON error responses', async () => {
    const response = new Response(JSON.stringify({ detail: '画像は10MB以下にしてください' }), { status: 413, headers: { 'content-type': 'application/json' } });
    await expect(parseRecognitionResponse(response)).rejects.toThrow('画像は10MB以下にしてください');
  });

  it('rejects successful JSON from the wrong endpoint', async () => {
    const response = new Response(JSON.stringify({ status: 'ok' }), { headers: { 'content-type': 'application/json' } });
    await expect(parseRecognitionResponse(response)).rejects.toThrow('応答形式が正しくありません');
  });
});

describe('refineRecognition', () => {
  afterEach(() => { vi.unstubAllGlobals(); });
  const file = new File(['x'], 'd.png', { type: 'image/png' });
  const targets = [{ id: 's2', kind: 'state' as const, x: 1, y: 2, width: 3, height: 4 }];

  it('posts the targets and returns the parsed reading list', async () => {
    let sentBody: FormData | undefined;
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
      sentBody = init.body as FormData;
      return new Response(JSON.stringify({ items: [{ id: 's2', text: '入金済み', confidence: 0.8 }], processing_ms: 38000, timed_out: false, attempted: 1 }), { headers: { 'content-type': 'application/json' } });
    }));
    const result = await refineRecognition(file, targets, new AbortController().signal);
    expect(result.items).toEqual([{ id: 's2', text: '入金済み', confidence: 0.8 }]);
    expect(JSON.parse(String(sentBody?.get('regions')))).toEqual({ regions: targets });
  });

  it('surfaces the backend error detail', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ detail: '高精度の再読取中に問題が発生しました。' }), { status: 500, headers: { 'content-type': 'application/json' } })));
    await expect(refineRecognition(file, targets, new AbortController().signal)).rejects.toThrow('問題が発生しました');
  });

  it('rejects a non-JSON response', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('<html>502</html>', { status: 502, headers: { 'content-type': 'text/html' } })));
    await expect(refineRecognition(file, targets, new AbortController().signal)).rejects.toThrow('JSONを返しませんでした');
  });
});
