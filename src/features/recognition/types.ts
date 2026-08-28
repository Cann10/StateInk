export interface RecognitionGeometry { x: number; y: number; width: number; height: number }
export interface RecognizedState { id: string; name: string; geometry: RecognitionGeometry; confidence: number; initial: boolean; final: boolean }
export interface RecognizedTransition { id: string; from: string; to: string; event: string; geometry: RecognitionGeometry; confidence: number; direction_confirmed: boolean }
export interface RecognitionResult { states: RecognizedState[]; transitions: RecognizedTransition[]; warnings: string[]; processing_ms: number }
