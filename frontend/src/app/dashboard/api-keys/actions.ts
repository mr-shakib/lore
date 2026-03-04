"use server";

import { auth } from "@clerk/nextjs/server";
import { revalidatePath } from "next/cache";

const BASE_URL = process.env.LORE_API_URL ?? "https://lore-m0st.onrender.com";

async function getAuthToken(): Promise<string | null> {
  const { getToken } = await auth();
  return getToken();
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CreatedKey {
  id: string;
  name: string;
  plaintext: string;
  workspace_id: string;
  scopes: string[];
  created_at: string;
}

export interface CreateKeyState {
  created?: CreatedKey;
  error?: string;
}

// ── Actions ───────────────────────────────────────────────────────────────────

/**
 * Create a new API key. Uses useActionState so the plaintext key is
 * returned to the client component and can be shown exactly once.
 */
export async function createKeyAction(
  _prev: CreateKeyState | null,
  formData: FormData,
): Promise<CreateKeyState> {
  const name = (formData.get("name") as string | null)?.trim();
  if (!name) return { error: "Key name is required." };

  const scopeStr = (formData.get("scopes") as string) ?? "read,write";
  const scopes = scopeStr.split(",").map((s) => s.trim()).filter(Boolean);

  const token = await getAuthToken();
  if (!token) return { error: "Not authenticated." };

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/v1/auth/api-keys`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ name, scopes }),
      cache: "no-store",
    });
  } catch {
    return { error: "Could not reach the API. Check LORE_API_URL." };
  }

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    return { error: `API error ${res.status}: ${text}` };
  }

  // Backend returns: { id, name, key, scopes, workspace_id, created_at, expires_at }
  const data = await res.json();

  revalidatePath("/dashboard/api-keys");

  return {
    created: {
      id: data.id,
      name: data.name,
      plaintext: data.key,           // backend field is 'key', not 'plaintext_key'
      workspace_id: data.workspace_id,
      scopes: data.scopes ?? scopes,
      created_at: data.created_at,
    },
  };
}

/**
 * Delete (revoke) an API key by ID.
 */
export async function deleteKeyAction(formData: FormData): Promise<void> {
  const id = formData.get("id") as string | null;
  if (!id) return;

  const token = await getAuthToken();
  if (!token) return;

  await fetch(`${BASE_URL}/v1/auth/api-keys/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
  }).catch(() => null);

  revalidatePath("/dashboard/api-keys");
}
