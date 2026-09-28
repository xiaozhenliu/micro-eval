/**
 * Stable refusal reason identifiers and the fixed hints the API routes may
 * attach for them. Client-safe: no Node built-ins. A route only ever echoes
 * its own constant for a known reason — an arbitrary `hint` coming from a
 * backend process is never forwarded (GRO-972).
 */
export const INVALID_GIT_REF_REASON = "invalid_git_ref";

export const INVALID_GIT_REF_HINT =
  "Use a branch, tag, or commit SHA that exists in the server repository and resolves to a commit. Correct the ref or fetch the required commit, then preview again.";
