import type { StateMachine } from '../../core/types';
import type { RecognitionResult } from './types';

export function recognitionToStateMachine(result: RecognitionResult): StateMachine {
  const validIds = new Set(result.states.map((state) => state.id));
  return {
    states: result.states.map((state) => ({ id: state.id, name: state.name.trim() || state.id, position: { x: state.geometry.x, y: state.geometry.y }, initial: state.initial, final: state.final })),
    transitions: result.transitions.filter((edge) => validIds.has(edge.from) && validIds.has(edge.to)).map((edge) => ({ id: edge.id, from: edge.from, to: edge.to, event: edge.event.trim() || 'event' })),
  };
}
