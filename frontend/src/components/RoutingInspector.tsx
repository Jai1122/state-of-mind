import type { RoutingDecision } from "../types";

interface Props {
  decisions: RoutingDecision[];
  currentStep: number;
}

export function RoutingInspector({ decisions, currentStep: _currentStep }: Props) {
  if (decisions.length === 0) {
    return (
      <div className="rounded-lg border border-surface-3 bg-surface-1 p-6 text-center text-sm text-gray-500">
        No routing decisions captured for this execution.
        <br />
        <span className="text-xs text-gray-600">
          Conditional edges must be present in the graph to see routing data.
        </span>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
        Routing Decisions
      </h3>
      {decisions.map((decision, i) => (
        <div
          key={i}
          className="rounded-lg border border-surface-3 bg-surface-1 p-4"
        >
          {/* Edge visualization */}
          <div className="mb-3 flex items-center gap-2 text-sm">
            <span className="rounded bg-accent-blue/20 px-2 py-0.5 font-mono text-accent-blue">
              {decision.source_node}
            </span>
            <svg
              width="20"
              height="12"
              viewBox="0 0 20 12"
              className="text-gray-500"
            >
              <path
                d="M0 6h16M13 2l4 4-4 4"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              />
            </svg>
            <span className="rounded bg-accent-green/20 px-2 py-0.5 font-mono text-accent-green">
              {decision.target_node}
            </span>
          </div>

          {/* Condition */}
          {decision.condition_description && (
            <div className="mb-2">
              <span className="text-xs text-gray-500">Condition:</span>
              <pre className="mt-1 rounded bg-surface-0 p-2 font-mono text-xs text-gray-300">
                {decision.condition_description}
              </pre>
            </div>
          )}

          {/* Evaluated value */}
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500">Result:</span>
            <span className="font-mono text-xs text-accent-yellow">
              {JSON.stringify(decision.evaluated_value)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
