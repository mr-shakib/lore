import { getApiKeys, createApiKey, deleteApiKey } from "@/lib/api";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import ApiKeysClientPage from "./_client";

export const dynamic = "force-dynamic";

async function handleFormAction(formData: FormData) {
  "use server";
  const action = formData.get("_action") as string;

  if (action === "create") {
    const name   = formData.get("name") as string;
    const scopes = ((formData.get("scopes") as string) ?? "read,write").split(",").map(s => s.trim());
    await createApiKey(name, scopes);
    revalidatePath("/dashboard/api-keys");
  }

  if (action === "delete") {
    const id = formData.get("id") as string;
    await deleteApiKey(id);
    revalidatePath("/dashboard/api-keys");
  }
}

export default async function ApiKeysPage() {
  let keys: Awaited<ReturnType<typeof getApiKeys>>["api_keys"] = [];
  try {
    const res = await getApiKeys();
    keys = res.api_keys;
  } catch { /* empty */ }

  return (
    <form action={handleFormAction}>
      <ApiKeysClientPage data={{ keys }} />
    </form>
  );
}
