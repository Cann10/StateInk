import { describe, expect, it } from 'vitest';
import { isValidStateMachine } from './validate';

const state = (id: string, extra: Record<string, unknown> = {}) => ({ id, name: id, position: { x: 0, y: 0 }, ...extra });

describe('isValidStateMachine', () => {
  it('accepts a well-formed machine', () => {
    expect(isValidStateMachine({ states: [state('a', { initial: true }), state('b')], transitions: [{ id: 't', from: 'a', to: 'b', event: 'go' }] })).toBe(true);
  });

  it('accepts an empty machine', () => {
    expect(isValidStateMachine({ states: [], transitions: [] })).toBe(true);
  });

  it('rejects non-objects and missing arrays', () => {
    expect(isValidStateMachine(null)).toBe(false);
    expect(isValidStateMachine('{}')).toBe(false);
    expect(isValidStateMachine({ states: [] })).toBe(false);
    expect(isValidStateMachine({ states: {}, transitions: [] })).toBe(false);
  });

  it('rejects malformed state entries', () => {
    expect(isValidStateMachine({ states: [{ id: 'a' }], transitions: [] })).toBe(false);
    expect(isValidStateMachine({ states: [{ id: 'a', name: 'a', position: { x: 'nope', y: 0 } }], transitions: [] })).toBe(false);
    expect(isValidStateMachine({ states: [null], transitions: [] })).toBe(false);
  });

  it('rejects duplicate state ids', () => {
    expect(isValidStateMachine({ states: [state('a'), state('a')], transitions: [] })).toBe(false);
  });

  it('rejects transitions that reference unknown states', () => {
    expect(isValidStateMachine({ states: [state('a')], transitions: [{ id: 't', from: 'a', to: 'ghost', event: 'go' }] })).toBe(false);
    expect(isValidStateMachine({ states: [state('a')], transitions: [{ id: 't', from: 'a', to: 'a' }] })).toBe(false);
  });
});
