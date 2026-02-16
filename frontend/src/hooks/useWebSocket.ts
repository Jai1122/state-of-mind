/** Hook for live WebSocket updates from the debug server. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { LiveEvent } from "../types";

export function useWebSocket(onEvent: (event: LiveEvent) => void) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/live`);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => {
      setConnected(false);
      // Reconnect after 2 seconds.
      setTimeout(connect, 2000);
    };
    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data) as LiveEvent;
        onEventRef.current(parsed);
      } catch {
        // Ignore malformed messages.
      }
    };

    wsRef.current = ws;
  }, []);

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
    };
  }, [connect]);

  return { connected };
}
