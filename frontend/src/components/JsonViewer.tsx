import { useState } from "react";

interface Props {
  data: unknown;
  /** Dotted paths to highlight as changed. */
  highlightPaths?: Set<string>;
  /** Current path prefix (used recursively). */
  _path?: string;
  /** Nesting depth for indentation. */
  _depth?: number;
}

const MAX_DEPTH = 20;
const MAX_INLINE_LEN = 60;

export function JsonViewer({
  data,
  highlightPaths,
  _path = "",
  _depth = 0,
}: Props) {
  if (_depth > MAX_DEPTH) {
    return <span className="text-gray-500">...</span>;
  }

  if (data === null || data === undefined) {
    return <span className="text-accent-purple">null</span>;
  }

  if (typeof data === "boolean") {
    return (
      <span className="text-accent-yellow">{data ? "true" : "false"}</span>
    );
  }

  if (typeof data === "number") {
    return <span className="text-accent-blue">{data}</span>;
  }

  if (typeof data === "string") {
    // Truncate very long strings.
    const display = data.length > 200 ? data.slice(0, 200) + "..." : data;
    return <span className="text-accent-green">"{display}"</span>;
  }

  if (Array.isArray(data)) {
    return (
      <CollapsibleArray
        data={data}
        highlightPaths={highlightPaths}
        path={_path}
        depth={_depth}
      />
    );
  }

  if (typeof data === "object") {
    return (
      <CollapsibleObject
        data={data as Record<string, unknown>}
        highlightPaths={highlightPaths}
        path={_path}
        depth={_depth}
      />
    );
  }

  return <span className="text-gray-400">{String(data)}</span>;
}

function CollapsibleObject({
  data,
  highlightPaths,
  path,
  depth,
}: {
  data: Record<string, unknown>;
  highlightPaths?: Set<string>;
  path: string;
  depth: number;
}) {
  const keys = Object.keys(data);
  const [collapsed, setCollapsed] = useState(depth > 2);

  // Check if any highlighted path is under this object.
  const hasHighlight = highlightPaths
    ? [...highlightPaths].some((p) => p === path || p.startsWith(path + "."))
    : false;

  // Inline short objects.
  const inlineStr = JSON.stringify(data);
  if (inlineStr.length < MAX_INLINE_LEN && keys.length <= 3) {
    return (
      <span
        className={`font-mono text-xs ${hasHighlight ? "bg-accent-yellow/10 rounded px-0.5" : ""}`}
      >
        {inlineStr}
      </span>
    );
  }

  if (collapsed) {
    return (
      <span>
        <button
          onClick={() => setCollapsed(false)}
          className="text-gray-500 hover:text-gray-300"
        >
          {"{ "}
          <span className="text-xs text-gray-600">{keys.length} keys</span>
          {" }"}
        </button>
        {hasHighlight && (
          <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-accent-yellow" />
        )}
      </span>
    );
  }

  return (
    <div className="font-mono text-xs">
      <button
        onClick={() => setCollapsed(true)}
        className="text-gray-500 hover:text-gray-300"
      >
        {"{"}
      </button>
      <div className="ml-4 border-l border-surface-3 pl-2">
        {keys.map((key) => {
          const childPath = path ? `${path}.${key}` : key;
          const isHighlighted = highlightPaths?.has(childPath);
          return (
            <div
              key={key}
              className={`py-0.5 ${isHighlighted ? "diff-changed pl-1" : ""}`}
            >
              <span className="text-accent-purple">{key}</span>
              <span className="text-gray-500">: </span>
              <JsonViewer
                data={data[key]}
                highlightPaths={highlightPaths}
                _path={childPath}
                _depth={depth + 1}
              />
            </div>
          );
        })}
      </div>
      <span className="text-gray-500">{"}"}</span>
    </div>
  );
}

function CollapsibleArray({
  data,
  highlightPaths,
  path,
  depth,
}: {
  data: unknown[];
  highlightPaths?: Set<string>;
  path: string;
  depth: number;
}) {
  const [collapsed, setCollapsed] = useState(depth > 2 || data.length > 10);

  if (collapsed) {
    return (
      <span>
        <button
          onClick={() => setCollapsed(false)}
          className="text-gray-500 hover:text-gray-300"
        >
          {"[ "}
          <span className="text-xs text-gray-600">{data.length} items</span>
          {" ]"}
        </button>
      </span>
    );
  }

  return (
    <div className="font-mono text-xs">
      <button
        onClick={() => setCollapsed(true)}
        className="text-gray-500 hover:text-gray-300"
      >
        {"["}
      </button>
      <div className="ml-4 border-l border-surface-3 pl-2">
        {data.map((item, i) => {
          const childPath = `${path}[${i}]`;
          const isHighlighted = highlightPaths?.has(childPath);
          return (
            <div
              key={i}
              className={`py-0.5 ${isHighlighted ? "diff-changed pl-1" : ""}`}
            >
              <span className="mr-2 text-gray-600">{i}:</span>
              <JsonViewer
                data={item}
                highlightPaths={highlightPaths}
                _path={childPath}
                _depth={depth + 1}
              />
            </div>
          );
        })}
      </div>
      <span className="text-gray-500">{"]"}</span>
    </div>
  );
}
