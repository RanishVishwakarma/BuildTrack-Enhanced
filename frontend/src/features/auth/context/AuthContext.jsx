/* eslint-disable react-refresh/only-export-components */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { clearStoredSession, getStoredToken, getStoredUser, persistSession } from "../services/session.js";
import * as authService from "../services/authService.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => getStoredUser());
  const [token, setToken] = useState(() => getStoredToken());
  // True until the stored session has been refreshed from /auth/me, so route
  // guards do not deny a page using a stale or permission-less profile.
  const [profilePending, setProfilePending] = useState(() => Boolean(getStoredToken()));

  useEffect(() => {
    const handleExpired = () => {
      setUser(null);
      setToken(null);
      toast.error("Your session expired. Please sign in again.");
    };
    window.addEventListener("buildtrack:session-expired", handleExpired);
    return () => window.removeEventListener("buildtrack:session-expired", handleExpired);
  }, []);

  // Refresh the stored profile once per session so the role and permissions an
  // administrator changed (or a session saved before permissions existed)
  // are current. The backend still checks every request itself.
  useEffect(() => {
    if (!token) {
      setProfilePending(false);
      return undefined;
    }
    let cancelled = false;
    authService
      .getCurrentUser(getStoredUser()?.workerId)
      .then((fresh) => {
        if (cancelled) return;
        persistSession(token, fresh);
        setUser(fresh);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setProfilePending(false);
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const signIn = useCallback(async (payload) => {
    const session = await authService.login(payload);
    persistSession(session.token, session.user);
    setToken(session.token);
    setUser(session.user);
    return session;
  }, []);

  const signUp = useCallback(async (payload) => {
    const session = await authService.register(payload);
    if (session.pending) return session;
    persistSession(session.token, session.user);
    setToken(session.token);
    setUser(session.user);
    return session;
  }, []);

  const signOut = useCallback(() => {
    clearStoredSession();
    setToken(null);
    setUser(null);
  }, []);

  // Applies profile changes returned by the backend to the active session.
  const updateSessionUser = useCallback((changes, nextToken) => {
    setUser((current) => {
      const merged = { ...current, ...changes };
      persistSession(nextToken || getStoredToken(), merged);
      return merged;
    });
    if (nextToken) setToken(nextToken);
  }, []);

  const value = useMemo(
    () => ({
      user,
      token,
      isAuthenticated: Boolean(token),
      profilePending,
      signIn,
      signUp,
      signOut,
      updateSessionUser,
      hasRole: (roles = []) => Boolean(user?.role && roles.includes(user.role)),
    }),
    [profilePending, signIn, signOut, signUp, token, updateSessionUser, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}
