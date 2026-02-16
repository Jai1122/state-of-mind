/** Domain types matching the Python backend models. */

export interface Execution {
  execution_id: string;
  graph_name: string;
  started_at: string;
  ended_at: string | null;
  status: "running" | "completed" | "failed";
  initial_state: Record<string, unknown>;
  final_state: Record<string, unknown> | null;
  step_count: number;
  metadata: Record<string, unknown>;
}

export interface DiffEntry {
  path: string;
  value?: unknown;
  old_value?: unknown;
  new_value?: unknown;
}

export interface StateDiff {
  changed: DiffEntry[];
  added: DiffEntry[];
  removed: DiffEntry[];
}

export interface ExecutionStep {
  step_id: string;
  execution_id: string;
  node_name: string;
  step_index: number;
  timestamp_start: string;
  timestamp_end: string | null;
  status: "running" | "completed" | "failed";
  state_before: Record<string, unknown> | null;
  state_after: Record<string, unknown> | null;
  state_diff: StateDiff;
  is_checkpoint: boolean;
  error: string | null;
  metadata: Record<string, unknown>;
}

export interface TimelineEntry {
  step_index: number;
  node_name: string;
  state: Record<string, unknown>;
  diff: StateDiff;
  timestamp_start: string;
  timestamp_end: string | null;
  status: "running" | "completed" | "failed";
  error: string | null;
}

export interface RoutingDecision {
  step_id: string;
  source_node: string;
  target_node: string;
  condition_description: string;
  condition_inputs: Record<string, unknown>;
  evaluated_value: unknown;
}

export interface StepComparison {
  step_a: number;
  step_b: number;
  state_a: Record<string, unknown>;
  state_b: Record<string, unknown>;
  diff: StateDiff;
}

/** WebSocket event from the live feed. */
export interface LiveEvent {
  type:
    | "execution_started"
    | "execution_ended"
    | "step_recorded"
    | "routing_decision";
  data: Record<string, unknown>;
}
