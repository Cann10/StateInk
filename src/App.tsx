import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node, type NodeMouseHandler, type EdgeMouseHandler } from '@xyflow/react';
import { AlertTriangle, CheckCircle2, CirclePlus, Download, FileJson, FilePenLine, Home, ImagePlus, Play, RotateCcw, Sparkles, Trash2, Upload } from 'lucide-react';
import { analyze } from './core/analyzer';
import { addState, addTransition, removeState, removeTransition, setInitialState, updateState, updateTransitionEvent } from './core/editor';
import { availableEvents, createSimulation, replayEvents, reset, transition, type ReplayResult, type Simulation } from './core/simulator';
import type { AnalysisIssue, StateMachine } from './core/types';
import { isValidStateMachine } from './core/validate';
import { brokenVendingMachine } from './samples/brokenVendingMachine';
import { vendingMachine } from './samples/vendingMachine';
import { RecognitionPanel } from './features/recognition/RecognitionPanel';
import { downloadPng, downloadText, machineToJson, machineToSvg } from './features/export/exportMachine';
import { loadSavedWorkspace, saveWorkspace } from './features/workspace/storage';

const samples = { valid: vendingMachine, broken: brokenVendingMachine } as const;
const initialErrorText = { 'missing-initial': '開始状態がないため実行できません。', 'multiple-initial': '開始状態が複数あるため実行できません。' } as const;

function visibleIssues(issues: AnalysisIssue[]): AnalysisIssue[] {
  const initialIssues = issues.filter((item) => item.type === 'missing-initial' || item.type === 'multiple-initial');
  if (initialIssues.length > 0) return initialIssues;
  const deadEndStates = new Set(issues.filter((item) => item.type === 'dead-end').flatMap((item) => item.stateIds));
  return issues.filter((item) => item.type !== 'non-terminating-cycle' || !item.stateIds.every((id) => deadEndStates.has(id)));
}

export function App() {
  const [savedWorkspace] = useState(loadSavedWorkspace);
  const [screen, setScreen] = useState<'home' | 'workspace'>(() => savedWorkspace?.screen ?? 'home');
  const [sampleKey, setSampleKey] = useState<keyof typeof samples>(() => savedWorkspace?.sampleKey ?? 'valid');
  const [machine, setMachine] = useState<StateMachine>(() => savedWorkspace?.machine ?? vendingMachine);
  const [simulation, setSimulation] = useState<Simulation>(() => createSimulation(savedWorkspace?.machine ?? vendingMachine));
  const [selectedStateId, setSelectedStateId] = useState<string>();
  const [selectedTransitionId, setSelectedTransitionId] = useState<string>();
  const [transitionDraft, setTransitionDraft] = useState({ from: 'idle', to: 'idle', event: '' });
  const [showRecognition, setShowRecognition] = useState(false);
  const [fileError, setFileError] = useState<string>();
  const [replayedPath, setReplayedPath] = useState<ReplayResult>();
  const simulatorRef = useRef<HTMLElement>(null);

  const replayCounterexample = (events: string[]) => {
    const replay = replayEvents(machine, events);
    setSimulation(replay.simulation);
    setReplayedPath(replay);
    simulatorRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  };
  const issues = useMemo(() => analyze(machine), [machine]);
  const shownIssues = visibleIssues(issues);
  const problemStates = new Set(shownIssues.flatMap((item) => item.stateIds));
  const current = machine.states.find((state) => state.id === simulation.currentStateId);
  const selectedState = machine.states.find((state) => state.id === selectedStateId);
  const selectedTransition = machine.transitions.find((edge) => edge.id === selectedTransitionId);

  useEffect(() => {
    saveWorkspace({ machine, sampleKey, screen });
  }, [machine, sampleKey, screen]);

  const applyEdit = (edit: (previous: StateMachine) => StateMachine) => {
    setReplayedPath(undefined);
    setMachine((previous) => { const next = edit(previous); setSimulation(createSimulation(next)); return next; });
  };
  const chooseSample = (key: keyof typeof samples) => {
    const next = samples[key]; setSampleKey(key); setMachine(next); setSimulation(createSimulation(next)); setReplayedPath(undefined);
    setSelectedStateId(undefined); setSelectedTransitionId(undefined); setTransitionDraft({ from: next.states[0]?.id ?? '', to: next.states[0]?.id ?? '', event: '' });
  };
  const replayedStateIds = new Set(replayedPath?.stateIds ?? []);
  const replayedTransitionIds = new Set(replayedPath?.transitionIds ?? []);
  const nodes: Node[] = machine.states.map((state) => ({ id: state.id, position: state.position, data: { label: <div className="node-label"><span>{state.initial ? '▶ ' : ''}{state.name}{state.final ? ' ◎' : ''}</span>{state.initial && <small>開始</small>}{state.final && <small>正常終了</small>}{problemStates.has(state.id) && <small className="problem-label">⚠ 要確認</small>}</div> }, className: `${state.id === current?.id ? 'current-node' : ''} ${problemStates.has(state.id) ? 'problem-node' : ''} ${state.id === selectedStateId ? 'selected-node' : ''} ${replayedStateIds.has(state.id) ? 'replayed-node' : ''}` }));
  const edges: Edge[] = machine.transitions.map((edge) => ({ id: edge.id, source: edge.from, target: edge.to, label: edge.event, animated: edge.id === simulation.lastTransitionId || replayedTransitionIds.has(edge.id), className: `${edge.id === simulation.lastTransitionId ? 'active-edge' : ''} ${edge.id === selectedTransitionId ? 'selected-edge' : ''} ${replayedTransitionIds.has(edge.id) ? 'replayed-edge' : ''}`, markerEnd: { type: MarkerType.ArrowClosed } }));
  const selectNode: NodeMouseHandler = (_, node) => { setSelectedStateId(node.id); setSelectedTransitionId(undefined); };
  const selectEdge: EdgeMouseHandler = (_, edge) => { setSelectedTransitionId(edge.id); setSelectedStateId(undefined); };

  const openWorkspace = (next: StateMachine, key: keyof typeof samples = 'valid') => {
    setSampleKey(key); setMachine(next); setSimulation(createSimulation(next)); setReplayedPath(undefined); setScreen('workspace');
    setSelectedStateId(undefined); setSelectedTransitionId(undefined);
    setTransitionDraft({ from: next.states[0]?.id ?? '', to: next.states[0]?.id ?? '', event: '' });
  };

  const importJson = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    try {
      const candidate: unknown = JSON.parse(await file.text());
      if (!isValidStateMachine(candidate)) throw new Error();
      openWorkspace(candidate);
      setFileError(undefined);
    } catch {
      setFileError('StateInkのJSONファイルを読み込めませんでした。');
    }
  };

  if (screen === 'home') return <main className="home-screen">
    <div className="home-brand"><span className="brand-mark">S</span><strong>StateInk</strong><span className="home-tag">STATE MACHINE REVIEW</span></div>
    <div className="home-layout"><section className="hero"><p className="eyebrow">VERIFY BEFORE YOU BUILD</p><h1>描いた設計を、<br/>動かして確かめる。</h1><p>紙の状態遷移図を、実行・検証できる設計図へ。</p><div className="hero-proof"><span>編集できる</span><span>その場で実行</span><span>問題操作を表示</span></div></section><div className="home-preview" aria-hidden="true"><div className="preview-state start">待機</div><span className="preview-arrow">coin →</span><div className="preview-state">選択中</div><span className="preview-arrow">select →</span><div className="preview-state warning">売り切れ ⚠</div><div className="preview-finding">refund がないため待機へ戻れません</div></div></div>
    <section className="home-start"><div><p className="eyebrow">START ・ はじめる</p><h2>3つの入り口から選べます</h2><p className="home-start-hint">初めての方は <b>「サンプルを試す」</b> がおすすめです。</p></div><nav className="start-options" aria-label="はじめる方法">
        <button className="recommended" onClick={() => openWorkspace(brokenVendingMachine, 'broken')}><Sparkles/><span><strong>サンプルを試す</strong><small>まず動かして雰囲気をつかむ</small></span><b>→</b></button>
        <button onClick={() => { setScreen('workspace'); setShowRecognition(true); }}><ImagePlus/><span><strong>紙から読み取る</strong><small>手書き・印刷した図の写真から始める</small></span><b>→</b></button>
        <button onClick={() => openWorkspace({ states: [], transitions: [] })}><FilePenLine/><span><strong>自分で図を作る</strong><small>白紙から自分で作図する</small></span><b>→</b></button>
      </nav></section>
    <section className="home-steps"><p className="eyebrow">HOW IT WORKS ・ 使い方は4ステップ</p><div><article><b>1</b><strong>読み込む</strong><span>写真・新規・サンプル</span></article><article><b>2</b><strong>確認する</strong><span>読み取り結果をチェック</span></article><article><b>3</b><strong>編集する</strong><span>状態と矢印を直す</span></article><article><b>4</b><strong>動かす</strong><span>イベントを押して確認</span></article></div></section>
  </main>;

  return <main>
    <header><div className="brand"><button className="home-link" aria-label="ホームへ戻る" onClick={() => setScreen('home')}><Home size={18}/></button><span className="brand-mark">S</span><div><h1>StateInk</h1><p>描いた設計を、動かして確かめる。</p></div></div><div className="header-actions"><button onClick={() => setShowRecognition(true)}><ImagePlus size={16}/>紙から読み取る</button><label>サンプル<select aria-label="サンプル" value={sampleKey} onChange={(event) => chooseSample(event.target.value as keyof typeof samples)}><option value="valid">正常な自動販売機</option><option value="broken">問題のある自動販売機</option></select></label></div></header>
    <nav className="flow-steps" aria-label="このツールの進めかた">
      {[{ n: 1, label: '読み込む' }, { n: 2, label: '確認する' }, { n: 3, label: '編集する' }, { n: 4, label: '動かす' }].map((step) => {
        const isCurrent = showRecognition ? step.n <= 2 : step.n >= 3;
        return <span key={step.n} className="flow-step" data-state={isCurrent ? 'current' : 'idle'} aria-current={isCurrent ? 'step' : undefined}><b>{step.n}</b>{step.label}</span>;
      })}
    </nav>
    <section className="file-toolbar" aria-label="ファイル操作"><div><button onClick={() => openWorkspace({ states: [], transitions: [] })}><FilePenLine size={15}/>新規作成</button><label className="toolbar-button"><Upload size={15}/>JSON読込<input type="file" accept="application/json,.json" onChange={importJson}/></label></div><div className="export-actions"><span>Export ・ 書き出し</span><button onClick={() => downloadText('stateink-machine.json', machineToJson(machine), 'application/json')}><FileJson size={15}/>JSON</button><button onClick={() => downloadText('stateink-diagram.svg', machineToSvg(machine), 'image/svg+xml')}><Download size={15}/>SVG</button><button onClick={() => downloadPng(machine).catch(() => setFileError('PNGを作成できませんでした。'))}><Download size={15}/>PNG</button></div></section>
    {fileError && <p className="file-error" role="alert">{fileError}</p>}
    {showRecognition && <div className="recognition-wrap"><RecognitionPanel onClose={() => setShowRecognition(false)} onConfirm={(next) => { setMachine(next); setSimulation(createSimulation(next)); setReplayedPath(undefined); setShowRecognition(false); setSelectedStateId(undefined); setSelectedTransitionId(undefined); setTransitionDraft({ from: next.states[0]?.id ?? '', to: next.states[0]?.id ?? '', event: '' }); }}/></div>}
    <section className="intro"><p className="eyebrow">編集 → 実行 → 自動チェック</p><h2>{sampleKey === 'broken' ? 'まず問題を再現し、refund 遷移を追加して直してみましょう。' : '図を直すと、チェック結果もすぐに変わります。'}</h2><p>{sampleKey === 'broken' ? 'coin → select → sold_out を押すと問題状態へ進みます。売り切れから待機への refund を追加すると警告が消えます。' : '状態を選んで編集するか、下のフォームで遷移を追加してください。編集するとシミュレーターは開始地点へ戻ります。'}</p></section>
    <div className="workspace">
      <section className="card diagram"><div className="card-title"><div><span>01 / EDIT<span className="eyebrow-en"> DIAGRAM</span> ・ 図を編集</span><h2>状態遷移図</h2><p className="card-hint">状態（丸）と矢印を足したり直したりします。図の中の状態・矢印をクリックすると、下で名前を編集できます。</p></div><button className="primary small" onClick={() => { const next = addState(machine, '新しい状態', { x: 100 + machine.states.length * 25, y: 300 }); applyEdit(() => next); setSelectedStateId(next.states.at(-1)?.id); }}><CirclePlus size={16}/> 状態を追加</button></div>
        <div className="flow"><ReactFlow key={sampleKey} nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.22 }} minZoom={0.4} maxZoom={1.5} nodesDraggable nodesConnectable={false} onNodeClick={selectNode} onEdgeClick={selectEdge} onNodeDragStop={(_, node) => applyEdit((value) => updateState(value, node.id, { position: node.position }))}><Background gap={20}/><Controls showInteractive={false}/></ReactFlow></div>
        <div className="editor" aria-label="図の編集">
          {selectedState ? <div className="edit-block"><div className="edit-heading"><strong>状態「{selectedState.name}」を編集</strong><button className="danger-link" onClick={() => { applyEdit((value) => removeState(value, selectedState.id)); setSelectedStateId(undefined); }}><Trash2 size={14}/>削除</button></div><label>状態名<input value={selectedState.name} onChange={(event) => applyEdit((value) => updateState(value, selectedState.id, { name: event.target.value }))}/></label><div className="checks"><label><input type="radio" name="initial" checked={Boolean(selectedState.initial)} onChange={() => applyEdit((value) => setInitialState(value, selectedState.id))}/> 開始状態にする</label><label><input type="checkbox" checked={Boolean(selectedState.final)} onChange={(event) => applyEdit((value) => updateState(value, selectedState.id, { final: event.target.checked }))}/> 正常終了にする</label></div></div> : selectedTransition ? <div className="edit-block"><div className="edit-heading"><strong>遷移を編集</strong><button className="danger-link" onClick={() => { applyEdit((value) => removeTransition(value, selectedTransition.id)); setSelectedTransitionId(undefined); }}><Trash2 size={14}/>削除</button></div><label>イベント名<input value={selectedTransition.event} onChange={(event) => applyEdit((value) => updateTransitionEvent(value, selectedTransition.id, event.target.value))}/></label></div> : <p className="editor-hint">図の状態または矢印を選ぶと、名前や設定を編集できます。</p>}
          <form className="transition-form" onSubmit={(event) => { event.preventDefault(); const next = addTransition(machine, transitionDraft.from, transitionDraft.to, transitionDraft.event); if (next !== machine) { applyEdit(() => next); setTransitionDraft((draft) => ({ ...draft, event: '' })); } }}><strong>遷移を追加</strong><label>移動元<select aria-label="遷移の移動元" value={transitionDraft.from} onChange={(event) => setTransitionDraft({ ...transitionDraft, from: event.target.value })}>{machine.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><span>→</span><label>移動先<select aria-label="遷移の移動先" value={transitionDraft.to} onChange={(event) => setTransitionDraft({ ...transitionDraft, to: event.target.value })}>{machine.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><label>イベント<input aria-label="遷移のイベント" placeholder="例: refund" value={transitionDraft.event} onChange={(event) => setTransitionDraft({ ...transitionDraft, event: event.target.value })}/></label><button className="primary" disabled={!transitionDraft.event.trim() || machine.states.length === 0}>追加</button></form>
        </div>
      </section>
      <aside><section className="card simulator" ref={simulatorRef}><div className="card-title"><div><span>02 / RUN<span className="eyebrow-en"> ・ SIMULATE</span> ・ 動かす</span><h2>動作を試す</h2><p className="card-hint">イベントのボタンを押すと、図がその通りに動きます（Simulator）。</p></div><button className="reset" onClick={() => { setSimulation(reset(machine)); setReplayedPath(undefined); }}><RotateCcw size={15}/>リセット</button></div>{simulation.error ? <div className="blocked"><AlertTriangle/><div>{initialErrorText[simulation.error]}<span className="blocked-fix">図で開始状態（▶）をちょうど1つ設定してください。</span></div></div> : <><p className="caption">現在の状態</p><div className="current" aria-live="polite"><Play size={18} fill="currentColor"/><strong>{current?.name}</strong></div>{replayedPath && <p className="replay-status" role="status">最短操作列を再現し、経路を図で強調しています。</p>}<p className="caption">利用可能な操作</p><div className="events">{availableEvents(machine, simulation).map((event) => <button key={event} onClick={() => { setReplayedPath(undefined); setSimulation((previous) => transition(machine, previous, event)); }}>{event}<span>→</span></button>)}{availableEvents(machine, simulation).length === 0 && <p className="empty">この状態から進めるイベントがありません。行き止まりでなければ、Editorで遷移を追加してください。</p>}</div><p className="caption">操作の履歴（Trace）</p><ol className="trace">{simulation.trace.map((step, index) => <li key={`${index}-${step.stateId}`}>{step.event && <><b>{step.event}</b><span>→</span></>}<strong>{machine.states.find((state) => state.id === step.stateId)?.name}</strong></li>)}</ol></>}</section>
        <section className="card analysis"><div className="card-title"><div><span>03 / CHECK<span className="eyebrow-en"> ・ LIVE</span> ・ 設計チェック</span><h2>設計チェック</h2><p className="card-hint">編集するたびに、行き止まり・到達不能などの問題を自動で調べます（Analyzer）。</p></div><span className="live">● 自動更新</span></div><div className="analysis-body" aria-live="polite">{shownIssues.length === 0 ? <div className="success"><CheckCircle2/><div><strong>問題は見つかりませんでした</strong><p>編集内容はすぐにチェックされています。</p></div></div> : <><div className="issue-count"><AlertTriangle/><strong>確認したい問題が{shownIssues.length}件あります</strong></div>{shownIssues.map((item, index) => <article className="issue" key={`${item.type}-${index}`}><h3>{item.title}</h3><p className="issue-desc"><span className="issue-label">どうなる？</span>{item.description}</p>{item.counterexample && item.counterexample.length > 0 ? <div className="reproduce"><span>問題を再現する操作</span><strong>{item.counterexample.join(' → ')}</strong><button onClick={() => replayCounterexample(item.counterexample ?? [])}>問題を再現</button></div> : item.type === 'unreachable' || item.type === 'isolated' ? <p className="no-path">初期状態から到達できないため、再現操作はありません。</p> : null}{item.suggestions?.map((suggestion) => <div className="fix-suggestion" key={`${suggestion.from}-${suggestion.to}-${suggestion.event}`}><span>直し方（押すと追加）</span><strong>{suggestion.description}</strong><code>{suggestion.event}</code><button onClick={() => applyEdit((value) => addTransition(value, suggestion.from, suggestion.to, suggestion.event))}>この候補を追加</button></div>)}<small>{item.technicalName}</small></article>)}</>}</div></section></aside>
    </div>
  </main>;
}
