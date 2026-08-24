import type { StateMachine } from './types';

/** BFS guarantees the first discovered path uses the fewest events. */
export function shortestEventPath(machine: StateMachine, targetId: string): string[] | undefined {
  const initial = machine.states.find((state) => state.initial);
  if (!initial) return undefined;
  const queue: Array<{ stateId: string; events: string[] }> = [{ stateId: initial.id, events: [] }];
  const visited = new Set([initial.id]);
  while (queue.length > 0) {
    const item = queue.shift();
    if (!item) break;
    if (item.stateId === targetId) return item.events;
    for (const transition of machine.transitions.filter((edge) => edge.from === item.stateId)) {
      if (!visited.has(transition.to)) {
        visited.add(transition.to);
        queue.push({ stateId: transition.to, events: [...item.events, transition.event] });
      }
    }
  }
  return undefined;
}
