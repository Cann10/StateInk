import { describe, expect, it } from 'vitest';
import { describeRecognitionError, parseRecognitionResponse } from './api';

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
