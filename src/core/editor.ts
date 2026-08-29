import type { Position, StateMachine } from './types';

export function addState(machine: StateMachine, name = '新しい状態', position: Position = { x: 100, y: 100 }): StateMachine {
  let suffix = machine.states.length + 1;
  while (machine.states.some((state) => state.id === `state-${suffix}`)) suffix += 1;
  return { ...machine, states: [...machine.states, { id: `state-${suffix}`, name, position }] };
}

export function removeState(machine: StateMachine, stateId: string): StateMachine {
  return { states: machine.states.filter((state) => state.id !== stateId), transitions: machine.transitions.filter((edge) => edge.from !== stateId && edge.to !== stateId) };
}

/** How many transitions would also disappear if this state were removed. */
export function connectedTransitionCount(machine: StateMachine, stateId: string): number {
  return machine.transitions.filter((edge) => edge.from === stateId || edge.to === stateId).length;
}

export function updateState(machine: StateMachine, stateId: string, changes: Partial<Pick<StateMachine['states'][number], 'name' | 'position' | 'initial' | 'final'>>): StateMachine {
  return { ...machine, states: machine.states.map((state) => state.id === stateId ? { ...state, ...changes } : state) };
}

export function setInitialState(machine: StateMachine, stateId: string): StateMachine {
  return { ...machine, states: machine.states.map((state) => ({ ...state, initial: state.id === stateId })) };
}

export function addTransition(machine: StateMachine, from: string, to: string, event: string): StateMachine {
  const trimmed = event.trim();
  if (!trimmed || !machine.states.some((state) => state.id === from) || !machine.states.some((state) => state.id === to)) return machine;
  let suffix = machine.transitions.length + 1;
  while (machine.transitions.some((edge) => edge.id === `transition-${suffix}`)) suffix += 1;
  return { ...machine, transitions: [...machine.transitions, { id: `transition-${suffix}`, from, to, event: trimmed }] };
}

export function updateTransitionEvent(machine: StateMachine, transitionId: string, event: string): StateMachine {
  const trimmed = event.trim();
  if (!trimmed) return machine;
  return { ...machine, transitions: machine.transitions.map((edge) => edge.id === transitionId ? { ...edge, event: trimmed } : edge) };
}

export function removeTransition(machine: StateMachine, transitionId: string): StateMachine {
  return { ...machine, transitions: machine.transitions.filter((edge) => edge.id !== transitionId) };
}
