"use client";
import { useCallback, useEffect, useState } from "react";

export class ApiError extends Error {}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the server. Check your connection and try again.");
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch { /* keep default */ }
    throw new ApiError(msg);
  }
  return res.json() as Promise<T>;
}

export function post<T>(path: string, body?: unknown): Promise<T> {
  return api<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
}

export function useApi<T>(path: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    try { setData(await api<T>(path)); setError(null); }
    catch (e) { setError(e instanceof Error ? e.message : "Unknown error"); }
    finally { setLoading(false); }
  }, [path]);
  useEffect(() => { void load(); }, [load]);
  return { data, error, loading, reload: load, setData };
}

const KEY = "oneman.actor";
export function getActor(): string {
  try { return localStorage.getItem(KEY) || "demo.approver"; } catch { return "demo.approver"; }
}
export function setActor(v: string) { try { localStorage.setItem(KEY, v); } catch { /* ignore */ } }
