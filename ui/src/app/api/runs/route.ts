import { NextResponse } from "next/server";
import { listRuns } from "@/lib/api";

export async function GET() {
  const runs = await listRuns();
  return NextResponse.json(runs);
}
