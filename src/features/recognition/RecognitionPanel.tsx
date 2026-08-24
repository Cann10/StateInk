import { useState, type ChangeEvent } from 'react';
import { AlertTriangle, ImagePlus, LoaderCircle, Repeat2, Trash2, X } from 'lucide-react';
import type { StateMachine } from '../../core/types';
import { apiUrl } from '../../config';
import { recognitionToStateMachine } from './toStateMachine';
import type { RecognitionResult } from './types';

interface Props { onConfirm: (machine: StateMachine) => void; onClose: () => void }

export function RecognitionPanel({ onConfirm, onClose }: Props) {
  const [result, setResult] = useState<RecognitionResult>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const recognize = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setLoading(true); setError(undefined);
    const form = new FormData(); form.append('file', file);
    try {
      const response = await fetch(apiUrl('/api/recognize'), { method: 'POST', body: form });
      if (!response.ok) throw new Error((await response.json() as { detail?: string }).detail ?? '画像を読み取れませんでした');
      setResult(await response.json() as RecognitionResult);
    } catch (reason) { setError(reason instanceof Error ? reason.message : '画像を読み取れませんでした'); }
    finally { setLoading(false); }
  };
  const updateState = (id: string, changes: Partial<RecognitionResult['states'][number]>) => setResult((previous) => previous && ({ ...previous, states: previous.states.map((state) => state.id === id ? { ...state, ...changes } : state) }));
  const updateTransition = (id: string, changes: Partial<RecognitionResult['transitions'][number]>) => setResult((previous) => previous && ({ ...previous, transitions: previous.transitions.map((edge) => edge.id === id ? { ...edge, ...changes } : edge) }));
  const removeState = (id: string) => setResult((previous) => previous && ({ ...previous, states: previous.states.filter((state) => state.id !== id), transitions: previous.transitions.filter((edge) => edge.from !== id && edge.to !== id) }));

  return <section className="recognition card" aria-label="画像読み取りレビュー">
    <div className="card-title"><div><span>RECOGNITION / REVIEW</span><h2>写真から下書きを作る</h2></div><button className="reset" onClick={onClose}><X size={16}/>閉じる</button></div>
    {!result && <div className="upload"><ImagePlus size={34}/><strong>状態遷移図の画像を選択</strong><p>認識は自動完成ではなく、編集できる下書きを作ります。白紙に黒ペンで描いた図を選んでください。</p><label className="primary">画像を選択<input aria-label="状態遷移図の画像" type="file" accept="image/png,image/jpeg,image/webp" onChange={recognize}/></label>{loading && <div className="loading-state" role="status"><LoaderCircle className="spin"/>下書きを作成しています…</div>}{error && <div className="upload-error" role="alert"><strong>画像を読み取れませんでした</strong><p>{error}</p><p>バックエンドの起動と画像形式を確認してください。</p></div>}</div>}
    {result && <div className="review"><div className="review-notice"><AlertTriangle/><div><strong>読み取り結果を確認してください</strong><p>下書きです。名前、矢印の移動元・移動先・向き・イベントを確認してください（{result.processing_ms.toFixed(0)} ms）。</p></div></div>{result.warnings.map((warning) => <p className="recognition-warning" key={warning}>{warning}</p>)}
      <h3>状態</h3>{result.states.length === 0 && <div className="review-empty"><strong>状態を検出できませんでした</strong><p>別の画像を選ぶか、Editorで状態を追加してください。</p></div>}<div className="review-list">{result.states.map((state) => <div className={state.confidence < .7 ? 'review-row low-confidence' : 'review-row'} key={state.id}><label>名前<input value={state.name} onChange={(event) => updateState(state.id, { name: event.target.value })}/></label><label className="compact"><input type="radio" name="recognized-initial" checked={state.initial} onChange={() => setResult({ ...result, states: result.states.map((item) => ({ ...item, initial: item.id === state.id })) })}/>開始</label><label className="compact"><input type="checkbox" checked={state.final} onChange={(event) => updateState(state.id, { final: event.target.checked })}/>終了</label><span className="confidence">{state.confidence < .7 ? '⚠ 要確認 ' : '確信度 '}{Math.round(state.confidence * 100)}%</span><button aria-label={`${state.name}を削除`} className="danger-link" onClick={() => removeState(state.id)}><Trash2 size={15}/></button></div>)}</div>
      <h3>遷移（移動元 → 移動先）</h3>{result.transitions.length === 0 && <div className="review-empty"><strong>矢印を検出できませんでした</strong><p>確定後、Editorで遷移を追加できます。</p></div>}<div className="review-list">{result.transitions.map((edge) => <div className={edge.confidence < .7 ? 'review-row transition-review low-confidence' : 'review-row transition-review'} key={edge.id}><label>移動元<select value={edge.from} onChange={(event) => updateTransition(edge.id, { from: event.target.value })}>{result.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><span>→</span><label>移動先<select value={edge.to} onChange={(event) => updateTransition(edge.id, { to: event.target.value })}>{result.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><label>イベント<input value={edge.event} onChange={(event) => updateTransition(edge.id, { event: event.target.value })}/></label><button className="reverse-button" onClick={() => updateTransition(edge.id, { from: edge.to, to: edge.from })}><Repeat2 size={14}/>向きを反転</button><span className="confidence">{edge.confidence < .7 ? '⚠ 読み取りを確認 ' : '確信度 '}{Math.round(edge.confidence * 100)}%</span><button aria-label={`${edge.event}を削除`} className="danger-link" onClick={() => setResult({ ...result, transitions: result.transitions.filter((item) => item.id !== edge.id) })}><Trash2 size={15}/></button></div>)}</div>
      <div className="review-actions"><button className="reset" onClick={() => setResult(undefined)}>別の画像を選ぶ</button><button className="primary" disabled={result.states.length === 0 || !result.states.some((state) => state.initial)} onClick={() => onConfirm(recognitionToStateMachine(result))}>確認してEditorへ</button></div>
    </div>}
  </section>;
}
