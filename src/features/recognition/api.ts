import { apiUrl } from '../../config';
import type { RecognitionResult } from './types';

/** Turn a fetch/parse failure into a short Japanese message the reviewer can act on. */
export function describeRecognitionError(reason: unknown, timeoutMs: number): string {
  if (reason instanceof DOMException && reason.name === 'AbortError') {
    return `認識サーバーが${Math.round(timeoutMs / 1000)}秒以内に応答しませんでした。通信環境を確認して再試行してください。`;
  }
  if (reason instanceof TypeError) {
    return '認識サーバーに接続できませんでした。バックエンドが起動しているか、通信環境を確認してください。';
  }
  if (reason instanceof Error && reason.message) return reason.message;
  return '画像を読み取れませんでした。別の画像で試してください。';
}

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
  return {
    ...body,
    transitions: body.transitions.map((transition) => ({
      ...transition,
      direction_confirmed: typeof transition.direction_confirmed === 'boolean'
        ? transition.direction_confirmed
        : transition.confidence >= 0.7,
    })),
  };
}

/** One weak box to re-read at high accuracy. Geometry is in the uploaded-image space. */
export interface RefineTarget {
  id: string;
  kind: 'state' | 'transition';
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface RefineResult {
  items: { id: string; text: string; confidence: number }[];
  processing_ms: number;
  timed_out: boolean;
  attempted: number;
}

function isRefineResult(value: unknown): value is RefineResult {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<RefineResult>;
  return Array.isArray(candidate.items) && typeof candidate.processing_ms === 'number';
}

/**
 * Ask the backend to re-read only the given boxes with the slow, exhaustive
 * OCR pass. Never changes structure/connection/direction — the caller applies
 * the returned text to names/events itself.
 */
export async function refineRecognition(
  file: File,
  targets: RefineTarget[],
  signal: AbortSignal,
): Promise<RefineResult> {
  const form = new FormData();
  form.append('file', file);
  form.append('regions', JSON.stringify({ regions: targets }));
  const response = await fetch(apiUrl('/api/recognize/refine'), { method: 'POST', body: form, signal });
  const contentType = response.headers.get('content-type')?.toLowerCase() ?? '';
  if (!contentType.includes('application/json')) {
    await response.text();
    throw new Error(`高精度再読取APIがJSONを返しませんでした（HTTP ${response.status}）。`);
  }
  const body: unknown = await response.json();
  if (!response.ok) {
    const detail = typeof body === 'object' && body !== null && 'detail' in body
      ? (body as { detail?: unknown }).detail
      : undefined;
    throw new Error(typeof detail === 'string' ? detail : `高精度再読取でエラーが発生しました（HTTP ${response.status}）。`);
  }
  if (!isRefineResult(body)) {
    throw new Error('高精度再読取の応答形式が正しくありません。');
  }
  return body;
}
