import { useMemo, useState } from 'react';
import { Background, Controls, MarkerType, ReactFlow, type Edge, type Node, type NodeMouseHandler, type EdgeMouseHandler } from '@xyflow/react';
import { AlertTriangle, CheckCircle2, CirclePlus, FilePenLine, Home, ImagePlus, Play, RotateCcw, Sparkles, Trash2 } from 'lucide-react';
import { analyze } from './core/analyzer';
import { addState, addTransition, removeState, removeTransition, setInitialState, updateState, updateTransitionEvent } from './core/editor';
import { availableEvents, createSimulation, reset, transition, type Simulation } from './core/simulator';
import type { AnalysisIssue, StateMachine } from './core/types';
import { brokenVendingMachine } from './samples/brokenVendingMachine';
import { vendingMachine } from './samples/vendingMachine';
import { RecognitionPanel } from './features/recognition/RecognitionPanel';

const samples = { valid: vendingMachine, broken: brokenVendingMachine } as const;
const initialErrorText = { 'missing-initial': '開始状態がないため実行できません。', 'multiple-initial': '開始状態が複数あるため実行できません。' } as const;

function visibleIssues(issues: AnalysisIssue[]): AnalysisIssue[] {
  const initialIssues = issues.filter((item) => item.type === 'missing-initial' || item.type === 'multiple-initial');
  if (initialIssues.length > 0) return initialIssues;
  const deadEndStates = new Set(issues.filter((item) => item.type === 'dead-end').flatMap((item) => item.stateIds));
  return issues.filter((item) => item.type !== 'non-terminating-cycle' || !item.stateIds.every((id) => deadEndStates.has(id)));
}

export function App() {
  const [screen, setScreen] = useState<'home' | 'workspace'>('home');
  const [sampleKey, setSampleKey] = useState<keyof typeof samples>('valid');
  const [machine, setMachine] = useState<StateMachine>(vendingMachine);
  const [simulation, setSimulation] = useState<Simulation>(() => createSimulation(vendingMachine));
  const [selectedStateId, setSelectedStateId] = useState<string>();
  const [selectedTransitionId, setSelectedTransitionId] = useState<string>();
  const [transitionDraft, setTransitionDraft] = useState({ from: 'idle', to: 'idle', event: '' });
  const [showRecognition, setShowRecognition] = useState(false);
  const issues = useMemo(() => analyze(machine), [machine]);
  const shownIssues = visibleIssues(issues);
  const problemStates = new Set(shownIssues.flatMap((item) => item.stateIds));
  const current = machine.states.find((state) => state.id === simulation.currentStateId);
  const selectedState = machine.states.find((state) => state.id === selectedStateId);
  const selectedTransition = machine.transitions.find((edge) => edge.id === selectedTransitionId);

  const applyEdit = (edit: (previous: StateMachine) => StateMachine) => {
    setMachine((previous) => { const next = edit(previous); setSimulation(createSimulation(next)); return next; });
  };
  const chooseSample = (key: keyof typeof samples) => {
    const next = samples[key]; setSampleKey(key); setMachine(next); setSimulation(createSimulation(next));
    setSelectedStateId(undefined); setSelectedTransitionId(undefined); setTransitionDraft({ from: next.states[0]?.id ?? '', to: next.states[0]?.id ?? '', event: '' });
  };
  const nodes: Node[] = machine.states.map((state) => ({ id: state.id, position: state.position, data: { label: <div className="node-label"><span>{state.initial ? '▶ ' : ''}{state.name}{state.final ? ' ◎' : ''}</span>{state.initial && <small>開始</small>}{state.final && <small>正常終了</small>}{problemStates.has(state.id) && <small className="problem-label">⚠ 要確認</small>}</div> }, className: `${state.id === current?.id ? 'current-node' : ''} ${problemStates.has(state.id) ? 'problem-node' : ''} ${state.id === selectedStateId ? 'selected-node' : ''}` }));
  const edges: Edge[] = machine.transitions.map((edge) => ({ id: edge.id, source: edge.from, target: edge.to, label: edge.event, animated: edge.id === simulation.lastTransitionId, className: `${edge.id === simulation.lastTransitionId ? 'active-edge' : ''} ${edge.id === selectedTransitionId ? 'selected-edge' : ''}`, markerEnd: { type: MarkerType.ArrowClosed } }));
  const selectNode: NodeMouseHandler = (_, node) => { setSelectedStateId(node.id); setSelectedTransitionId(undefined); };
  const selectEdge: EdgeMouseHandler = (_, edge) => { setSelectedTransitionId(edge.id); setSelectedStateId(undefined); };

  const openWorkspace = (next: StateMachine, key: keyof typeof samples = 'valid') => {
    setSampleKey(key); setMachine(next); setSimulation(createSimulation(next)); setScreen('workspace');
    setSelectedStateId(undefined); setSelectedTransitionId(undefined);
    setTransitionDraft({ from: next.states[0]?.id ?? '', to: next.states[0]?.id ?? '', event: '' });
  };

  if (screen === 'home') return <main className="home-screen">
    <div className="home-brand"><span className="brand-mark">S</span><strong>StateInk</strong></div>
    <section className="hero"><p className="eyebrow">STATE MACHINE / VERIFY BEFORE YOU BUILD</p><h1>描いた設計を、<br/>動かして確かめる。</h1><p>紙の状態遷移図を、実行・検証できる設計図へ。</p></section>
    <nav className="start-options" aria-label="はじめる方法">
      <button onClick={() => { setScreen('workspace'); setShowRecognition(true); }}><ImagePlus/><span><strong>紙から読み取る</strong><small>写真から編集できる下書きを作る</small></span><b>→</b></button>
      <button onClick={() => openWorkspace({ states: [], transitions: [] })}><FilePenLine/><span><strong>自分で図を作る</strong><small>空のキャンバスから設計する</small></span><b>→</b></button>
      <button className="recommended" onClick={() => openWorkspace(brokenVendingMachine, 'broken')}><Sparkles/><span><strong>サンプルを試す</strong><small>問題発見と修正をすぐ体験</small></span><b>→</b></button>
    </nav>
  </main>;

  return <main>
    <header><div className="brand"><button className="home-link" aria-label="ホームへ戻る" onClick={() => setScreen('home')}><Home size={18}/></button><span className="brand-mark">S</span><div><h1>StateInk</h1><p>描いた設計を、動かして確かめる。</p></div></div><div className="header-actions"><button onClick={() => setShowRecognition(true)}><ImagePlus size={16}/>紙から読み取る</button><label>サンプル<select aria-label="サンプル" value={sampleKey} onChange={(event) => chooseSample(event.target.value as keyof typeof samples)}><option value="valid">正常な自動販売機</option><option value="broken">問題のある自動販売機</option></select></label></div></header>
    {showRecognition && <div className="recognition-wrap"><RecognitionPanel onClose={() => setShowRecognition(false)} onConfirm={(next) => { setMachine(next); setSimulation(createSimulation(next)); setShowRecognition(false); setSelectedStateId(undefined); setSelectedTransitionId(undefined); setTransitionDraft({ from: next.states[0]?.id ?? '', to: next.states[0]?.id ?? '', event: '' }); }}/></div>}
    <section className="intro"><p className="eyebrow">編集 → 実行 → 自動チェック</p><h2>{sampleKey === 'broken' ? 'まず問題を再現し、refund 遷移を追加して直してみましょう。' : '図を直すと、チェック結果もすぐに変わります。'}</h2><p>{sampleKey === 'broken' ? 'coin → select → sold_out を押すと問題状態へ進みます。売り切れから待機への refund を追加すると警告が消えます。' : '状態を選んで編集するか、下のフォームで遷移を追加してください。編集するとシミュレーターは開始地点へ戻ります。'}</p></section>
    <div className="workspace">
      <section className="card diagram"><div className="card-title"><div><span>01 / EDIT DIAGRAM</span><h2>状態遷移図</h2></div><button className="primary small" onClick={() => { const next = addState(machine, '新しい状態', { x: 100 + machine.states.length * 25, y: 300 }); applyEdit(() => next); setSelectedStateId(next.states.at(-1)?.id); }}><CirclePlus size={16}/> 状態を追加</button></div>
        <div className="flow"><ReactFlow key={sampleKey} nodes={nodes} edges={edges} fitView fitViewOptions={{ padding: 0.22 }} minZoom={0.4} maxZoom={1.5} nodesDraggable nodesConnectable={false} onNodeClick={selectNode} onEdgeClick={selectEdge} onNodeDragStop={(_, node) => applyEdit((value) => updateState(value, node.id, { position: node.position }))}><Background gap={20}/><Controls showInteractive={false}/></ReactFlow></div>
        <div className="editor" aria-label="図の編集">
          {selectedState ? <div className="edit-block"><div className="edit-heading"><strong>状態「{selectedState.name}」を編集</strong><button className="danger-link" onClick={() => { applyEdit((value) => removeState(value, selectedState.id)); setSelectedStateId(undefined); }}><Trash2 size={14}/>削除</button></div><label>状態名<input value={selectedState.name} onChange={(event) => applyEdit((value) => updateState(value, selectedState.id, { name: event.target.value }))}/></label><div className="checks"><label><input type="radio" name="initial" checked={Boolean(selectedState.initial)} onChange={() => applyEdit((value) => setInitialState(value, selectedState.id))}/> 開始状態にする</label><label><input type="checkbox" checked={Boolean(selectedState.final)} onChange={(event) => applyEdit((value) => updateState(value, selectedState.id, { final: event.target.checked }))}/> 正常終了にする</label></div></div> : selectedTransition ? <div className="edit-block"><div className="edit-heading"><strong>遷移を編集</strong><button className="danger-link" onClick={() => { applyEdit((value) => removeTransition(value, selectedTransition.id)); setSelectedTransitionId(undefined); }}><Trash2 size={14}/>削除</button></div><label>イベント名<input value={selectedTransition.event} onChange={(event) => applyEdit((value) => updateTransitionEvent(value, selectedTransition.id, event.target.value))}/></label></div> : <p className="editor-hint">図の状態または矢印を選ぶと、名前や設定を編集できます。</p>}
          <form className="transition-form" onSubmit={(event) => { event.preventDefault(); const next = addTransition(machine, transitionDraft.from, transitionDraft.to, transitionDraft.event); if (next !== machine) { applyEdit(() => next); setTransitionDraft((draft) => ({ ...draft, event: '' })); } }}><strong>遷移を追加</strong><label>移動元<select aria-label="遷移の移動元" value={transitionDraft.from} onChange={(event) => setTransitionDraft({ ...transitionDraft, from: event.target.value })}>{machine.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><span>→</span><label>移動先<select aria-label="遷移の移動先" value={transitionDraft.to} onChange={(event) => setTransitionDraft({ ...transitionDraft, to: event.target.value })}>{machine.states.map((state) => <option key={state.id} value={state.id}>{state.name}</option>)}</select></label><label>イベント<input aria-label="遷移のイベント" placeholder="例: refund" value={transitionDraft.event} onChange={(event) => setTransitionDraft({ ...transitionDraft, event: event.target.value })}/></label><button className="primary" disabled={!transitionDraft.event.trim() || machine.states.length === 0}>追加</button></form>
        </div>
      </section>
      <aside><section className="card simulator"><div className="card-title"><div><span>02 / SIMULATE</span><h2>動作を試す</h2></div><button className="reset" onClick={() => setSimulation(reset(machine))}><RotateCcw size={15}/>リセット</button></div>{simulation.error ? <div className="blocked"><AlertTriangle/>{initialErrorText[simulation.error]}</div> : <><p className="caption">現在の状態</p><div className="current"><Play size={18} fill="currentColor"/><strong>{current?.name}</strong></div><p className="caption">利用可能な操作</p><div className="events">{availableEvents(machine, simulation).map((event) => <button key={event} onClick={() => setSimulation((previous) => transition(machine, previous, event))}>{event}<span>→</span></button>)}{availableEvents(machine, simulation).length === 0 && <p className="empty">実行できる操作がありません</p>}</div><p className="caption">操作の履歴（Trace）</p><ol className="trace">{simulation.trace.map((step, index) => <li key={`${index}-${step.stateId}`}>{step.event && <><b>{step.event}</b><span>→</span></>}<strong>{machine.states.find((state) => state.id === step.stateId)?.name}</strong></li>)}</ol></>}</section>
        <section className="card analysis"><div className="card-title"><div><span>03 / LIVE CHECK</span><h2>設計チェック</h2></div><span className="live">● 自動更新</span></div>{shownIssues.length === 0 ? <div className="success"><CheckCircle2/><div><strong>問題は見つかりませんでした</strong><p>編集内容はすぐにチェックされています。</p></div></div> : <><div className="issue-count"><AlertTriangle/><strong>確認したい問題が{shownIssues.length}件あります</strong></div>{shownIssues.map((item, index) => <article className="issue" key={`${item.type}-${index}`}><h3>{item.title}</h3><p>{item.description}</p>{item.counterexample && item.counterexample.length > 0 ? <div className="reproduce"><span>問題を再現する操作</span><strong>{item.counterexample.join(' → ')}</strong></div> : item.type === 'unreachable' || item.type === 'isolated' ? <p className="no-path">初期状態から到達できないため、再現操作はありません。</p> : null}<small>{item.technicalName}</small></article>)}</>}</section></aside>
    </div>
  </main>;
}
