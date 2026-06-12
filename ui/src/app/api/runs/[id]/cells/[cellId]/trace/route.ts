import { NextResponse } from "next/server";
import { getCellTrace } from "@/lib/api";

interface RouteContext {
  params: Promise<{ id: string; cellId: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { id, cellId } = await context.params;
  const traces = await getCellTrace(id, decodeURIComponent(cellId));
  return NextResponse.json(traces);
}
