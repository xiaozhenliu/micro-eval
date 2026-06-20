---
title: "Global Project Registry & Multi-Project Dashboard"
date: 2026-06-15
status: draft
type: feature-spec
tags:
  - registry
  - ui
  - dashboard
  - v0.3.5
---

# Global Project Registry & Multi-Project Dashboard

## 1. Problem Statement

micro-eval stores run data in `<cwd>/.micro-eval/runs/`. The Web UI resolves a
single project root via `MICRO_EVAL_PROJECT_ROOT` or `process.cwd()/..` and
reads only that one directory. Consequences:

1. **Runs in different directories are invisible to the UI.** Running
   `micro-eval run` in `examples/agent-codefix-showdown/` and then launching
   `micro-eval ui` from the repo root shows "No runs yet."
2. **No cross-project overview.** A team evaluating multiple agents across
   separate project directories cannot see all results in one place.
3. **Workaround is fragile.** Setting `MICRO_EVAL_PROJECT_ROOT` per-launch
   only shifts the problem — you see one project at a time.

## 2. Design Goals

- One dashboard shows all registered projects and their runs.
- Zero data migration — run data stays in `<cwd>/.micro-eval/runs/` where it
  was written.
- Registration is automatic on `micro-eval run` and manual via
  `micro-eval register`.
- UI groups runs by project with a card-based landing page.
- Usage is documented in the VitePress guide (English + Chinese).

## 3. Non-Goals

- Centralized / relocated run storage.
- Cross-project comparison matrices (comparing runs from different projects in
  one matrix view).
- Remote / multi-machine registry sync.
- Authentication or multi-user access control.

---

## 4. Key Design Decision: Project Identity

### 4.1 The Problem

`project_name` is user-defined in `eval.yaml` and not unique — the same name
can appear in multiple directory checkouts. Using `project_name` alone as a
routing key causes collisions.

### 4.2 Decision: `project_key` = URL-safe slug derived from `realpath`

Each registered project gets a stable, unique `project_key`:

```python
import hashlib
from pathlib import Path

def project_key(project_path: Path) -> str:
    """Derive a stable URL-safe key from the resolved absolute path."""
    resolved = str(project_path.resolve())
    digest = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    # Use directory basename + hash suffix for human readability
    basename = project_path.resolve().name
    # Sanitize basename to URL-safe chars
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in basename)
    return f"{safe}-{digest}"
```

Example: `/Users/xz/Projects/micro-eval/examples/agent-codefix-showdown`
→ `agent-codefix-showdown-a3f7b2c1e9d0`

### 4.3 Where `project_key` Is Used

- **UI page routes**: `/project/[key]/...` (path segment, not query param)
- **API routes**: `/api/project/[key]/...` (path segment, not query param)
- **CLI output**: `micro-eval projects` shows both name and key
- **Registry storage**: stored alongside name and path

**Consistency rule**: `project_key` is always a URL path segment, never a
query parameter. This avoids ambiguity about whether `project` means key,
name, or path in different contexts.

### 4.4 Where `project_name` Is Still Used

- **Display**: UI cards, page headings, CLI output show the human-readable name
- **eval.yaml**: unchanged, still `project_name`
- **run.json**: unchanged, still `project_name`

---

## 5. Global Registry

### 5.1 File Location

```
~/.micro-eval/registry.json
```

The directory `~/.micro-eval/` is created on first write with mode `0o700`
(owner-only access to avoid leaking project paths to other local users).

### 5.2 Schema

```json
{
  "schema_version": "1.0",
  "projects": [
    {
      "key": "agent-codefix-showdown-a3f7b2c1e9d0",
      "name": "agent-codefix-showdown-mock",
      "path": "/absolute/path/to/project",
      "output_dir": ".micro-eval/runs",
      "registered_at": "2026-06-15T09:18:03Z",
      "last_run_at": "2026-06-15T09:18:03Z",
      "run_count": 3
    }
  ]
}
```

**Identity key**: `key` (derived from `realpath`, globally unique).
`run_count` is a hint updated on registration; the authoritative count comes
from scanning the runs directory at read time.

### 5.3 Schema Versioning

The `schema_version` is a **top-level field** on the registry object (not
per-entry). It governs the structure of the entire file. Rules:
- Current code reads `"1.0"` only. Unknown version → log warning, treat
  entire registry as empty (do not partially parse unknown structures).
- Future versions must be backward-compatible within the `"1.x"` series
  (add fields to entries, not remove).
- A breaking structural change bumps to `"2.0"` and the reader migrates
  the file in-place on first load.
- Extra/unknown fields within entries are preserved on read-modify-write
  (forward-compat for intermediate versions).

### 5.4 Python Module: `src/micro_eval/store/registry.py`

Public API:

```python
@dataclass
class ProjectEntry:
    key: str
    name: str
    path: Path
    output_dir: str
    registered_at: str
    last_run_at: str | None
    run_count: int

class ProjectRegistry:
    """Read/write ~/.micro-eval/registry.json with atomic file safety."""

    REGISTRY_DIR = Path.home() / ".micro-eval"
    REGISTRY_FILE = REGISTRY_DIR / "registry.json"
    LOCK_FILE = REGISTRY_DIR / "registry.lock"

    def register(self, name: str, path: Path, output_dir: str = ".micro-eval/runs") -> ProjectEntry: ...
    def unregister(self, *, key: str | None = None, path: Path | None = None) -> bool: ...
    def list_projects(self) -> list[ProjectEntry]: ...
    def update_last_run(self, path: Path) -> None: ...
    def find_by_key(self, key: str) -> ProjectEntry | None: ...
    def find_by_path(self, path: Path) -> ProjectEntry | None: ...
    def find_all_by_run_id(self, run_id: str) -> list[ProjectEntry]: ...
```

`find_all_by_run_id` returns a list (not a single entry) because run IDs can
theoretically collide across projects (§9.5). Callers must handle the
zero / one / many cases explicitly.

### 5.5 Atomic Write Protocol

Registry writes follow this sequence to prevent corruption:

1. Acquire exclusive lock on `~/.micro-eval/registry.lock` via `fcntl.flock`
   (Unix) / `msvcrt.locking` (Windows). The lock file is a separate file
   (not a symlink) to avoid symlink-based lock spoofing.
2. Read current `registry.json`.
3. Apply mutation.
4. Write to `registry.json.tmp` with `0o600` permissions.
5. `os.fsync()` the temp file descriptor.
6. `os.replace()` temp → `registry.json` (atomic on POSIX).
7. Release lock.

If step 1 fails (another process holds the lock), retry up to 3 times with
100ms backoff, then raise `RegistryLockError`.

### 5.6 Automatic Registration

`RunStore.finalize_run()` calls `ProjectRegistry.register()` after writing
`run.json`. The project name comes from `RunRecord.project_name`, the path
from `RunStore.project_root`. Registration is best-effort — failure to write
the registry does not fail the run.

### 5.7 Staleness Handling

When the UI reads a registered project, it checks that `<path>/<output_dir>/`
exists on disk. Outcomes:
- **Path exists**: normal display.
- **Path missing**: project card shows "path not found" badge, run list is
  empty, no error thrown.
- **Path exists but empty**: card shows "0 runs".

No auto-removal — the user must explicitly `micro-eval unregister`.

---

## 6. New CLI Commands

### 6.1 `micro-eval register [path]`

Register a project directory manually. Defaults to cwd. Scans for existing
`.micro-eval/runs/` and reads `project_name` from the most recent `run.json`
(or falls back to the directory basename). Also accepts `--name` to override.

```bash
# Register current directory
micro-eval register

# Register a specific path
micro-eval register /path/to/eval-project

# Register with explicit name
micro-eval register --name my-project /path/to/eval-project
```

If the path is already registered, update `name` (if `--name` provided) and
`last_run_at`. Print the project key.

### 6.2 `micro-eval unregister <key-or-path>`

Remove a project from the registry by its `project_key` or absolute path.
Does not delete any run data.

```bash
# By key (unambiguous)
micro-eval unregister agent-codefix-showdown-a3f7b2c1e9d0

# By path (resolved to key internally)
micro-eval unregister /path/to/eval-project
```

If the argument matches neither a key nor a path in the registry, print an
error with the list of registered projects.

### 6.3 `micro-eval projects`

List all registered projects with status.

```bash
micro-eval projects
```

Output:

```
                          Registered Projects
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Project                         ┃ Key             ┃ Runs ┃ Last Run       ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━┩
│ agent-codefix-showdown-mock     │ agent-cod...d0  │ 22   │ 3 min ago      │
│ multi-task-matrix-mock          │ multi-tas...e2  │ 1    │ 3 min ago      │
│ git-workspace-isolation-mock    │ git-works...b4  │ 2    │ 3 min ago      │
└─────────────────────────────────┴─────────────────┴──────┴────────────────┘
```

Use `--json` for machine-readable output (full key and path included).

---

## 7. UI Changes

### 7.1 UI Launch Strategy

**Problem**: `micro-eval ui` currently requires `<cwd>/ui/` to exist, meaning
it only works from the micro-eval source checkout.

**Context**: The wheel (`pyproject.toml`) only packages `src/micro_eval`. The
Next.js UI is not bundled into the wheel — it requires a source checkout and
`npm install`. This is by design for the MVP (source-checkout distribution).

**Solution**: `micro-eval ui` locates the UI directory via this priority:
1. `MICRO_EVAL_UI_DIR` environment variable (explicit override — allows
   pointing to a UI checkout from anywhere).
2. `<cwd>/ui/` (current behavior, works in source checkout).
3. `<git-repo-root>/ui/` (walk up from cwd looking for `.git/` to identify
   the repository root, then check if `<repo-root>/ui/` exists. This avoids
   false matches on unrelated `ui/` directories in parent paths).

If none found, print a clear error:
```
Error: UI directory not found.
  Set MICRO_EVAL_UI_DIR=/path/to/micro-eval/ui or run from the source checkout.
```

**Future**: When/if the UI is bundled into the wheel (e.g., as pre-built
static assets), add a `<package-install-dir>/ui/` lookup. This is out of
scope for v0.3.5.

### 7.2 Data Layer: `ui/src/lib/api.ts`

New functions:

```typescript
interface Registry {
  schema_version: string;
  projects: RegistryEntry[];
}

interface RegistryEntry {
  key: string;
  name: string;
  path: string;
  output_dir: string;
  registered_at: string;
  last_run_at: string | null;
  run_count: number;
}

// Read ~/.micro-eval/registry.json (returns empty registry if absent)
export function getRegistry(): Registry { ... }

// Aggregate project summaries from registry
export async function listAllProjects(): Promise<ProjectSummary[]> { ... }

// Resolve a project key to its disk path via registry lookup
export function resolveProjectPath(key: string): string | null { ... }

// List runs for a specific project (by key, resolved to path)
export async function listRunsByProject(key: string): Promise<Run[]> { ... }

// Project-scoped versions of existing functions
export async function getRunInProject(key: string, runId: string): Promise<Run | null> { ... }
export async function getCellInProject(key: string, runId: string, cellId: string): Promise<CellResult | null> { ... }
export async function getArtifactInProject(key: string, runId: string, artifactId: string): Promise<{artifact: ArtifactRef; content: string} | null> { ... }
export async function getCellTraceInProject(key: string, runId: string, cellId: string): Promise<TraceRef[]> { ... }
```

All project-scoped functions validate `key` against the registry before
resolving a path. Unknown keys return null / empty.

**Internal helper refactoring**: The existing `getRun()`, `getCell()`, etc.
are refactored to accept a `runsDir: string` parameter instead of calling
`getProjectRoot()` internally. The project-scoped wrappers call
`resolveProjectPath(key)` → `validateProjectPath()` → pass the validated
`runsDir` to the internal helper. `getProjectRoot()` is retained only as a
fallback for the single-project mode (§9.3 rows 1-2). Example:

```typescript
// Before (single-root):
export async function getRun(id: string): Promise<Run | null> {
  const filePath = path.join(getRunsDir(), safeId(id)!, "run.json");
  ...
}

// After (parameterized):
function getRunFromDir(runsDir: string, id: string): Run | null { ... }

export async function getRunInProject(key: string, runId: string) {
  const runsDir = resolveAndValidate(key);
  if (!runsDir) return null;
  return getRunFromDir(runsDir, runId);
}

// Legacy fallback (single-project mode):
export async function getRun(id: string) {
  return getRunFromDir(getRunsDir(), id);
}
```

### 7.3 Path Validation in Data Layer

Every path resolved from the registry goes through this check before any
filesystem read:

```typescript
function validateProjectPath(registryPath: string, outputDir: string): string | null {
  const resolved = path.resolve(registryPath);
  const runsDir = path.resolve(resolved, outputDir);
  // Ensure output_dir is relative and stays inside project
  if (!runsDir.startsWith(resolved + path.sep)) return null;
  // Resolve symlinks and re-check containment
  try {
    const realResolved = fs.realpathSync(resolved);
    const realRunsDir = fs.realpathSync(runsDir);
    if (!realRunsDir.startsWith(realResolved + path.sep)) return null;
    return realRunsDir;
  } catch {
    return null; // path doesn't exist
  }
}
```

### 7.4 New Type: `ProjectSummary`

```typescript
const ProjectSummarySchema = z.object({
  key: z.string(),
  name: z.string(),
  path: z.string(),
  output_dir: z.string(),
  run_count: z.number(),
  last_run_at: z.string().nullable(),
  accessible: z.boolean(),
  latest_verdict: z.string().nullable(),
});
type ProjectSummary = z.infer<typeof ProjectSummarySchema>;
```

`run_count` and `latest_verdict` are derived at read time by scanning the
actual runs directory (the registry's `run_count` is a hint, not authoritative).

### 7.5 Page Routing

| Route | Content |
|-------|---------|
| `/` | Project card grid (new landing page) |
| `/project/[key]` | Run list for a single project |
| `/project/[key]/run/[id]` | Run detail (existing components) |
| `/project/[key]/run/[id]/review` | Review page (existing components) |
| `/project/[key]/run/[id]/artifact/[artifactId]` | Artifact viewer (existing) |

All routes use `project_key` (not `project_name`) to avoid collisions.

### 7.6 Backward-Compatible Route Redirects

All old `/run/[id]` routes (including sub-routes) remain as redirect handlers:

| Old Route | Redirects To |
|-----------|-------------|
| `/run/[id]` | `/project/[key]/run/[id]` |
| `/run/[id]/review` | `/project/[key]/run/[id]/review` |
| `/run/[id]/artifact/[artifactId]` | `/project/[key]/run/[id]/artifact/[artifactId]` |

Redirect logic (shared by all old routes):

1. Read `~/.micro-eval/registry.json` directly from the TypeScript data layer
   (same as `getRegistry()` in §7.2 — the registry is a simple JSON file,
   no Python process needed).
2. For each registered project, check if `<path>/<output_dir>/<run_id>/`
   exists on disk. Collect all matches.
3. If exactly one match → redirect 308 to the project-scoped equivalent,
   preserving the sub-path.
4. If multiple matches → return a disambiguation page listing the matching
   projects with links to each.
5. If no match → 404.

**Implementation decision**: Use a **shared server component layout** in
`app/run/[id]/layout.tsx` (not middleware). Rationale:
- The redirect logic needs filesystem access (`fs.existsSync`) which is
  available in server components but restricted in Edge middleware.
- A shared layout at `app/run/[id]/layout.tsx` naturally covers all
  sub-routes (`/run/[id]`, `/run/[id]/review`, `/run/[id]/artifact/...`)
  without duplicating logic in each page.
- The layout calls `redirect()` from `next/navigation` before rendering
  children, achieving the same effect as middleware.

**Note**: The `find_all_by_run_id` method on Python's `ProjectRegistry` is
used by CLI commands and the Python evaluate subprocess. The Next.js redirect
logic performs the equivalent scan in TypeScript by reading `registry.json`
and checking directories — it does not call into Python. This avoids a
cross-process dependency for what is a simple JSON read + directory check.

### 7.7 Landing Page: Project Cards

The new `/` page shows a responsive card grid. Each card displays:

- **Project name** (as heading)
- **Project key** (small, muted text)
- **Path** (truncated, with tooltip for full path)
- **Run count** and **last run timestamp**
- **Latest decision verdict** badge (improved / regressed / inconclusive / ...)
- **Status indicator**: green dot if path accessible, red dot with
  "path not found" if stale

Cards are sorted by `last_run_at` descending (most recently active first).

Empty state (no projects registered and no fallback project):

```
No projects registered.

Run `micro-eval run` in any project directory to get started,
or use `micro-eval register <path>` to register an existing project.
```

### 7.8 Project Run List: `/project/[key]`

Same as the current run list (reuses `RunList` component), scoped to one project.
Header shows the project name, key, and path. A "Back to projects" breadcrumb
link at the top.

### 7.9 Component Updates

All components that generate internal links must use the project-scoped route
prefix. Affected components and their changes:

| Component | Current Link Pattern | New Link Pattern |
|-----------|---------------------|------------------|
| `RunList.tsx` | `href={/run/${run.id}}` | `href={/project/${key}/run/${run.id}}` |
| `CellDetail.tsx` | `href={/run/${run.id}/artifact/${id}}` | `href={/project/${key}/run/${run.id}/artifact/${id}}` |
| `MatrixHeatmap.tsx` | `href={/run/${runId}/review#...}` | `href={/project/${key}/run/${runId}/review#...}` |

These components receive `projectKey` as a new required prop.

`AnnotationPanel.tsx` does not generate navigation links, but its inner
`EvaluationForm` component constructs a `fetch()` URL to the evaluate API
(`/api/runs/${runId}/cells/${cellId}/evaluate`). Both `AnnotationPanel` and
its inner `EvaluationForm` must receive `projectKey` and use it in the fetch
URL: `/api/project/${projectKey}/runs/${runId}/cells/${cellId}/evaluate`.

**Components audited and confirmed unaffected** (no links, no API calls, no
routing logic — display-only):

| Component | Reason |
|-----------|--------|
| `ArtifactViewer.tsx` | Receives `artifact` + `content` as props, renders only. No fetch, no links. |
| `CostPanel.tsx` | Receives `decision` as prop, renders table. No fetch, no links. |
| `TraceViewer.tsx` | Receives `traces[]` as prop, renders list. No fetch, no links. |
| `CaveatBanner.tsx` | Receives `run` as prop, renders caveat text. No fetch, no links. |
| `DecisionSummary.tsx` | Receives `run` as prop, renders summary. No fetch, no links. |
| `ComparisonTable.tsx` | Renders cell data as plain text table. Does not embed `CellDetail` or `MatrixHeatmap` — those are separate siblings in the page layout. No `projectKey` pass-through needed. |

### 7.10 Evaluate API: Project-Scoped Write

The POST handler at `/api/runs/[id]/cells/[cellId]/evaluate/route.ts` currently
calls `getProjectRoot()` as the `cwd` for the `uv run` subprocess. This must
be updated:

**New route**: `/api/project/[key]/runs/[id]/cells/[cellId]/evaluate`

The handler resolves the project path from the registry via `key`, validates
it, and passes it as `cwd` to the subprocess.

**Old route disposition**: The old POST evaluate route returns **410 Gone**
(not a redirect) because HTTP redirects for POST are unsafe — the request
body may be dropped by clients, and a 308 redirect to an unexpected host
could leak the evaluation payload. GET routes use scan-and-redirect (308)
because they are idempotent and have no body. This asymmetry is intentional.

All other API routes follow the same pattern:

| Old Route | New Route |
|-----------|-----------|
| `GET /api/runs` | `GET /api/project/[key]/runs` |
| `GET /api/runs/[id]` | `GET /api/project/[key]/runs/[id]` |
| `GET /api/runs/[id]/cells/[cellId]` | `GET /api/project/[key]/runs/[id]/cells/[cellId]` |
| `GET /api/runs/[id]/cells/[cellId]/trace` | `GET /api/project/[key]/runs/[id]/cells/[cellId]/trace` |
| `GET /api/runs/[id]/artifacts` | `GET /api/project/[key]/runs/[id]/artifacts` |
| `POST /api/runs/[id]/cells/[cellId]/evaluate` | `POST /api/project/[key]/runs/[id]/cells/[cellId]/evaluate` |
| `GET /api/trends` | `GET /api/project/[key]/trends` |

A new top-level `GET /api/projects` returns all `ProjectSummary` entries.

### 7.11 Trends API

The `/api/project/[key]/trends` route reads `index.db` from the resolved
project path:

```
GET /api/project/[key]/trends?configuration_id=mock-local&metric=pass_rate
```

Without a project key, the old `/api/trends` returns 400 with a message
directing clients to use the project-scoped endpoint.

---

## 8. VitePress Documentation

### 8.1 Updates to `site/guide/getting-started.md` (English)

Replace the "Starting the Web UI" section (lines ~225-244) with expanded
content covering:

1. **Single-project usage** (unchanged workflow):
   ```bash
   cd my-eval-project
   micro-eval run
   micro-eval ui
   # UI shows runs from this directory
   ```

2. **Multi-project dashboard**:
   ```bash
   # Projects are auto-registered when you run evaluations
   cd ~/eval-project-A && micro-eval run
   cd ~/eval-project-B && micro-eval run

   # Launch UI from anywhere — it reads the global registry
   micro-eval ui
   # Dashboard shows both Project A and Project B
   ```

3. **Manual registration** for existing projects:
   ```bash
   # Register a project that already has .micro-eval/runs/ data
   micro-eval register ~/old-eval-project

   # Register all example directories at once
   micro-eval register examples/agent-codefix-showdown
   micro-eval register examples/multi-task-matrix
   micro-eval register examples/git-workspace-isolation
   ```

4. **Managing projects**:
   ```bash
   # List all registered projects
   micro-eval projects

   # Remove a project from the dashboard (data is not deleted)
   micro-eval unregister agent-codefix-showdown-a3f7b2c1e9d0
   ```

### 8.2 Updates to `site/zh/guide/getting-started.md` (Chinese)

Mirror the same content updates in Chinese. The Chinese guide is a full
translation, not a subset — all new sections must be translated.

### 8.3 Updates to `site/reference/web-ui.md` and `site/zh/reference/web-ui.md`

Update the existing Web UI reference page to document:

- Project card grid (new landing page)
- Project-scoped routes (`/project/[key]/...`)
- Project-scoped API endpoints
- Backward-compatible `/run/[id]` redirects
- Troubleshooting: "path not found" badge, empty dashboard

### 8.4 VitePress Sidebar

No new sidebar entries needed — the existing `reference/web-ui` entry covers
the expanded content. The getting-started guide already has its entry.

---

## 9. Migration & Backward Compatibility

### 9.1 Existing Data

No migration needed. Existing `.micro-eval/runs/` directories are not moved.
Users run `micro-eval register <path>` to make old projects visible in the UI.

### 9.2 `MICRO_EVAL_PROJECT_ROOT` Environment Variable

Still honored. When set and no registry exists, the UI behaves exactly as
before (single-project mode). When the registry exists, `MICRO_EVAL_PROJECT_ROOT`
is treated as a synthetic registered project:
- It appears in the project card grid with name derived from the directory.
- Its key is computed the same way as any registered project.
- If the same path is also in the registry, the registry entry takes
  precedence (no duplicate card).

### 9.3 Fallback Behavior Matrix

The UI landing page behavior depends on two conditions: whether the registry
exists (and has entries) and whether a local `.micro-eval/runs/` is available
(via `MICRO_EVAL_PROJECT_ROOT` or the UI's resolved cwd).

| Registry | Local `.micro-eval/runs/` | Landing Page Behavior |
|----------|--------------------------|----------------------|
| Missing or empty | Present | Single-project run list (current behavior, no project cards). Local project shown directly. |
| Missing or empty | Absent | Empty state with registration instructions. |
| Has entries | Present, path matches a registry entry | Project card grid. Local project de-duped. |
| Has entries | Present (cwd-local), path NOT in registry | Project card grid. Local project shown as an extra "unregistered" card with a "Register" action button. |
| Has entries | `MICRO_EVAL_PROJECT_ROOT` set, NOT in registry | Project card grid. Env-root path treated as synthetic project card (per §9.2), key computed from realpath. |
| Has entries | Absent | Project card grid (normal multi-project dashboard). |

The key upgrade path: existing single-project users see no change until they
either run `micro-eval register` or run evaluations in a second directory.
The transition from single-project to multi-project mode is seamless.

### 9.4 Old Route Handling

**Page routes** (all use the same redirect logic from §7.6):

| Old Route | Redirects To |
|-----------|-------------|
| `/run/[id]` | `/project/[key]/run/[id]` |
| `/run/[id]/review` | `/project/[key]/run/[id]/review` |
| `/run/[id]/artifact/[artifactId]` | `/project/[key]/run/[id]/artifact/[artifactId]` |

**API routes**:

| Old Route | Behavior |
|-----------|----------|
| `GET /api/runs` | Return 301 with `Location: /api/projects` |
| `GET /api/runs/[id]` | Scan registry; 308 redirect if unique match; 400 with project list if ambiguous; 404 if none |
| `GET /api/runs/[id]/cells/[cellId]` | Same scan-and-redirect logic as above |
| `GET /api/runs/[id]/cells/[cellId]/trace` | Same scan-and-redirect logic as above |
| `GET /api/runs/[id]/artifacts` | Same scan-and-redirect logic as above |
| `POST /api/runs/[id]/cells/[cellId]/evaluate` | Return 410 Gone (not redirect — POST body safety, see §7.10) |
| `GET /api/trends` | Return 400 with message to use `/api/project/[key]/trends` |

### 9.5 Duplicate Run ID Across Projects

Run IDs contain timestamps and random suffixes (`run-20260615T091803Z-fabb41f4`),
making cross-project collisions extremely unlikely but not impossible. When the
old `/run/[id]` redirect finds multiple matches, it returns a disambiguation
page — never silently picks one.

---

## 10. Implementation Boundaries

### 10.1 Files to Create

| File | Purpose |
|------|---------|
| `src/micro_eval/store/registry.py` | `ProjectRegistry` class + `ProjectEntry` dataclass |
| `src/micro_eval/cli/register.py` | register / unregister / projects CLI commands |
| `ui/src/app/project/[key]/page.tsx` | Per-project run list page |
| `ui/src/app/project/[key]/run/[id]/page.tsx` | Run detail (project-scoped) |
| `ui/src/app/project/[key]/run/[id]/review/page.tsx` | Review page (project-scoped) |
| `ui/src/app/project/[key]/run/[id]/artifact/[artifactId]/page.tsx` | Artifact viewer (project-scoped) |
| `ui/src/app/api/projects/route.ts` | `GET /api/projects` endpoint |
| `ui/src/app/api/project/[key]/runs/route.ts` | Project-scoped runs API |
| `ui/src/app/api/project/[key]/runs/[id]/route.ts` | Project-scoped run detail API |
| `ui/src/app/api/project/[key]/runs/[id]/cells/[cellId]/route.ts` | Project-scoped cell API |
| `ui/src/app/api/project/[key]/runs/[id]/cells/[cellId]/evaluate/route.ts` | Project-scoped evaluate API |
| `ui/src/app/api/project/[key]/runs/[id]/cells/[cellId]/trace/route.ts` | Project-scoped trace API |
| `ui/src/app/api/project/[key]/runs/[id]/artifacts/route.ts` | Project-scoped artifacts API |
| `ui/src/app/api/project/[key]/trends/route.ts` | Project-scoped trends API |
| `ui/src/app/run/[id]/layout.tsx` | Shared redirect handler for all old `/run/[id]` sub-routes (§7.6) |
| `ui/src/components/ProjectCard.tsx` | Project card component |

### 10.2 Files to Modify

| File | Change |
|------|--------|
| `src/micro_eval/store/run_store.py` | `finalize_run()` calls registry (best-effort) |
| `src/micro_eval/cli/main.py` | Add register/unregister/projects commands; update `ui` command launch strategy |
| `ui/src/lib/api.ts` | Add registry reader, project-scoped functions, path validation |
| `ui/src/lib/schema.ts` | Add `ProjectSummarySchema`, `RegistrySchema` |
| `ui/src/app/page.tsx` | Replace RunList with ProjectCard grid (with single-project fallback) |
| `ui/src/app/run/[id]/page.tsx` | Simplify to minimal pass-through (redirect handled by parent `layout.tsx`) |
| `ui/src/app/run/[id]/review/page.tsx` | Simplify to minimal pass-through (redirect handled by parent `layout.tsx`) |
| `ui/src/app/run/[id]/artifact/[artifactId]/page.tsx` | Simplify to minimal pass-through (redirect handled by parent `layout.tsx`) |
| `ui/src/app/api/runs/route.ts` | Return 301 to `/api/projects` |
| `ui/src/app/api/runs/[id]/route.ts` | Scan-and-redirect (308/400/404) |
| `ui/src/app/api/runs/[id]/cells/[cellId]/route.ts` | Scan-and-redirect (308/400/404) |
| `ui/src/app/api/runs/[id]/cells/[cellId]/trace/route.ts` | Scan-and-redirect (308/400/404) |
| `ui/src/app/api/runs/[id]/cells/[cellId]/evaluate/route.ts` | Return 410 Gone |
| `ui/src/app/api/runs/[id]/artifacts/route.ts` | Scan-and-redirect (308/400/404) |
| `ui/src/app/api/trends/route.ts` | Return 400 directing to project-scoped endpoint |
| `ui/src/components/RunList.tsx` | Accept `projectKey` prop, update link pattern |
| `ui/src/components/CellDetail.tsx` | Accept `projectKey` prop, update artifact link |
| `ui/src/components/MatrixHeatmap.tsx` | Accept `projectKey` prop, update review link |
| `ui/src/components/ComparisonTable.tsx` | No changes needed (renders plain text, no embedded link-generating children — see §7.9 audit) |
| `ui/src/components/DecisionSummary.tsx` | No changes needed (display-only — see §7.9 audit) |
| `ui/src/components/AnnotationPanel.tsx` | Accept `projectKey` prop; POST to `/api/project/${key}/runs/.../evaluate` |
| `site/guide/getting-started.md` | Update "Starting the Web UI" section |
| `site/zh/guide/getting-started.md` | Mirror English updates in Chinese |
| `site/reference/web-ui.md` | Update to document multi-project dashboard |
| `site/zh/reference/web-ui.md` | Mirror English updates in Chinese |

### 10.3 Test Plan

**Registry (pytest)**:
| Test | What it verifies |
|------|-----------------|
| `test_register_creates_registry` | First register creates dir + file with correct permissions |
| `test_register_idempotent` | Re-registering same path updates timestamp, doesn't duplicate |
| `test_register_same_name_different_path` | Two entries created with distinct keys |
| `test_unregister_by_key` | Removes correct entry |
| `test_unregister_by_path` | Resolves to key, removes correct entry |
| `test_unregister_not_found` | Returns False, no error |
| `test_project_key_deterministic` | Same path always produces same key |
| `test_project_key_unique` | Different paths produce different keys |
| `test_find_all_by_run_id` | Scans all project dirs, returns correct entry list |
| `test_find_all_by_run_id_no_match` | Returns empty list |
| `test_atomic_write_corrupt_recovery` | Interrupted write leaves valid or absent file |
| `test_lock_contention` | Concurrent register calls don't corrupt |
| `test_corrupt_registry_handled` | Malformed JSON → empty project list, no crash |
| `test_permission_denied` | Read-only dir → graceful error |
| `test_schema_version_unknown` | Future version entries skipped with warning |
| `test_finalize_run_triggers_registration` | Integration: RunStore.finalize_run registers |
| `test_lock_file_symlink_rejected` | Symlink at lock path → RegistryLockError, no follow |
| `test_world_writable_dir_rejected` | 0o777 registry dir → refuses to write |
| `test_find_all_by_run_id_multiple` | Same run ID in two projects → returns both entries |

**CLI (pytest)**:
| Test | What it verifies |
|------|-----------------|
| `test_register_default_cwd` | Registers cwd |
| `test_register_explicit_path` | Registers given path |
| `test_register_with_name` | Uses --name override |
| `test_unregister_by_key` | Removes by key |
| `test_unregister_by_path` | Removes by path |
| `test_projects_list` | Shows table output |
| `test_projects_json` | Shows JSON output |
| `test_register_virgin_path` | Path with no `.micro-eval/` → succeeds, name = basename, run_count = 0 |
| `test_ui_launch_env_override` | `MICRO_EVAL_UI_DIR` set → uses that dir |
| `test_ui_launch_git_root` | Running from subdirectory → walks up to `.git/` root, finds `ui/` |
| `test_ui_launch_not_found` | No ui/ anywhere → clear error message |

**UI Data Layer (vitest)**:
| Test | What it verifies |
|------|-----------------|
| `test_getRegistry_missing_file` | Returns empty registry |
| `test_getRegistry_valid` | Parses correctly |
| `test_listAllProjects_aggregates` | Reads from multiple paths |
| `test_listAllProjects_stale_path` | Missing path → accessible=false |
| `test_resolveProjectPath_valid_key` | Returns correct path |
| `test_resolveProjectPath_unknown_key` | Returns null |
| `test_validateProjectPath_traversal` | Rejects `../` in output_dir |
| `test_validateProjectPath_symlink_escape` | Rejects symlink outside project |
| `test_listRunsByProject_correct_dir` | Reads from project-specific dir |
| `test_getRunInProject_isolates` | Doesn't read from other projects |
| `test_env_root_dedup` | MICRO_EVAL_PROJECT_ROOT same as registry entry → one card |
| `test_env_root_synthetic` | MICRO_EVAL_PROJECT_ROOT not in registry → extra card |
| `test_single_project_fallback` | No registry + local .micro-eval → old behavior |

**UI Routes (vitest)**:
| Test | What it verifies |
|------|-----------------|
| `test_old_run_route_redirects` | `/run/[id]` → 308 to correct project |
| `test_old_run_route_ambiguous` | Multiple matches → disambiguation page |
| `test_old_run_route_not_found` | No match → 404 |
| `test_old_run_review_route_redirects` | `/run/[id]/review` → 308 to project-scoped review |
| `test_old_run_artifact_route_redirects` | `/run/[id]/artifact/[aid]` → 308 to project-scoped artifact |
| `test_old_api_runs_redirects` | `/api/runs` → 301 |
| `test_old_api_runs_id_ambiguous` | `/api/runs/[id]` with multi-match → 400 |
| `test_project_api_runs` | `/api/project/[key]/runs` returns correct runs |
| `test_project_api_evaluate` | POST writes to correct project dir |
| `test_project_api_trends` | Reads correct index.db |
| `test_annotation_panel_posts_to_project_api` | EvaluationForm (inner) constructs fetch URL with project key |
| `test_old_api_artifacts_redirects` | `/api/runs/[id]/artifacts` → scan-and-redirect |
| `test_old_api_trace_redirects` | `/api/runs/[id]/cells/[cellId]/trace` → scan-and-redirect |
| `test_old_api_evaluate_410` | `POST /api/runs/[id]/cells/.../evaluate` → 410 Gone |
| `test_env_root_not_in_registry_synthetic_card` | `MICRO_EVAL_PROJECT_ROOT` set, not in registry → synthetic card |
| `test_unregistered_local_project_card` | Registry exists + local .micro-eval/ not in registry → extra card |

**Contract**:
| Test | What it verifies |
|------|-----------------|
| `test_registry_schema_forward_compat` | Extra fields in entries are preserved |
| `test_registry_schema_roundtrip` | Write → read → write produces identical JSON |

---

## 11. Security Considerations

### 11.1 Path Traversal

`ProjectRegistry` validates that registered paths are absolute and normalized
(`Path.resolve()`). The UI validates all paths via `validateProjectPath()`
(§7.3) which:
1. Resolves the project path from the registry (never from user input directly).
2. Verifies `output_dir` is relative and resolves inside the project root.
3. Resolves symlinks and re-checks containment.

The UI never accepts a raw filesystem path from query parameters — only
`project_key`, which is looked up in the registry.

### 11.2 Registry File Permissions

- `~/.micro-eval/` directory: mode `0o700` (owner-only).
- `~/.micro-eval/registry.json`: mode `0o600` (owner read/write).
- `~/.micro-eval/registry.lock`: mode `0o600`.

While the registry contains no secrets, project paths can reveal directory
structure. Owner-only permissions prevent other local users from enumerating
evaluation projects.

### 11.3 Symlink Safety for Lock File

The lock file must not follow symlinks (prevents symlink-based lock
redirection attacks). Implementation:

```python
import os

fd = os.open(
    str(LOCK_FILE),
    os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW,
    0o600,
)
```

`O_NOFOLLOW` causes the open to fail with `ELOOP` if the path is a symlink.
On failure:
1. Log a warning: "registry.lock is a symlink, refusing to acquire lock".
2. Do not delete the symlink (could be an attack vector itself).
3. Raise `RegistryLockError` — the caller (finalize_run) catches this and
   degrades gracefully (run succeeds, registration skipped).

**Post-open verification** (belt-and-suspenders): after opening, `os.fstat(fd)`
and verify `stat.S_ISREG` is true. If not, close and raise.

**Windows**: `O_NOFOLLOW` is not available. On Windows, use `os.lstat()` before
open to check for symlink, accepting the TOCTOU window as an acceptable risk
on a platform where symlinks require elevated privileges by default.

**Run data access**: uses `fs.realpathSync` + containment check (same as
existing `getArtifact` in `api.ts:100-106`).

### 11.4 World-Writable Directory Check

Before writing to `~/.micro-eval/`, the registry code checks that the directory
is not world-writable (`stat.st_mode & 0o002`). If it is, registration fails
with an error message advising the user to fix permissions.

---

## 12. Error Handling Summary

| Scenario | Behavior |
|----------|----------|
| Registry file missing | Treated as empty registry; created on first write |
| Registry file corrupt (invalid JSON) | Log warning, treat as empty; next write recreates |
| Registry dir missing | Created with `0o700` on first write |
| Registry dir world-writable | Refuse to write, log error |
| Lock acquisition timeout | Retry 3×100ms, then `RegistryLockError` |
| Registered path doesn't exist | UI shows "path not found" badge; CLI warns |
| Registered path has no runs | UI shows "0 runs" |
| Permission denied reading runs dir | UI shows "access denied" badge |
| `output_dir` escapes project root | Rejected by path validation; entry ignored |
| Unknown `schema_version` (top-level) | Log warning, treat entire registry as empty (do not partially parse) |
| Duplicate run ID across projects | Old route shows disambiguation page |
| `MICRO_EVAL_PROJECT_ROOT` same as registry entry | De-duplicated to one card |
| Lock file is a symlink | `O_NOFOLLOW` fails with ELOOP → `RegistryLockError`; registration skipped, run succeeds |
| Permission denied creating `~/.micro-eval/` | `RegistryLockError`; registration skipped, run succeeds |
| `register` on path with no `.micro-eval/` | Succeeds; name falls back to directory basename; run_count = 0 |
