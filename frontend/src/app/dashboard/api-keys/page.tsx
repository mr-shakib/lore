import { getApiKeys, type ApiKey } from "@/lib/api";
import ApiKeysClientPage from "./_client";
import { deleteKeyAction } from "./actions";

export const dynamic = "force-dynamic";

export default async function ApiKeysPage() {
  let keys: ApiKey[] = [];
  try {
    const res = await getApiKeys();
    keys = res.keys ?? [];
  } catch { /* show empty state */ }

  // Derive workspace_id from any existing key (all share the same workspace)
  const workspaceId = keys[0]?.workspace_id ?? null;

  return (
    <ApiKeysClientPage
      initialKeys={keys}
      workspaceId={workspaceId}
      deleteAction={deleteKeyAction}
    />
  );
}
