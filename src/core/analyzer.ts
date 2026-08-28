import { shortestEventPath } from './counterexample';
import type { AnalysisIssue, StateMachine } from './types';

const issue = (value: AnalysisIssue): AnalysisIssue => value;

function reachable(machine: StateMachine): Set<string> {
  const starts = machine.states.filter((state) => state.initial).map((state) => state.id);
  const seen = new Set(starts); const queue = [...starts];
  for (let id = queue.shift(); id; id = queue.shift()) {
    for (const edge of machine.transitions.filter((item) => item.from === id)) if (!seen.has(edge.to)) { seen.add(edge.to); queue.push(edge.to); }
  }
  return seen;
}

// Tarjan identifies maximal cycles; termination reachability is evaluated afterwards.
function nonTerminatingComponents(machine: StateMachine, reached: Set<string>): string[][] {
  const finalIds = new Set(machine.states.filter((state) => state.final).map((state) => state.id));
  if (finalIds.size === 0) return [];
  let next = 0; const index = new Map<string, number>(); const low = new Map<string, number>();
  const stack: string[] = []; const onStack = new Set<string>(); const components: string[][] = [];
  const visit = (id: string): void => {
    index.set(id, next); low.set(id, next++); stack.push(id); onStack.add(id);
    for (const edge of machine.transitions.filter((item) => item.from === id)) {
      if (!index.has(edge.to)) { visit(edge.to); low.set(id, Math.min(low.get(id) ?? 0, low.get(edge.to) ?? 0)); }
      else if (onStack.has(edge.to)) low.set(id, Math.min(low.get(id) ?? 0, index.get(edge.to) ?? 0));
    }
    if (low.get(id) === index.get(id)) { const component: string[] = []; let node: string | undefined; do { node = stack.pop(); if (node) { onStack.delete(node); component.push(node); } } while (node !== id); components.push(component); }
  };
  machine.states.forEach((state) => { if (!index.has(state.id)) visit(state.id); });
  const canReachFinal = (startIds: string[]): boolean => {
    const seen = new Set(startIds); const queue = [...startIds];
    for (let id = queue.shift(); id; id = queue.shift()) {
      if (finalIds.has(id)) return true;
      for (const edge of machine.transitions.filter((item) => item.from === id)) if (!seen.has(edge.to)) { seen.add(edge.to); queue.push(edge.to); }
    }
    return false;
  };
  return components.filter((component) => {
    const isCycle = component.length > 1 || machine.transitions.some((edge) => edge.from === component[0] && edge.to === component[0]);
    return isCycle && component.some((id) => reached.has(id)) && !canReachFinal(component);
  });
}

export function analyze(machine: StateMachine): AnalysisIssue[] {
  const issues: AnalysisIssue[] = []; const initials = machine.states.filter((state) => state.initial);
  const singleInitial = initials.length === 1 ? initials[0] : undefined;
  if (initials.length === 0) issues.push(issue({ type: 'missing-initial', severity: 'error', title: '開始地点がありません', technicalName: 'Missing Initial State', description: '最初に動き始める状態を1つ指定してください。', stateIds: [] }));
  if (initials.length > 1) issues.push(issue({ type: 'multiple-initial', severity: 'error', title: '開始地点が複数あります', technicalName: 'Multiple Initial States', description: '開始状態は1つだけにしてください。', stateIds: initials.map((state) => state.id) }));
  const reached = reachable(machine);
  for (const state of machine.states) {
    const incoming = machine.transitions.some((edge) => edge.to === state.id); const outgoing = machine.transitions.some((edge) => edge.from === state.id);
    if (!incoming && !outgoing && !state.initial) issues.push(issue({ type: 'isolated', severity: 'warning', title: `「${state.name}」が図から孤立しています`, technicalName: 'Isolated State', description: 'この状態はほかの状態とつながっていません。', stateIds: [state.id] }));
    else if (!reached.has(state.id)) issues.push(issue({ type: 'unreachable', severity: 'warning', title: `「${state.name}」には到達できません`, technicalName: 'Unreachable State', description: '開始地点からこの状態へ移動する操作がありません。', stateIds: [state.id] }));
    if (!outgoing && !state.final && reached.has(state.id)) issues.push(issue({
      type: 'dead-end', severity: 'error', title: `「${state.name}」に入ると、どこにも移動できません`, technicalName: 'Dead End State', description: '意図した終了状態でなければ、戻る遷移を追加してください。', stateIds: [state.id], counterexample: shortestEventPath(machine, state.id),
      suggestions: singleInitial && singleInitial.id !== state.id ? [{ kind: 'add-transition', from: state.id, to: singleInitial.id, event: 'return', description: `「${singleInitial.name}」へ戻る遷移を追加` }] : undefined,
    }));
  }
  const grouped = new Map<string, typeof machine.transitions>();
  for (const edge of machine.transitions) { const key = `${edge.from}\0${edge.event}`; grouped.set(key, [...(grouped.get(key) ?? []), edge]); }
  for (const edges of grouped.values()) if (edges.length > 1 && new Set(edges.map((edge) => edge.to)).size > 1) {
    const source = machine.states.find((state) => state.id === edges[0].from);
    issues.push(issue({ type: 'transition-conflict', severity: 'error', title: '同じ操作に複数の行き先があります', technicalName: 'Transition Conflict', description: `「${source?.name ?? edges[0].from}」の「${edges[0].event}」の行き先を1つにしてください。`, stateIds: [edges[0].from, ...edges.map((edge) => edge.to)], events: [edges[0].event], counterexample: shortestEventPath(machine, edges[0].from) }));
  }
  for (const component of nonTerminatingComponents(machine, reached)) issues.push(issue({ type: 'non-terminating-cycle', severity: 'warning', title: 'このループに入ると、正常終了へ進めません', technicalName: 'Non-terminating Cycle', description: 'ループ内から、正常終了として設定された状態へ移動する経路がありません。', stateIds: component, counterexample: shortestEventPath(machine, component[0]) }));
  return issues;
}
