# Agent Instructions

---

## Output

Talk caveman. grammar not important. short. direct. no filler.

good: "done. 3 files changed. auth broken, fix next"
bad: "I have successfully completed the implementation of the authentication module and would like to inform you that..."

code blocks still formatted normal. only prose goes caveman.

---

## KB — setup

before using any KB tool, check `.vscode/mcp.json` exists and contains agent-kb server config.

if missing or agent-kb entry absent — cannot self-add, needs values from user.
ask user three things in one message:
- "agent-kb not in mcp.json. need 3 things:"
- "1. db url — postgres://user:pass@host:5432/dbname"
- "2. ollama model name — e.g. nomic-embed-text"
- "3. embedding dims for that model — e.g. 768"

common models and dims for reference:
- nomic-embed-text → 768
- mxbai-embed-large → 1024
- snowflake-arctic-embed → 1024
- all-minilm → 384

once user provides all three — add entry, merge into existing servers, do not overwrite:

```json
{
  "servers": {
    "agent-kb": {
      "type": "stdio",
      "command": "npx",
      "args": [
        "agent-kb-mcp",
        "--db-url", "postgres://agentuser:agentpass@host:5433/agentdb",
        "--ollama-model", "nomic-embed-text",
        "--embedding-dims", "768"
      ]
    }
  }
}
```

tell user: "agent-kb added to .vscode/mcp.json. make sure ollama is running and model is pulled: ollama pull nomic-embed-text. restart MCP server."

---

## Memory — log to KB after every blocker

when hit blocker or bug or unexpected behaviour:

1. `search_kb(problem description)` — check if already solved
2. if similarity >= 0.82 → hit counts, call `get_context(same query)` → apply the solution block it returns before trying anything else. tell user: "KB hit [similarity score]: [problem matched]"
3. if no hit or similarity < 0.82 → solve it fresh
4. before logging, apply fix confirmation rule below — determines whether to log now or wait
5. once confirmed (by agent or user depending on bug type) → `log_problem` then `log_solution(worked=true)`
6. if a complete, deliberate attempt was tried fully and failed → `log_solution(worked=false)` — logs the dead end so future runs skip it

**fix confirmation rule:**
- logic / runtime bug → agent can self-verify (error gone, tests pass, output correct) → log immediately, no need to wait
- UI/UX bug → agent cannot see screen, cannot self-verify → wait for explicit user confirmation before logging
- when unsure if bug is logic or visual → treat as UI/UX → wait for user

**what to log:**
- language / runtime
- what the problem was (plain language, factual, language-agnostic where possible — makes KB useful across stacks)
- exact fix that worked, step by step
- any context that made it non-obvious (version mismatch, env quirk, order dependency)

**what NOT to log:**
- guesses or things half-tried
- partial fixes — only log a solution if it fully resolved the problem
- UI/UX fixes that user has not confirmed
- `worked=false` entries for guesses — only log a failed attempt if it was a complete, deliberate attempt that turned out wrong

---

## Logs — always add before running

before running any code, add logs at every key execution point.

each log needs two things:
1. the label + actual value printed at runtime
2. a short inline comment saying what this log expects — grammar not important

```ts
// expects: user object with valid id after db fetch
console.log("[after-db-fetch]", JSON.stringify(user))

// expects: token not null, expiry in future
console.log("[token-check]", token, expiry)
```

```python
# expects: list non-empty after filter
print("[after-filter]", items)
```

```go
// expects: err nil here, conn established
log.Printf("[db-connect] %+v %v", conn, err)
```

rules:
- max 3 logs per function — if you need more, the function is too big, split it
- log at decision points, boundaries, and state changes — not every line
- do not log trivial things: loop iterations, simple assignments, getters, pure transformations
- good log targets: after external calls (db, api, fs), after auth/validation checks, at branch outcomes that change flow
- label in brackets, descriptive, unique per run
- comment says expected state — not what the code does, what you expect to see
- if log shows something unexpected → stop, do not keep running, diagnose first
- remove all debug logs before closing task — only production-intentional logs stay

---

## Flowmap — setup

before using any flowmap tool, check `.vscode/mcp.json` exists and contains flowmap server config.

if missing or flowmap entry absent — add it, no need to ask user:

```json
{
  "servers": {
    "flowmap": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "callgraph-mcp"],
      "env": {
        "FLOWMAP_TRANSPORT": "stdio"
      }
    }
  }
}
```

if `.vscode/mcp.json` already exists with other servers — merge flowmap entry in, do not overwrite the file.
tell user: "flowmap added to .vscode/mcp.json. restart MCP server if not already running."

---

## Flowmap — run after every major feature

(Only works for jsx/tsx,js/ts,python,go)
after completing any feature that adds or changes function relationships:

1. `flowmap_analyze_workspace(workspacePath)` — full graph check
2. look for:
3. - check duplication and scope for reusable functions rather than repetitions
   - new orphans (functions you added that nothing calls — probably wired wrong)
   - new cycles (you created a circular dependency)
   - chokepoints (your new function has high in + out degree — fragile)
4. if duplicates found check if reusable function can be implemented and used
5. if cycles found → fix before moving on, do not defer
6. if orphans found → either wire them or delete them, tell user which
7. report findings caveman: "2 orphan. 1 cycle in auth→db→auth. fix?"

when to also run flowmap (not just after features):
- before refactor — get baseline graph, compare after
- after agent-generated code runs for a while — `flowmap_find_duplicates` to catch silent copy-paste sprawl
- before PR — `flowmap_get_callers(changed_function)` for every function touched, report blast radius to user

---

## Code quality

- never leave TODO without a comment explaining why not done now
- if touching a file, leave it cleaner than found — fix obvious things in passing
- new function → ask: does this already exist? run `flowmap_find_duplicates` if unsure
- if adding a dependency, say why. one line comment at import.
- no magic numbers. name them.

---

## Asking vs doing

- task is clear and small → do it, report after
- task is ambiguous or touches more than 3 files → confirm scope first, one question only
- blocked → say what tried, what failed, what options are. do not spiral silently
- never ask two questions at once. pick the most important one.

---

## Task hygiene

- one thing at a time. finish before starting next.
- if task grows mid-execution (scope creep found) → stop, report, ask before continuing
- before closing any task: logs removed, tests pass, flowmap clean, KB updated if there was a blocker
- do not mark done if any of those four are unresolved

---

## Quick reference — which MCP for what

| situation | tool | confirmation needed? |
|---|---|---|
| hit a bug / blocker | `search_kb` → if >= 0.82, `get_context` | — |
| logic/runtime fix verified by agent | `log_problem` + `log_solution(worked=true)` | no — agent self-verify |
| UI/UX fix | `log_problem` + `log_solution(worked=true)` | yes — wait for user |
| complete attempt that fully failed | `log_solution(worked=false)` | no |
| finished a feature | `flowmap_analyze_workspace` | — |
| about to refactor | `flowmap_analyze_workspace` (baseline) | — |
| changed a function | `flowmap_get_callers` (blast radius) | — |
| codebase getting messy | `flowmap_find_duplicates` + `flowmap_find_cycles` | — |
| new to codebase | `flowmap_list_entry_points` + `flowmap_get_flow` per entry | — |
