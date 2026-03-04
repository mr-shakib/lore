"use client";

import { useEffect } from "react";

/**
 * Silently calls /api/bootstrap on first dashboard load.
 * This ensures the Clerk user has a corresponding row in the `users` table
 * and a workspace_id assigned, which is required before any API key operations.
 * Safe to call multiple times — idempotent on the server side.
 */
export default function BootstrapOnMount() {
  useEffect(() => {
    const key = "lore_bootstrapped";
    if (sessionStorage.getItem(key)) return;

    fetch("/api/bootstrap", { method: "GET" })
      .then(res => {
        if (res.ok) sessionStorage.setItem(key, "1");
      })
      .catch(() => {
        // Non-fatal — user can still use the dashboard, creation might fail
        // until they reload after the backend recovers.
      });
  }, []);

  return null;
}
