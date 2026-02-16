/** API client for the lgdebug backend. */

import type {
  Execution,
  ExecutionStep,
  RoutingDecision,
  StepComparison,
  TimelineEntry,
} from "../types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listExecutions: (limit = 50, offset = 0) =>
    get<Execution[]>(`/executions?limit=${limit}&offset=${offset}`),

  getExecution: (id: string) => get<Execution>(`/executions/${id}`),

  getSteps: (id: string) => get<ExecutionStep[]>(`/executions/${id}/steps`),

  getStateAtStep: (id: string, stepIndex: number) =>
    get<{ execution_id: string; step_index: number; state: Record<string, unknown> }>(
      `/executions/${id}/state/${stepIndex}`
    ),

  getTimeline: (id: string) =>
    get<TimelineEntry[]>(`/executions/${id}/timeline`),

  getRouting: (id: string) =>
    get<RoutingDecision[]>(`/executions/${id}/routing`),

  compareSteps: (id: string, stepA: number, stepB: number) =>
    get<StepComparison>(
      `/executions/${id}/compare?step_a=${stepA}&step_b=${stepB}`
    ),
};
