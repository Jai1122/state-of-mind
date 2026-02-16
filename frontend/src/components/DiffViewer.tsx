import type { StateDiff } from "../types";

interface Props {
  diff: StateDiff;
}

export function DiffViewer({ diff }: Props) {
  const totalChanges =
    diff.changed.length + diff.added.length + diff.removed.length;

  if (totalChanges === 0) {
    return (
      <div className="rounded-lg border border-surface-3 bg-surface-1 p-6 text-center text-sm text-gray-500">
        No state changes in this step
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="flex items-center gap-4 text-xs text-gray-400">
        {diff.changed.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-accent-yellow" />
            {diff.changed.length} changed
          </span>
        )}
        {diff.added.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-accent-green" />
            {diff.added.length} added
          </span>
        )}
        {diff.removed.length > 0 && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-2 w-2 rounded-full bg-accent-red" />
            {diff.removed.length} removed
          </span>
        )}
      </div>

      {/* Changed entries */}
      {diff.changed.map((entry, i) => (
        <div key={`c-${i}`} className="diff-changed rounded-lg bg-surface-1 p-3">
          <div className="mb-1 font-mono text-xs font-semibold text-accent-yellow">
            {entry.path}
          </div>
          <div className="flex items-start gap-2 font-mono text-xs">
            <div className="flex-1">
              <span className="mr-1 text-gray-500">-</span>
              <InlineValue value={entry.old_value} className="text-accent-red" />
            </div>
            <div className="flex-1">
              <span className="mr-1 text-gray-500">+</span>
              <InlineValue
                value={entry.new_value}
                className="text-accent-green"
              />
            </div>
          </div>
        </div>
      ))}

      {/* Added entries */}
      {diff.added.map((entry, i) => (
        <div key={`a-${i}`} className="diff-added rounded-lg bg-surface-1 p-3">
          <div className="mb-1 font-mono text-xs font-semibold text-accent-green">
            + {entry.path}
          </div>
          <div className="font-mono text-xs">
            <InlineValue value={entry.value} className="text-gray-300" />
          </div>
        </div>
      ))}

      {/* Removed entries */}
      {diff.removed.map((entry, i) => (
        <div
          key={`r-${i}`}
          className="diff-removed rounded-lg bg-surface-1 p-3"
        >
          <div className="mb-1 font-mono text-xs font-semibold text-accent-red">
            - {entry.path}
          </div>
          <div className="font-mono text-xs">
            <InlineValue value={entry.value} className="text-gray-500 line-through" />
          </div>
        </div>
      ))}
    </div>
  );
}

function InlineValue({
  value,
  className = "",
}: {
  value: unknown;
  className?: string;
}) {
  if (value === null || value === undefined) {
    return <span className={`${className} italic`}>null</span>;
  }

  if (typeof value === "object") {
    const str = JSON.stringify(value, null, 2);
    // Show inline if short, otherwise as a block.
    if (str.length < 80) {
      return <span className={className}>{str}</span>;
    }
    return (
      <pre className={`mt-1 max-h-32 overflow-auto rounded bg-surface-0 p-2 ${className}`}>
        {str}
      </pre>
    );
  }

  return <span className={className}>{String(value)}</span>;
}
