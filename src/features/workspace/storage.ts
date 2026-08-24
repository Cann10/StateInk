import type { StateMachine } from '../../core/types';

export const workspaceStorageKey = 'stateink.workspace.v1';

export interface SavedWorkspace {
  machine: StateMachine;
  sampleKey: 'valid' | 'broken';
  screen: 'home' | 'workspace';
}

function isStateMachine(value: unknown): value is StateMachine {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Partial<StateMachine>;
  return Array.isArray(candidate.states) && Array.isArray(candidate.transitions);
}

export function parseSavedWorkspace(value: string | null): SavedWorkspace | undefined {
  if (!value) return undefined;
  try {
    const candidate = JSON.parse(value) as Partial<SavedWorkspace>;
    if (!isStateMachine(candidate.machine)) return undefined;
    return {
      machine: candidate.machine,
      sampleKey: candidate.sampleKey === 'broken' ? 'broken' : 'valid',
      screen: candidate.screen === 'workspace' ? 'workspace' : 'home',
    };
  } catch {
    return undefined;
  }
}

export function loadSavedWorkspace(): SavedWorkspace | undefined {
  if (typeof window === 'undefined') return undefined;
  return parseSavedWorkspace(window.localStorage.getItem(workspaceStorageKey));
}

export function saveWorkspace(workspace: SavedWorkspace): void {
  window.localStorage.setItem(workspaceStorageKey, JSON.stringify(workspace));
}
