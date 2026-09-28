import path from "node:path";
import os from "node:os";

export function isServerMode(): boolean {
  return process.env.MICRO_EVAL_SERVER_MODE === "true";
}

export function getServerDataRoot(): string {
  return process.env.MICRO_EVAL_DATA_ROOT || path.join(os.homedir(), ".micro-eval-server");
}
