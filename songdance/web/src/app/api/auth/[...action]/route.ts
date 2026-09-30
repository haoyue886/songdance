import { type NextRequest } from "next/server";
import { handleAuth } from "@/lib/auth/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
type Context = { params: Promise<{ action: string[] }> };
export async function POST(request: NextRequest, context: Context) {
  return handleAuth(request, (await context.params).action.join("/"));
}
export async function GET(request: NextRequest, context: Context) {
  return handleAuth(request, (await context.params).action.join("/"));
}
