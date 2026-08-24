import type { StateMachine, TraceStep } from './types';

export type SimulationError = 'missing-initial' | 'multiple-initial';
export interface Simulation { currentStateId?: string; trace: TraceStep[]; lastTransitionId?: string; error?: SimulationError }

export function createSimulation(machine: StateMachine): Simulation {
  const initials = machine.states.filter((state) => state.initial);
  if (initials.length === 0) return { trace: [], error: 'missing-initial' };
  if (initials.length > 1) return { trace: [], error: 'multiple-initial' };
  const initial = initials[0];
  return { currentStateId: initial.id, trace: [{ stateId: initial.id }] };
}
export function availableEvents(machine: StateMachine, simulation: Simulation): string[] {
  if (!simulation.currentStateId || simulation.error) return [];
  return [...new Set(machine.transitions.filter((edge) => edge.from === simulation.currentStateId).map((edge) => edge.event))];
}
export function transition(machine: StateMachine, simulation: Simulation, event: string): Simulation {
  if (!simulation.currentStateId || simulation.error) return simulation;
  const matches = machine.transitions.filter((edge) => edge.from === simulation.currentStateId && edge.event === event);
  if (matches.length !== 1) return simulation;
  const edge = matches[0];
  return { currentStateId: edge.to, lastTransitionId: edge.id, trace: [...simulation.trace, { event, stateId: edge.to }] };
}
export function reset(machine: StateMachine): Simulation { return createSimulation(machine); }
