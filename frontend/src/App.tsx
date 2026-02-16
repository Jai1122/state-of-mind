import { useCallback, useEffect, useState } from "react";
import { ExecutionList } from "./components/ExecutionList";
import { ExecutionView } from "./components/ExecutionView";
import { useWebSocket } from "./hooks/useWebSocket";
import { api } from "./lib/api";
import type { Execution, LiveEvent } from "./types";

export function App() {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const loadExecutions = useCallback(async () => {
    try {
      const data = await api.listExecutions();
      setExecutions(data);
    } catch {
      // Server may not be running yet.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadExecutions();
  }, [loadExecutions]);

  // Live updates via WebSocket.
  const handleLiveEvent = useCallback(
    (event: LiveEvent) => {
      if (
        event.type === "execution_started" ||
        event.type === "execution_ended"
      ) {
        void loadExecutions();
      }
    },
    [loadExecutions]
  );

  const { connected } = useWebSocket(handleLiveEvent);

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-surface-3 bg-surface-1 px-4 py-2">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold text-white">lgdebug</h1>
          <span className="text-xs text-gray-500">
            LangGraph State Debugger
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              connected ? "bg-accent-green" : "bg-accent-red"
            }`}
            title={connected ? "Connected" : "Disconnected"}
          />
          <span className="text-xs text-gray-500">
            {connected ? "Live" : "Offline"}
          </span>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar: execution list */}
        <aside className="w-72 flex-shrink-0 overflow-y-auto border-r border-surface-3 bg-surface-1">
          <ExecutionList
            executions={executions}
            selectedId={selectedId}
            onSelect={setSelectedId}
            loading={loading}
          />
        </aside>

        {/* Main panel: execution detail view */}
        <main className="flex-1 overflow-hidden">
          {selectedId ? (
            <ExecutionView executionId={selectedId} />
          ) : (
            <div className="flex h-full items-center justify-center text-gray-500">
              <div className="text-center">
                <p className="text-lg">Select an execution to inspect</p>
                <p className="mt-1 text-sm">
                  {executions.length === 0 && !loading
                    ? "No executions recorded yet. Run your LangGraph app with debugging enabled."
                    : `${executions.length} execution${executions.length !== 1 ? "s" : ""} available`}
                </p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
