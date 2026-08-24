import { describe, expect, it } from 'vitest';
import { parseSavedWorkspace } from './storage';

describe('parseSavedWorkspace', () => {
  it('restores a saved workspace', () => {
    const saved = { machine: { states: [], transitions: [] }, sampleKey: 'broken', screen: 'workspace' };
    expect(parseSavedWorkspace(JSON.stringify(saved))).toEqual(saved);
  });

  it('ignores corrupt or incompatible storage', () => {
    expect(parseSavedWorkspace('{broken')).toBeUndefined();
    expect(parseSavedWorkspace(JSON.stringify({ machine: {} }))).toBeUndefined();
  });
});
