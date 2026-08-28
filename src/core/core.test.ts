import { describe, expect, it } from 'vitest';
import { analyze } from './analyzer';
import { shortestEventPath } from './counterexample';
import { availableEvents, createSimulation, replayEvents, reset, transition } from './simulator';
import { addState, addTransition, removeState, removeTransition, updateState } from './editor';
import type { StateMachine } from './types';
import { vendingMachine } from '../samples/vendingMachine';

const state = (id: string, initial = false) => ({ id, name: id, position: { x: 0, y: 0 }, initial });
const machine = (states: StateMachine['states'], transitions: StateMachine['transitions'] = []): StateMachine => ({ states, transitions });
const edge = (id: string, from: string, to: string, event = id) => ({ id, from, to, event });

describe('analyzer', () => {
  it('accepts the valid vending machine', () => expect(analyze(vendingMachine)).toEqual([]));
  it('detects a missing initial state', () => expect(analyze(machine([state('a')]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'missing-initial' })])));
  it('detects multiple initial states', () => expect(analyze(machine([state('a', true), state('b', true)]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'multiple-initial' })])));
  it('detects an unreachable state', () => expect(analyze(machine([state('a', true), state('b'), state('c')], [edge('ab', 'a', 'b'), edge('cb', 'c', 'b')]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'unreachable', stateIds: ['c'] })])));
  it('detects a reachable dead end and suggests a reviewed return transition', () => expect(analyze(machine([state('a', true), state('b')], [edge('go', 'a', 'b')]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'dead-end', counterexample: ['go'], suggestions: [expect.objectContaining({ from: 'b', to: 'a', event: 'return' })] })])));
  it('detects an isolated state', () => expect(analyze(machine([state('a', true), state('alone')], [edge('loop', 'a', 'a')]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'isolated', stateIds: ['alone'] })])));
  it('detects a transition conflict', () => expect(analyze(machine([state('a', true), state('b'), state('c')], [edge('one', 'a', 'b', 'go'), edge('two', 'a', 'c', 'go')]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'transition-conflict' })])));
  it('detects a cycle that cannot reach an existing final state', () => expect(analyze(machine([state('a', true), state('b'), state('c'), { ...state('done'), final: true }], [edge('enter', 'a', 'b'), edge('finish', 'a', 'done'), edge('bc', 'b', 'c'), edge('cb', 'c', 'b')]))).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'non-terminating-cycle' })])));
  it('does not report a final state as a dead end', () => expect(analyze(machine([{ ...state('a', true), final: true }])).some((item) => item.type === 'dead-end')).toBe(false));
  it('does not duplicate a trivial dead end as a cycle', () => { const result = analyze(machine([state('a', true), state('b')], [edge('go', 'a', 'b')])); expect(result.filter((item) => item.type === 'dead-end')).toHaveLength(1); expect(result.some((item) => item.type === 'non-terminating-cycle')).toBe(false); });
  it('does not warn for a self-loop when the machine has no final state', () => expect(analyze(machine([state('a', true), state('b')], [edge('go', 'a', 'b'), edge('loop', 'b', 'b')])).some((item) => item.type === 'non-terminating-cycle')).toBe(false));
  it('does not warn for a traffic-light cycle without final states', () => { const result = analyze(machine([state('red', true), state('yellow'), state('green')], [edge('rg', 'red', 'green'), edge('gy', 'green', 'yellow'), edge('yr', 'yellow', 'red')])); expect(result.some((item) => item.type === 'non-terminating-cycle')).toBe(false); });
  it('warns for a self-loop that cannot reach an existing final state', () => { const result = analyze(machine([state('a', true), state('loop'), { ...state('done'), final: true }], [edge('enter', 'a', 'loop'), edge('finish', 'a', 'done'), edge('stay', 'loop', 'loop')])); expect(result).toEqual(expect.arrayContaining([expect.objectContaining({ type: 'non-terminating-cycle', stateIds: ['loop'] })])); });
  it('does not warn for an SCC containing a final state', () => { const result = analyze(machine([state('a', true), { ...state('done'), final: true }], [edge('finish', 'a', 'done'), edge('again', 'done', 'a')])); expect(result.some((item) => item.type === 'non-terminating-cycle')).toBe(false); });
  it('does not warn for an SCC with a path to a final state', () => { const result = analyze(machine([state('a', true), state('b'), state('c'), { ...state('done'), final: true }], [edge('enter', 'a', 'b'), edge('bc', 'b', 'c'), edge('cb', 'c', 'b'), edge('finish', 'c', 'done')])); expect(result.some((item) => item.type === 'non-terminating-cycle')).toBe(false); });
  it('does not invent a counterexample for an unreachable issue', () => { const found = analyze(machine([state('a', true), state('b'), state('c')], [edge('loop', 'a', 'a'), edge('cb', 'c', 'b')])); expect(found.find((item) => item.type === 'unreachable')?.counterexample).toBeUndefined(); });
});

describe('counterexample', () => {
  it('returns the shortest event path', () => { const value = machine([state('a', true), state('b'), state('c')], [edge('direct', 'a', 'c'), edge('ab', 'a', 'b'), edge('bc', 'b', 'c')]); expect(shortestEventPath(value, 'c')).toEqual(['direct']); });
});

describe('simulator', () => {
  it('transitions and records its trace', () => { const start = createSimulation(vendingMachine); const next = transition(vendingMachine, start, 'coin'); expect(next.currentStateId).toBe('paid'); expect(next.trace).toEqual([{ stateId: 'idle' }, { event: 'coin', stateId: 'paid' }]); expect(availableEvents(vendingMachine, next)).toEqual(['select', 'return']); });
  it('ignores an invalid event without mutation', () => { const start = createSimulation(vendingMachine); expect(transition(vendingMachine, start, 'hack')).toBe(start); });
  it('resets to the initial state', () => { const moved = transition(vendingMachine, createSimulation(vendingMachine), 'coin'); expect(reset(vendingMachine)).toEqual({ currentStateId: 'idle', trace: [{ stateId: 'idle' }] }); expect(moved.currentStateId).toBe('paid'); });
  it('refuses to start without exactly one initial state', () => { expect(createSimulation(machine([state('a')]))).toEqual({ trace: [], error: 'missing-initial' }); expect(createSimulation(machine([state('a', true), state('b', true)]))).toEqual({ trace: [], error: 'multiple-initial' }); });
  it('refuses an ambiguous transition conflict', () => { const value = machine([state('a', true), state('b'), state('c')], [edge('one', 'a', 'b', 'go'), edge('two', 'a', 'c', 'go')]); const start = createSimulation(value); expect(transition(value, start, 'go')).toBe(start); });
  it('replays a shortest operation sequence and returns its highlighted path', () => { const replay = replayEvents(vendingMachine, ['coin', 'select']); expect(replay.simulation.currentStateId).toBe('selected'); expect(replay.stateIds).toEqual(['idle', 'paid', 'selected']); expect(replay.transitionIds).toEqual(['coin', 'select']); });
});

describe('editor', () => {
  it('adds, renames, and deletes a state with connected transitions', () => { const added = addState(vendingMachine, '修理中'); const id = added.states.at(-1)?.id ?? ''; expect(added.states.at(-1)?.name).toBe('修理中'); const renamed = updateState(added, id, { name: '点検中' }); expect(renamed.states.at(-1)?.name).toBe('点検中'); const linked = addTransition(renamed, 'idle', id, 'inspect'); const removed = removeState(linked, id); expect(removed.states.some((item) => item.id === id)).toBe(false); expect(removed.transitions.some((item) => item.to === id)).toBe(false); });
  it('adds and removes a transition', () => { const added = addTransition(vendingMachine, 'idle', 'paid', 'card'); const created = added.transitions.at(-1); expect(created?.event).toBe('card'); expect(removeTransition(added, created?.id ?? '').transitions).toHaveLength(vendingMachine.transitions.length); });
  it('immediately analyzes an edited machine', () => { const fixed = addTransition(machine([state('a', true), state('b')], [edge('go', 'a', 'b')]), 'b', 'a', 'back'); expect(analyze(fixed)).toEqual([]); });
});
