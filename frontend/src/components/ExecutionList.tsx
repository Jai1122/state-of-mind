import type { Execution } from "../types";

interface Props {
  executions: Execution[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
}

const STATUS_COLORS: Record<string, string> = {
  completed: "bg-accent-green",
  running: "bg-accent-blue",
  failed: "bg-accent-red",
};

export function ExecutionList({
  executions,
  selectedId,
  onSelect,
  loading,
}: Props) {
  if (loading) {
    return (
      <div className="p-4 text-sm text-gray-500">Loading executions...</div>
    );
  }

  return (
    <div className="flex flex-col">
      <div className="border-b border-surface-3 px-4 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          Executions
        </h2>
      </div>
      {executions.map((ex) => (
        <button
          key={ex.execution_id}
          onClick={() => onSelect(ex.execution_id)}
          className={`flex flex-col gap-1 border-b border-surface-3 px-4 py-3 text-left transition-colors hover:bg-surface-2 ${
            selectedId === ex.execution_id
              ? "border-l-2 border-l-accent-blue bg-surface-2"
              : ""
          }`}
        >
          <div className="flex items-center gap-2">
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                STATUS_COLORS[ex.status] ?? "bg-gray-500"
              }`}
            />
            <span className="text-sm font-medium text-white">
              {ex.graph_name || "unnamed"}
            </span>
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span>{ex.step_count} steps</span>
            <span>{formatTime(ex.started_at)}</span>
          </div>
          <div className="font-mono text-xs text-gray-600">
            {ex.execution_id.slice(0, 12)}
          </div>
        </button>
      ))}
      {executions.length === 0 && (
        <div className="p-4 text-sm text-gray-600">
          No executions yet
        </div>
      )}
    </div>
  );
}

function formatTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}
