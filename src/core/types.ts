export interface Position { x: number; y: number }
export interface State { id: string; name: string; position: Position; initial?: boolean; final?: boolean }
export interface Transition { id: string; from: string; to: string; event: string }
export interface StateMachine { states: State[]; transitions: Transition[] }
export interface TraceStep { stateId: string; event?: string }

export type IssueType = 'missing-initial' | 'multiple-initial' | 'unreachable' | 'dead-end' | 'isolated' | 'transition-conflict' | 'non-terminating-cycle';
export interface AnalysisIssue {
  type: IssueType;
  severity: 'error' | 'warning';
  title: string;
  technicalName: string;
  description: string;
  stateIds: string[];
  events?: string[];
  counterexample?: string[];
  suggestions?: TransitionSuggestion[];
}

export interface TransitionSuggestion {
  kind: 'add-transition';
  from: string;
  to: string;
  event: string;
  description: string;
}
