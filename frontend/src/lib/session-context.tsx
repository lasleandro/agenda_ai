"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { fetchSession, type SessionUser } from "./auth";

const STORAGE_KEY = "agenda:session";

type SessionState = {
  /** Last-known identity. Seeded from sessionStorage, then reconciled. */
  user: SessionUser | null;
  /** True until the authoritative /api/auth/me response has come back. */
  loading: boolean;
};

const SessionContext = createContext<SessionState>({ user: null, loading: true });

function readCachedSession(): SessionUser | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as SessionUser) : null;
  } catch {
    return null;
  }
}

function writeCachedSession(user: SessionUser | null): void {
  try {
    if (user) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(user));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode or storage disabled — reconcile still works, just no seed */
  }
}

/**
 * Fetches the session once for the whole protected area and shares it via
 * context. On mount it seeds `user` from sessionStorage so feature-gated nav
 * renders correctly on the first paint (optimistic UI), then reconciles
 * against /api/auth/me and rolls back if anything changed.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Seed from the previous visit before the network settles. sessionStorage
    // is client-only, so this must happen on mount rather than in the
    // initializer to keep server and client markup in sync.
    const cached = readCachedSession();
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-shot hydrate from persisted session
    if (cached) setUser(cached);

    let active = true;
    fetchSession().then((fresh) => {
      if (!active) return;
      setUser(fresh);
      setLoading(false);
      writeCachedSession(fresh);
    });
    return () => {
      active = false;
    };
  }, []);

  return (
    <SessionContext.Provider value={{ user, loading }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionState {
  return useContext(SessionContext);
}
