/** Local authority for retained UI work; never an authentication oracle. */
import { useEffect, useRef, useSyncExternalStore } from "react";

let epoch = 0;
let notice = "";
const listeners = new Set<() => void>();
export const sessionEpoch = () => epoch;
export const subscribeSession = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export function invalidateWork() {
  epoch++;
  for (const listener of listeners) listener();
}
export const useSessionEpoch = () =>
  useSyncExternalStore(subscribeSession, sessionEpoch);
export function assertCurrent(expected: number) {
  if (expected !== epoch) throw new Error("Sessão ou navegação alterada.");
}
export function setAuthNotice(message: string) {
  notice = message;
}
export function getAuthNotice() {
  return notice;
}

/** Every asynchronous screen continuation must still belong to this mount/epoch. */
export function useWorkGuard() {
  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return () => {
    const expected = epoch;
    return () => {
      assertCurrent(expected);
      if (!mounted.current) throw new Error("Navegação alterada.");
    };
  };
}
