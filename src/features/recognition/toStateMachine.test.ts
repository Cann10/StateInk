import { describe, expect, it } from 'vitest';
import { recognitionToStateMachine } from './toStateMachine';

describe('recognitionToStateMachine', () => {
  it('converts reviewed recognition data and drops dangling transitions', () => {
    const machine = recognitionToStateMachine({ processing_ms: 12, warnings: [], states: [{ id: 'a', name: ' Ready ', geometry: { x: 10, y: 20, width: 50, height: 30 }, confidence: .8, initial: true, final: false }], transitions: [{ id: 'bad', from: 'a', to: 'missing', event: 'go', geometry: { x: 0, y: 0, width: 1, height: 1 }, confidence: .4 }] });
    expect(machine).toEqual({ states: [{ id: 'a', name: 'Ready', position: { x: 10, y: 20 }, initial: true, final: false }], transitions: [] });
  });
});
