---
name: ameparse
description: >-
  Inspect `.ame` model files — components, parameters, variables, local
  connection graph, simulation settings — via the read-only ameparse CLI.
  No modeling-software installation or license needed. Use this BEFORE writing any
  calibration script (set params / run / extract) to learn what the model
  contains and what is observable; never use it to modify a model.
---

# ameparse — read-only `.ame` model inspector

**Install (once):**

```bash
cd <this-repo>/scripts && uv tool install .
```

Then `ameparse` is on PATH — run it directly from anywhere, no `uv run` needed.

## Rules

1. **Read-only.** This CLI never modifies models. Setting parameters, running
   simulations and extracting results go through the runtime scripting
   API (amicalib) — not here.
2. **Brief once, then code.** Gather the facts below in a handful of small
   queries (a few KB total), then write your calibration script and stop
   querying. Model facts are static; do not re-query during iteration.
3. **Output discipline.** Never print the full card (MBs). Every query below
   returns KB-sized output; list commands refuse to run without a filter
   (`--all` overrides) — that guardrail protects your context.
4. **Identifiers** are `name@alias` (e.g. `Uinit@BatPackGene`) — the same
   internal ids the runtime API uses. Before `ameputp`, map them via
   `amegetparamnamefromui(sname, "Uinit@BatPackGene")`.
   Duplicate aliases exist (inside/outside supercomponents): error messages
   list the candidate `path=` qualifiers.

## Workflow (six phases)

### 1. Settings — what am I working with

```bash
ameparse MODEL.ame --settings      # version, final_time/print_interval, states, io
```

Note `final_time` (your iteration budget) and check `ame_version` matches the
local runtime.

### 2. Locate — translate the task's physical terms into components

```bash
ameparse MODEL.ame --components --submodel ESSBATPA01
ameparse MODEL.ame --search battery                 # by name/title substring
ameparse MODEL.ame --subgraph BatPackGene --hops 2  # local graph (typed nodes+edges)
ameparse MODEL.ame --subgraph BatPackGene --hops 2 --domain thermal
ameparse MODEL.ame --neighbors BatPackGene          # per-port neighbors
```

`--subgraph` is the loop view: nodes carry port types, edges carry both port
domains. Use `--domain` (thermal/elect/signal/...) to see one physical domain
at a time.

### 3. Parameters — define the search space

```bash
ameparse MODEL.ame --globals                       # global params + who uses them
ameparse MODEL.ame --global LF_beta7               # one knob and its ref sites
ameparse MODEL.ame --params --component BatPackGene --modified-only
ameparse MODEL.ame --param Uinit@BatPackGene
```

Two different knob spaces — check both:

- **Global parameters** (`--globals`). On encapsulated/protected deliverables
  (encrypted submodels, GUI read-only) the component tree is largely inert and
  the globals are the real lever. `refs` counts the parameter/variable values
  that mention each global, and a **variable** hit is that state's *initial
  value*, so the ref list answers "which states does this knob drive".
  Also read the diagnostics before trusting any value: `conflicts` (same name,
  different value across `.amegp`/`.cir`/`.pl` — the authoritative one is
  `global_params[].value`), `twins` (`X` vs `X__INSTANCE` with divergent values
  — edit one and the other silently keeps the old value), `unused` (defined but
  referenced nowhere).
- **Component parameters**, where modified-vs-default is the modeler's intent.
  This heuristic **fails on wrapped deliverables**: `--params --modified-only`
  there returns only wrapper rewrites (`x>NAME` → `x>NAME__BLOCK_1`), not real
  knobs. If every modified row looks like a rename, the levers are the globals.

`--param` gives `min`/`max` (your search bounds), `unit`, `default`, current `value`.

### 4. Verify observability — before writing any loop

```bash
ameparse MODEL.ame --variable Temp@BatPackGene
ameparse MODEL.ame --variables --component BatPackGene --saved
```

Check **`"saved": true`** — membership in the model's save list, the only
variables `ameloadvarst` can retrieve. (`"save": true` is merely the
saveable declaration and can contradict `saved`.) If your target is
`saved: false`, `--search` an alternative variable or report that the task
needs a save-list change — do not discover this after a multi-minute run.

### 5. Write the script — leave the CLI

You now have: param ids + bounds + units, retrievable variable ids,
`final_time`. Switch to runtime scripting code (amicalib). For bulk/unusual analysis,
export once and process the JSON in python — never cat it:

```bash
ameparse MODEL.ame -o card.json
```

### 6. Iterate — no more queries

During calibration, current values live in the runtime session and your trace,
not in the CLI. Come back only on errors (e.g. `AmbiguousAlias` → add
`path=`), or afterwards to diff the working copy's `--params --modified-only`
against the template as a hygiene check.

## Command reference

| Command | Purpose |
|---|---|
| `--settings` | version / simulation options (incl. raw numeric fields) / model io |
| `--summary` | counts overview |
| `--components --alias A / --submodel S / --all` | compact component rows (alias/submodel/ports/param count) |
| `--component ALIAS [--no-params] [--no-variables]` | one component, optionally trimmed |
| `--param ID` | one parameter: value/default/min/max/unit/param_id |
| `--params --component A / --submodel S [--modified-only] / --all` | compact param rows |
| `--variable ID` | one variable incl. `saved` (retrievable) and `save` (saveable flag) |
| `--variables --component A / --submodel S [--saved / --save-flag / --hidden] / --all` | compact variable rows; `--saved` is the authoritative filter |
| `--search KEYWORD` | globals, params & variables by name/title substring (capped at 100 each) |
| `--study-params` | study/batch parameters with bounds |
| `--globals` | global parameters (`.amegp`/`.cir`/`.pl` merged) with reference counts, conflicts and diagnostics |
| `--global NAME` | one global with every referencing param/variable (`name@alias`, role, expression) |
| `--globals --with-refs` | `--globals` plus per-global reference lists (capped at 20 each; prefer `--global NAME`) |
| `--neighbors ALIAS` | per-port neighbor map |
| `--subgraph ALIAS [--hops N] [--domain D]` | local graph: typed nodes + typed edges (≤300 nodes) |
| `--saved-variables` | full save list (large; prefer `--variables --saved --component`) |
| `--csv DIR` | params/variables CSV tables |
| `-o FILE` | write full card JSON to file |
| `export --resources DIR --out DIR` | batch: sources/ + cards/ + csv/ |

## Gotchas

- Ports are 1-based everywhere (`.cir` raw refs in `connections` are 0-based).
- Without a compiled `.c` member the graph is unavailable — graph queries fail;
  `connections` (raw entity numbers) still works. The **globals/refs path needs
  no `.c`** — it reads `.cir` text only, so it works on every model.
- `--globals` on a large model is a large output (one row per global; PB62 has
  234). Narrow with `--search` or drill in with `--global NAME`.
- Titles/units of Chinese models are UTF-8 in files that declare
  `encoding="ISO-8859-1"`; the decoder prefers UTF-8 so titles come out readable
  (a mojibake title means the value you are reading may be misattributed too).
- `.amegp`, `.cir` and `.pl` can each define the same global with a different
  value. Never assume the one you read is the operative one — `--globals` gives
  `source` per entry and lists disagreements in `conflicts`.
- `.sim` fields beyond start/final/print-interval are version-dependent;
  access them by index in `--settings` → `simulation.values`.
