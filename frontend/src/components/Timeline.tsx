import type { ExecutionStep } from "../types";

interface Props {
  steps: ExecutionStep[];
  selectedStep: number;
  onSelectStep: (index: number) => void;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "border-accent-green bg-accent-green/20 text-accent-green",
  running: "border-accent-blue bg-accent-blue/20 text-accent-blue",
  failed: "border-accent-red bg-accent-red/20 text-accent-red",
};

const SELECTED =
  "ring-2 ring-accent-blue ring-offset-1 ring-offset-surface-0";

export function Timeline({ steps, selectedStep, onSelectStep }: Props) {
  return (
    <div className="flex items-center gap-1 overflow-x-auto border-b border-surface-3 bg-surface-1 px-4 py-3">
      {/* Start marker */}
      <div className="flex-shrink-0 rounded border border-gray-600 bg-surface-3 px-2 py-1 text-[10px] font-semibold uppercase text-gray-400">
        Start
      </div>

      {steps.map((step, i) => (
        <div key={step.step_id} className="flex items-center">
          {/* Connector line */}
          <div className="h-px w-4 bg-gray-600" />

          {/* Node */}
          <button
            onClick={() => onSelectStep(i)}
            className={`flex-shrink-0 rounded border px-3 py-1.5 text-xs font-medium transition-all ${
              STATUS_COLORS[step.status] ?? "border-gray-600 text-gray-400"
            } ${i === selectedStep ? SELECTED : "hover:brightness-125"}`}
            title={`Step ${i}: ${step.node_name}${step.error ? ` (error: ${step.error})` : ""}`}
          >
            {step.node_name}
          </button>
        </div>
      ))}

      {/* End marker */}
      {steps.length > 0 && (
        <>
          <div className="h-px w-4 bg-gray-600" />
          <div className="flex-shrink-0 rounded border border-gray-600 bg-surface-3 px-2 py-1 text-[10px] font-semibold uppercase text-gray-400">
            End
          </div>
        </>
      )}
    </div>
  );
}
