// Keeps the business up to date: reads it now and then every few seconds. A failed read keeps
// the last data on screen and only flips `error`, so a short outage never empties the page.
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchOverview } from "../lib/api.js";

const POLL_MS = 5000;

export function useOverview(token) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [updatedAt, setUpdatedAt] = useState(null);
  const inFlight = useRef(null);

  const accept = useCallback(overview => {
    setData(overview);
    setError(null);
    setUpdatedAt(Date.now());
  }, []);

  const refresh = useCallback(async () => {
    inFlight.current?.abort();
    const controller = new AbortController();
    inFlight.current = controller;
    try {
      accept(await fetchOverview(token, controller.signal));
    } catch (failure) {
      if (failure.name !== "AbortError") setError(failure);
    }
  }, [token, accept]);

  useEffect(() => {
    setData(null);
    setError(null);
    refresh();
    const timer = setInterval(refresh, POLL_MS);
    return () => {
      clearInterval(timer);
      inFlight.current?.abort();
    };
  }, [refresh]);

  // `accept` lets a deploy put the node's answer on screen without waiting for the next poll.
  return { data, error, updatedAt, refresh, accept };
}
