import { describe, expect, it } from 'vitest';
import { parseRecognitionResponse } from './api';

const validResult = { states: [], transitions: [], warnings: [], processing_ms: 12 };

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
