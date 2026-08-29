import { useEffect, useMemo, useRef, useState, type ChangeEvent, type KeyboardEvent } from 'react';
import { AlertTriangle, Check, ImagePlus, LoaderCircle, Repeat2, Sparkles, Trash2, X } from 'lucide-react';
import type { StateMachine } from '../../core/types';
import { apiUrl } from '../../config';
import { describeRecognitionError, parseRecognitionResponse, refineRecognition, type RefineTarget } from './api';
import { scrollIntoViewGently } from '../../a11y';
import { recognitionToStateMachine } from './toStateMachine';
import type { RecognitionResult } from './types';

interface Props { onConfirm: (machine: StateMachine) => void; onClose: () => void }
type ConfidenceTier = 'high' | 'medium' | 'low';
type ReviewOrder = 'priority' | 'detected';

const RECOGNITION_TIMEOUT_MS = 25000;
const confidenceTier = (confidence: number): ConfidenceTier => confidence >= .8 ? 'high' : confidence >= .6 ? 'medium' : 'low';
const confidenceLabel = { high: '高', medium: '中', low: '低' } satisfies Record<ConfidenceTier, string>;

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error('画像のプレビューを作成できませんでした'));
    reader.readAsDataURL(file);
  });
}

export function RecognitionPanel({ onConfirm, onClose }: Props) {
  const [result, setResult] = useState<RecognitionResult>();
  const [imageUrl, setImageUrl] = useState<string>();
  const [imageSize, setImageSize] = useState({ width: 1, height: 1 });
  const [activeCandidateId, setActiveCandidateId] = useState<string>();
  const [reviewOrder, setReviewOrder] = useState<ReviewOrder>('priority');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [lastFile, setLastFile] = useState<File>();
  const [refining, setRefining] = useState(false);
  const [refineNote, setRefineNote] = useState<string>();
  const headingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => { headingRef.current?.focus(); }, []);

  const runRecognition = async (file: File) => {
    setLastFile(file);
    setLoading(true); setError(undefined);
    const form = new FormData(); form.append('file', file);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), RECOGNITION_TIMEOUT_MS);
    try {
      const [nextResult, preview] = await Promise.all([
        fetch(apiUrl('/api/recognize'), { method: 'POST', body: form, signal: controller.signal }).then(parseRecognitionResponse),
        fileToDataUrl(file),
      ]);
      const maxX = Math.max(1, ...nextResult.states.map((state) => state.geometry.x + state.geometry.width));
      const maxY = Math.max(1, ...nextResult.states.map((state) => state.geometry.y + state.geometry.height));
      setImageSize({ width: maxX, height: maxY });
      setImageUrl(preview); setResult(nextResult); setActiveCandidateId(undefined); setReviewOrder('priority');
    } catch (reason) {
      setError(describeRecognitionError(reason, RECOGNITION_TIMEOUT_MS));
    } finally {
      clearTimeout(timeout); setLoading(false);
    }
  };

  const recognize = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) void runRecognition(file);
  };
  const updateState = (id: string, changes: Partial<RecognitionResult['states'][number]>) => setResult((previous) => previous && ({ ...previous, states: previous.states.map((state) => state.id === id ? { ...state, ...changes } : state) }));
  const updateTransition = (id: string, changes: Partial<RecognitionResult['transitions'][number]>) => setResult((previous) => previous && ({ ...previous, transitions: previous.transitions.map((edge) => edge.id === id ? { ...edge, ...changes } : edge) }));
  const removeState = (id: string) => setResult((previous) => previous && ({ ...previous, states: previous.states.filter((state) => state.id !== id), transitions: previous.transitions.filter((edge) => edge.from !== id && edge.to !== id) }));
  const focusCandidate = (id: string) => {
    setActiveCandidateId(id);
    scrollIntoViewGently(document.getElementById(`review-${id}`));
  };
  const activateWithKeyboard = (event: KeyboardEvent<SVGGElement>, id: string) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); focusCandidate(id); }
  };
  const resetReview = () => { setResult(undefined); setImageUrl(undefined); setActiveCandidateId(undefined); setRefineNote(undefined); };
  const unconfirmedCount = result?.transitions.filter((edge) => !edge.direction_confirmed).length ?? 0;
  const isEmptyResult = !!result && result.states.length === 0 && result.transitions.length === 0;
  const orderedStates = useMemo(() => {
    if (!result) return [];
    return reviewOrder === 'detected' ? result.states : [...result.states].sort((first, second) => first.confidence - second.confidence);
  }, [result, reviewOrder]);
  const orderedTransitions = useMemo(() => {
    if (!result) return [];
    return reviewOrder === 'detected' ? result.transitions : [...result.transitions].sort((first, second) => {
      if (first.direction_confirmed !== second.direction_confirmed) return first.direction_confirmed ? 1 : -1;
      return first.confidence - second.confidence;
    });
  }, [result, reviewOrder]);
  const reviewCandidates = useMemo(() => {
    if (!result) return [];
    return [
      ...result.transitions.filter((edge) => !edge.direction_confirmed || edge.confidence < .8).map((edge) => ({ id: edge.id, score: edge.confidence - (edge.direction_confirmed ? 0 : .35) })),
      ...result.states.filter((state) => state.confidence < .8).map((state) => ({ id: state.id, score: state.confidence })),
    ].sort((first, second) => first.score - second.score);
  }, [result]);
  const isPlaceholderName = (text: string) => /^state\s*\d+$/i.test(text.trim()) || text.trim() === '';
  const isPlaceholderEvent = (text: string) => /^event_?\s*\d+$/i.test(text.trim()) || text.trim() === '';
  const refineTargets = useMemo<RefineTarget[]>(() => {
    if (!result) return [];
    const weakStates = result.states
      .filter((state) => state.confidence < .8 || isPlaceholderName(state.name))
      .map((state) => ({ id: state.id, kind: 'state' as const, ...state.geometry }));
    const weakTransitions = result.transitions
      .filter((edge) => edge.confidence < .8 || isPlaceholderEvent(edge.event))
      .map((edge) => ({ id: edge.id, kind: 'transition' as const, ...edge.geometry }));
    return [...weakStates, ...weakTransitions];
  }, [result]);
  const runRefine = async () => {
    if (!lastFile || !refineTargets.length || refining) return;
    setRefining(true); setRefineNote(undefined);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 75000);
    try {
      const refined = await refineRecognition(lastFile, refineTargets, controller.signal);
      const readings = new Map(refined.items.filter((item) => item.text.trim()).map((item) => [item.id, item]));
      setResult((previous) => previous && ({
        ...previous,
        states: previous.states.map((state) => {
          const hit = readings.get(state.id);
          return hit ? { ...state, name: hit.text, confidence: Math.max(state.confidence, hit.confidence) } : state;
        }),
        transitions: previous.transitions.map((edge) => {
          const hit = readings.get(edge.id);
          return hit ? { ...edge, event: hit.text, confidence: Math.max(edge.confidence, hit.confidence) } : edge;
        }),
      }));
      const applied = readings.size;
      const seconds = Math.round(refined.processing_ms / 1000);
      setRefineNote(
        `高精度モードで ${refineTargets.length} 件中 ${applied} 件を反映しました（約 ${seconds} 秒）。`
        + (applied < refineTargets.length ? ' 読み取れなかった項目はそのままです。' : '')
        + (refined.timed_out ? ' 時間の都合で一部は未処理です。' : ''),
      );
    } catch (reason) {
      setRefineNote(
        reason instanceof DOMException && reason.name === 'AbortError'
          ? '高精度の再読取がタイムアウトしました。通信環境を確認して再試行してください。'
          : reason instanceof Error && reason.message
            ? reason.message
            : '高精度の再読取に失敗しました。時間をおいて再試行してください。',
      );
    } finally {
      clearTimeout(timeout); setRefining(false);
    }
  };
  const focusNextReview = () => {
    if (!reviewCandidates.length) return;
    const currentIndex = reviewCandidates.findIndex((candidate) => candidate.id === activeCandidateId);
    focusCandidate(reviewCandidates[(currentIndex + 1) % reviewCandidates.length].id);
  };

  return <section className="recognition card" aria-label="画像読み取りレビュー">
    <div className="card-title"><div><span>RECOGNITION</span><h2 ref={headingRef} tabIndex={-1}>写真から下書きを作る</h2><p className="card-hint">STEP 1〜2。読み取り結果は「下書き」です。ここで直してから Editor へ渡します。</p></div><button className="reset" onClick={onClose}><X size={16}/>閉じる</button></div>
    {!result && <div className="upload"><ImagePlus size={34}/><strong>状態遷移図の画像を選ぶ</strong><p>自動で完成させるのではなく、<b>編集できる下書き</b>を作ります。</p><ul className="upload-tips"><li>白い紙に濃い線で描いた図</li><li>丸・楕円・長方形の状態と、まっすぐな矢印</li><li>日本語・英語の状態名／イベント名</li></ul><label className="primary">画像を選ぶ<input aria-label="状態遷移図の画像" type="file" accept="image/png,image/jpeg,image/webp" onChange={recognize}/></label>{loading && <div className="loading-state" role="status" aria-live="polite"><LoaderCircle className="spin" aria-hidden="true"/>下書きを作成しています… （10〜20秒ほどかかることがあります）</div>}{error && <div className="upload-error" role="alert"><strong>画像を読み取れませんでした</strong><p>{error}</p><p>時間をおくか、別の画像で試してください。</p>{lastFile && <button type="button" className="primary" disabled={loading} onClick={() => void runRecognition(lastFile)}>同じ画像で再試行</button>}</div>}</div>}
    {result && <div className="review"><div className="review-notice"><AlertTriangle/><div><strong>読み取り結果を確認してください</strong><p>元画像と色付き候補を見比べ、名前・接続・向きを確認してください（{result.processing_ms.toFixed(0)} ms）。</p>{reviewCandidates.length > 0 && <p className="review-priority"><b>まず {reviewCandidates.length} 件の候補を確認してください。</b>赤色（低確信度）と「方向未確認」を先に直すのがおすすめです。下の「次の要確認」で順番に移動できます。</p>}</div></div>{result.warnings.map((warning) => <p className="recognition-warning" key={warning}><AlertTriangle size={14}/>{warning}</p>)}
      {isEmptyResult ? <div className="review-empty review-nothing" role="status"><strong>この画像からは図の要素を読み取れませんでした</strong><p>照明やコントラストを上げて撮り直すか、下の「別の画像を選ぶ」で選び直してください。閉じて Editor で一から作ることもできます。</p></div> : <>
      {refineTargets.length > 0 && lastFile && <div className="refine-panel">
        <div>
          <strong><Sparkles size={15} aria-hidden="true"/>高精度で再読取（{refineTargets.length}件）</strong>
          <p>OCRに失敗・確信度が低い State / Event だけを、時間をかけて読み直します。時間がかかる場合があります（30〜60秒ほど）。読めた文字だけ反映し、構造や向きは変更しません。</p>
        </div>
        <button type="button" className="primary" disabled={refining} onClick={() => void runRefine()}>
          {refining ? '再読取中…' : '高精度で再読取'}
        </button>
      </div>}
      {refining && <div className="loading-state" role="status" aria-live="polite"><LoaderCircle className="spin" aria-hidden="true"/>高精度で再読取しています… 30〜60秒ほどかかることがあります</div>}
      {refineNote && <p className="refine-note" role="status">{refineNote}</p>}
      <div className="recognition-overview">
        <div className="overlay-stage" data-testid="recognition-overlay">
          {imageUrl && <img src={imageUrl} alt="アップロードした状態遷移図" onLoad={({ currentTarget }) => { const { naturalWidth, naturalHeight } = currentTarget; setImageSize((previous) => ({ width: Math.max(previous.width, naturalWidth), height: Math.max(previous.height, naturalHeight) })); }}/>}
          <svg viewBox={`0 0 ${imageSize.width} ${imageSize.height}`} aria-label="認識候補オーバーレイ" role="img">
            <defs>{(['high', 'medium', 'low'] as const).map((tier) => <marker key={tier} id={`arrow-${tier}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" className={`overlay-fill confidence-${tier}`}/></marker>)}</defs>
            {result.transitions.map((edge) => {
              const source = result.states.find((state) => state.id === edge.from); const target = result.states.find((state) => state.id === edge.to);
              if (!source || !target) return null;
              const tier = confidenceTier(edge.confidence);
              const x1 = source.geometry.x + source.geometry.width / 2; const y1 = source.geometry.y + source.geometry.height / 2;
              const x2 = target.geometry.x + target.geometry.width / 2; const y2 = target.geometry.y + target.geometry.height / 2;
              return <g key={edge.id} role="button" tabIndex={0} aria-label={`遷移 ${edge.event}、確信度${confidenceLabel[tier]}`} onClick={() => focusCandidate(edge.id)} onKeyDown={(event) => activateWithKeyboard(event, edge.id)} className={activeCandidateId === edge.id ? 'overlay-active' : ''}><line x1={x1} y1={y1} x2={x2} y2={y2} className={`overlay-transition confidence-${tier}`} markerEnd={`url(#arrow-${tier})`}/><text x={(x1 + x2) / 2} y={(y1 + y2) / 2 - 8}>{edge.event}</text></g>;
            })}
            {result.states.map((state) => { const tier = confidenceTier(state.confidence); return <g key={state.id} role="button" tabIndex={0} aria-label={`状態 ${state.name}、確信度${confidenceLabel[tier]}`} onClick={() => focusCandidate(state.id)} onKeyDown={(event) => activateWithKeyboard(event, state.id)} className={activeCandidateId === state.id ? 'overlay-active' : ''}><rect x={state.geometry.x} y={state.geometry.y} width={state.geometry.width} height={state.geometry.height} rx="8" className={`overlay-state confidence-${tier}`}/><text x={state.geometry.x + state.geometry.width / 2} y={state.geometry.y + state.geometry.height / 2}>{state.name}</text></g>; })}
          </svg>
        </div>
        <div className="confidence-legend" aria-label="確信度の凡例"><span className="confidence-high">高 80%以上</span><span className="confidence-medium">中 60–79%</span><span className="confidence-low">低 60%未満</span></div>
      </div>
      <div className="review-toolbar" aria-label="確認順序"><div><strong>要確認 {reviewCandidates.length}件</strong>{unconfirmedCount > 0 && <span>うち方向未確認 {unconfirmedCount}件</span>}</div><div className="review-toolbar-actions"><button className={reviewOrder === 'priority' ? 'active' : ''} aria-pressed={reviewOrder === 'priority'} onClick={() => setReviewOrder('priority')}>要確認を先に</button><button className={reviewOrder === 'detected' ? 'active' : ''} aria-pressed={reviewOrder === 'detected'} onClick={() => setReviewOrder('detected')}>検出順</button><button className="primary" disabled={!reviewCandidates.length} onClick={focusNextReview}>次の要確認</button></div></div>
      <h3>状態</h3>{result.states.length === 0 && result.transitions.length > 0 && <div className="review-empty"><strong>状態を検出できませんでした</strong><p>別の画像を選ぶか、Editorで状態を追加してください。</p></div>}<div className="review-list">{orderedStates.map((state) => { const tier = confidenceTier(state.confidence); return <div id={`review-${state.id}`} data-candidate-id={state.id} className={`review-row confidence-${tier} ${activeCandidateId === state.id ? 'active-review' : ''}`} key={state.id}><label>名前<input value={state.name} onFocus={() => setActiveCandidateId(state.id)} onChange={(event) => updateState(state.id, { name: event.target.value })}/></label><label className="compact"><input type="radio" name="recognized-initial" checked={state.initial} onChange={() => setResult({ ...result, states: result.states.map((item) => ({ ...item, initial: item.id === state.id })) })}/>開始</label><label className="compact"><input type="checkbox" checked={state.final} onChange={(event) => updateState(state.id, { final: event.target.checked })}/>終了</label><span className={`confidence-badge confidence-${tier}`}>確信度 {confidenceLabel[tier]} {Math.round(state.confidence * 100)}%</span><button aria-label={`${state.name}を削除`} className="danger-link" onClick={() => removeState(state.id)}><Trash2 size={15}/></button></div>; })}</div>
      <h3>遷移（移動元 → 移動先）</h3>{result.transitions.length === 0 && result.states.length > 0 && <div className="review-empty"><strong>矢印を検出できませんでした</strong><p>確定後、Editorで遷移を追加できます。</p></div>}<div className="review-list">{orderedTransitions.map((edge) => { const tier = confidenceTier(edge.confidence); return <div id={`review-${edge.id}`} data-candidate-id={edge.id} className={`review-row transition-review confidence-${tier} ${activeCandidateId === edge.id ? 'active-review' : ''}`} key={edge.id}><label>移動元<select value={edge.from} onFocus={() => setActiveCandidateId(edge.id)} onChange={(event) => updateTransition(edge.id, { from: event.target.value, direction_confirmed: true })}>{result.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><span>→</span><label>移動先<select value={edge.to} onChange={(event) => updateTransition(edge.id, { to: event.target.value, direction_confirmed: true })}>{result.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><label>イベント<input value={edge.event} onChange={(event) => updateTransition(edge.id, { event: event.target.value })}/></label><button className="reverse-button" onClick={() => updateTransition(edge.id, { from: edge.to, to: edge.from, direction_confirmed: true })}><Repeat2 size={14}/>向きを反転</button>{!edge.direction_confirmed && <button className="confirm-direction" onClick={() => updateTransition(edge.id, { direction_confirmed: true })}><Check size={14}/>この向きで確認</button>}<span className={`confidence-badge confidence-${tier}`}>{edge.direction_confirmed ? `確信度 ${confidenceLabel[tier]}` : '方向未確認'} {Math.round(edge.confidence * 100)}%</span><button aria-label={`${edge.event}を削除`} className="danger-link" onClick={() => setResult({ ...result, transitions: result.transitions.filter((item) => item.id !== edge.id) })}><Trash2 size={15}/></button></div>; })}</div>
      {unconfirmedCount > 0 && <p className="unconfirmed-directions" role="alert">方向未確認の遷移が{unconfirmedCount}件あります。向きを確認すると Editor へ進めます。</p>}
      <p className="confirm-hint">内容がよければ <b>「確認して Editor へ」</b>（Confirm）で確定します。あとから Editor でも直せます。</p>
      </>}
      <div className="review-actions"><button className="reset" onClick={resetReview}>別の画像を選ぶ</button>{!isEmptyResult && <button className="primary" disabled={result.states.length === 0 || !result.states.some((state) => state.initial) || unconfirmedCount > 0} onClick={() => onConfirm(recognitionToStateMachine(result))}>確認してEditorへ</button>}</div>
    </div>}
  </section>;
}
