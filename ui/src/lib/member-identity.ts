// Single source for the member identity stored in the browser.
// Server-mode write APIs require this value in the X-Micro-Eval-Member header.
export const MEMBER_NAME_KEY = "micro-eval:member-name";

export function getMemberName(): string {
  if (typeof window === "undefined") return "";
  return (window.localStorage.getItem(MEMBER_NAME_KEY) ?? "").trim();
}

export function setMemberName(name: string): void {
  if (typeof window === "undefined") return;
  const trimmed = name.trim();
  if (trimmed) window.localStorage.setItem(MEMBER_NAME_KEY, trimmed);
  else window.localStorage.removeItem(MEMBER_NAME_KEY);
}
