import type { RecognitionResult } from './types';

function isRecognitionResult(value: unknown): value is RecognitionResult {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<RecognitionResult>;
  return Array.isArray(candidate.states)
    && Array.isArray(candidate.transitions)
    && Array.isArray(candidate.warnings)
    && typeof candidate.processing_ms === 'number';
}

export async function parseRecognitionResponse(response: Response): Promise<RecognitionResult> {
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
  if (!contentType.includes('application/json')) {
    await response.text();
    throw new Error(`認識APIがJSONを返しませんでした（HTTP ${response.status}）。VITE_API_BASE_URLとRenderのURLを確認してください。`);
  }

  const body: unknown = await response.json();
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? (body as { detail?: unknown }).detail
      : undefined;
    throw new Error(typeof detail === 'string' ? detail : `認識APIでエラーが発生しました（HTTP ${response.status}）。`);
  }
  if (!isRecognitionResult(body)) {
    throw new Error('認識APIの応答形式が正しくありません。BackendとFrontendのバージョンを確認してください。');
  }
  return body;
}
