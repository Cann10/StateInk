import { describe, expect, it } from 'vitest';
import { recognitionToStateMachine } from './toStateMachine';

describe('recognitionToStateMachine', () => {
  it('converts reviewed recognition data and drops dangling transitions', () => {
    const machine = recognitionToStateMachine({ processing_ms: 12, warnings: [], states: [{ id: 'a', name: ' Ready ', geometry: { x: 10, y: 20, width: 50, height: 30 }, confidence: .8, initial: true, final: false }], transitions: [{ id: 'bad', from: 'a', to: 'missing', event: 'go', geometry: { x: 0, y: 0, width: 1, height: 1 }, confidence: .4, direction_confirmed: true }] });
    expect(machine).toEqual({ states: [{ id: 'a', name: 'Ready', position: { x: 10, y: 20 }, initial: true, final: false }], transitions: [] });
  });
  it('does not promote an unconfirmed direction into the executable machine', () => {
    const machine = recognitionToStateMachine({ processing_ms: 12, warnings: [], states: [{ id: 'a', name: 'A', geometry: { x: 0, y: 0, width: 50, height: 30 }, confidence: .8, initial: true, final: false }, { id: 'b', name: 'B', geometry: { x: 80, y: 0, width: 50, height: 30 }, confidence: .8, initial: false, final: false }], transitions: [{ id: 'candidate', from: 'a', to: 'b', event: 'go', geometry: { x: 50, y: 15, width: 30, height: 0 }, confidence: .45, direction_confirmed: false }] });
    expect(machine.transitions).toEqual([]);
  });
});
