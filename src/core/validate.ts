import type { StateMachine } from './types';

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function isValidState(value: unknown): boolean {
  if (typeof value !== 'object' || value === null) return false;
  const state = value as Record<string, unknown>;
  const position = state.position as Record<string, unknown> | null | undefined;
  return typeof state.id === 'string' && state.id.length > 0
    && typeof state.name === 'string'
    && typeof position === 'object' && position !== null
    && isFiniteNumber(position.x) && isFiniteNumber(position.y)
    && (state.initial === undefined || typeof state.initial === 'boolean')
    && (state.final === undefined || typeof state.final === 'boolean');
}

function isValidTransition(value: unknown, stateIds: ReadonlySet<string>): boolean {
  if (typeof value !== 'object' || value === null) return false;
  const transition = value as Record<string, unknown>;
  return typeof transition.id === 'string' && transition.id.length > 0
    && typeof transition.from === 'string' && stateIds.has(transition.from)
    && typeof transition.to === 'string' && stateIds.has(transition.to)
    && typeof transition.event === 'string';
}

/**
 * Deep structural check for a persisted or imported machine. Anything that would
 * crash the editor (missing ids, non-numeric positions, dangling transitions) is
 * rejected here so callers can safely fall back instead of rendering garbage.
 */
export function isValidStateMachine(value: unknown): value is StateMachine {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  if (!Array.isArray(candidate.states) || !Array.isArray(candidate.transitions)) return false;
  if (!candidate.states.every(isValidState)) return false;
  const stateIds = new Set(candidate.states.map((state) => (state as { id: string }).id));
  if (stateIds.size !== candidate.states.length) return false;
  return (candidate.transitions as unknown[]).every((transition) => isValidTransition(transition, stateIds));
}
