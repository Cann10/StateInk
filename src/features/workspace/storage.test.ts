import { describe, expect, it } from 'vitest';
import { clearSavedWorkspace, loadSavedWorkspace, parseSavedWorkspace, saveWorkspace, type SavedWorkspace } from './storage';

describe('parseSavedWorkspace', () => {
  it('restores a saved workspace', () => {
    const saved = { machine: { states: [], transitions: [] }, sampleKey: 'broken', screen: 'workspace' };
    expect(parseSavedWorkspace(JSON.stringify(saved))).toEqual(saved);
  });

  it('ignores corrupt or incompatible storage', () => {
    expect(parseSavedWorkspace('{broken')).toBeUndefined();
    expect(parseSavedWorkspace(JSON.stringify({ machine: {} }))).toBeUndefined();
  });

  it('rejects a machine whose entries would crash the editor', () => {
    expect(parseSavedWorkspace(JSON.stringify({ machine: { states: [{ id: 'a' }], transitions: [] } }))).toBeUndefined();
    expect(parseSavedWorkspace(JSON.stringify({ machine: { states: [], transitions: [{ id: 't', from: 'x', to: 'y', event: 'go' }] } }))).toBeUndefined();
  });
});

describe('storage side effects never throw', () => {
  const workspace: SavedWorkspace = { machine: { states: [], transitions: [] }, sampleKey: 'valid', screen: 'home' };

  it('save/clear swallow unavailable-storage errors', () => {
    expect(() => saveWorkspace(workspace)).not.toThrow();
    expect(() => clearSavedWorkspace()).not.toThrow();
  });

  it('load returns undefined when storage is unavailable', () => {
    expect(loadSavedWorkspace()).toBeUndefined();
  });
});
