import { NextResponse } from "next/server";
import { getCell } from "@/lib/api";

interface RouteContext {
  params: Promise<{ id: string; cellId: string }>;
}

export async function GET(_request: Request, context: RouteContext) {
  const { id, cellId } = await context.params;
  const cell = await getCell(id, decodeURIComponent(cellId));
  if (!cell) return NextResponse.json({ error: "cell not found" }, { status: 404 });
  return NextResponse.json(cell);
}
