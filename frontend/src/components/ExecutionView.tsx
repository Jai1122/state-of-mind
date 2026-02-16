import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ExecutionStep, RoutingDecision, TimelineEntry } from "../types";
import { DiffViewer } from "./DiffViewer";
import { JsonViewer } from "./JsonViewer";
import { ReplaySlider } from "./ReplaySlider";
import { RoutingInspector } from "./RoutingInspector";
import { Timeline } from "./Timeline";

interface Props {
  executionId: string;
}

type Tab = "state" | "diff" | "routing";

export function ExecutionView({ executionId }: Props) {
  const [steps, setSteps] = useState<ExecutionStep[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [routing, setRouting] = useState<RoutingDecision[]>([]);
  const [selectedStep, setSelectedStep] = useState<number>(0);
  const [activeTab, setActiveTab] = useState<Tab>("diff");
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [stepsData, timelineData, routingData] = await Promise.all([
        api.getSteps(executionId),
        api.getTimeline(executionId),
        api.getRouting(executionId),
      ]);
      setSteps(stepsData);
      setTimeline(timelineData);
      setRouting(routingData);
      setSelectedStep(0);
    } catch (err) {
      console.error("Failed to load execution data:", err);
    } finally {
      setLoading(false);
    }
  }, [executionId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Keyboard navigation.
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft" || e.key === "k") {
        setSelectedStep((s) => Math.max(0, s - 1));
      } else if (e.key === "ArrowRight" || e.key === "j") {
        setSelectedStep((s) => Math.min(steps.length - 1, s + 1));
      } else if (e.key === "1") {
        setActiveTab("diff");
      } else if (e.key === "2") {
        setActiveTab("state");
      } else if (e.key === "3") {
        setActiveTab("routing");
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [steps.length]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center text-gray-500">
        Loading execution data...
      </div>
    );
  }

  const currentStep = steps[selectedStep];
  const currentTimeline = timeline[selectedStep];

  return (
    <div className="flex h-full flex-col">
      {/* Execution timeline (horizontal) */}
      <Timeline
        steps={steps}
        selectedStep={selectedStep}
        onSelectStep={setSelectedStep}
      />

      {/* Replay slider */}
      <ReplaySlider
        stepCount={steps.length}
        currentStep={selectedStep}
        onStepChange={setSelectedStep}
      />

      {/* Tab bar */}
      <div className="flex border-b border-surface-3 bg-surface-1">
        {(["diff", "state", "routing"] as Tab[]).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab
                ? "border-b-2 border-accent-blue text-white"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab === "diff"
              ? "Diff"
              : tab === "state"
                ? "State"
                : "Routing"}
            <kbd className="ml-2 rounded bg-surface-3 px-1 py-0.5 text-[10px] text-gray-500">
              {tab === "diff" ? "1" : tab === "state" ? "2" : "3"}
            </kbd>
          </button>
        ))}
        {currentStep && (
          <div className="ml-auto flex items-center gap-2 px-4 text-xs text-gray-500">
            <span>
              Step {selectedStep + 1}/{steps.length}
            </span>
            <span className="font-mono text-accent-blue">
              {currentStep.node_name}
            </span>
            {currentStep.error && (
              <span className="text-accent-red">ERROR</span>
            )}
          </div>
        )}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-4">
        {activeTab === "diff" && currentStep && (
          <DiffViewer diff={currentStep.state_diff} />
        )}

        {activeTab === "state" && currentTimeline && currentStep && (
          <div className="grid grid-cols-2 gap-4">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                State Before
              </h3>
              <div className="rounded-lg border border-surface-3 bg-surface-1 p-3">
                <JsonViewer
                  data={
                    selectedStep > 0
                      ? (timeline[selectedStep - 1]?.state ?? {})
                      : {}
                  }
                />
              </div>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-400">
                State After
              </h3>
              <div className="rounded-lg border border-surface-3 bg-surface-1 p-3">
                <JsonViewer
                  data={currentTimeline.state}
                  highlightPaths={getChangedPaths(currentStep.state_diff)}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === "routing" && (
          <RoutingInspector decisions={routing} currentStep={selectedStep} />
        )}
      </div>
    </div>
  );
}

/** Extract all paths that changed in a diff — used to highlight in the JSON viewer. */
function getChangedPaths(diff: ExecutionStep["state_diff"]): Set<string> {
  const paths = new Set<string>();
  for (const entry of diff.changed) {
    paths.add(entry.path);
  }
  for (const entry of diff.added) {
    paths.add(entry.path);
  }
  return paths;
}
