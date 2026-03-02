import { auth } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const BASE_URL = process.env.LORE_API_URL ?? "https://lore-m0st.onrender.com";

export async function GET() {
  const { getToken } = await auth();
  const token = await getToken();

  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 });
  }

  const res = await fetch(`${BASE_URL}/v1/auth/bootstrap`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    return NextResponse.json({ error: text, status: res.status }, { status: res.status });
  }

  const data = await res.json();
  return NextResponse.json(data);
}
