import type { StateMachine } from '../../core/types';
import { isValidStateMachine } from '../../core/validate';

export const workspaceStorageKey = 'stateink.workspace.v1';

export interface SavedWorkspace {
  machine: StateMachine;
  sampleKey: 'valid' | 'broken';
  screen: 'home' | 'workspace';
}

export function parseSavedWorkspace(value: string | null): SavedWorkspace | undefined {
  if (!value) return undefined;
  try {
    const candidate = JSON.parse(value) as Partial<SavedWorkspace>;
    if (!isValidStateMachine(candidate.machine)) return undefined;
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
  try {
    return parseSavedWorkspace(window.localStorage.getItem(workspaceStorageKey));
  } catch {
    return undefined;
  }
}

export function saveWorkspace(workspace: SavedWorkspace): void {
  try {
    window.localStorage.setItem(workspaceStorageKey, JSON.stringify(workspace));
  } catch {
    // Storage can be full, disabled, or blocked (private mode). Losing the
    // autosave is acceptable; a thrown error here must not break the app.
  }
}

export function clearSavedWorkspace(): void {
  try {
    window.localStorage.removeItem(workspaceStorageKey);
  } catch {
    // Ignore: nothing to recover if storage is unavailable.
  }
}
