# Loop Engineering — a Spec Kit extension

**Engineer autonomous agent loops you can still stand behind.** A loop is a
recursive goal — define a purpose, let the agent iterate until complete — but
built with a maker/checker split, externalized state, and guardrails that keep a
human in the loop: budgeted iterations, an independent adversarial checker, a
comprehension-debt ledger, and a sign-off gate.

Operationalizes **Loop Engineering** — Addy Osmani,
[*"Loop Engineering"*](https://addyo.substack.com/p/loop-engineering) — for
[Spec Kit](https://github.com/github/spec-kit) workflows. It is not affiliated
with the author or GitHub.

## Why

Loop Engineering names a real shift in how we work with coding agents: you stop
prompting by hand through every turn and instead *design the system that prompts
the agent* — a **loop**, "a recursive goal where you define a purpose and the AI
iterates until complete." Spec-driven development already has that shape: drive
every task in `tasks.md` to a passing state, satisfy every requirement in a spec.

But the article is just as clear about the catch. Autonomy sharpens three failure
modes:

- **Unattended verification** — nobody checks the work, or the model grades its
  own homework ("the model that wrote the code is way too nice").
- **Comprehension debt** — the loop changes more than you understand, and the gap
  compounds.
- **Cognitive surrender** — you start accepting whatever the loop emits because
  checking it is effort.

Its prescription is the design brief for this extension: *"Build the loop. But
build it like someone who intends to stay the engineer."* So the extension is not
"run an agent in a while-loop." It is the file-based discipline that makes an
autonomous loop **safe and reviewable** inside Spec Kit: a contract with checkable
done-criteria, a maker that never grades itself, an independent checker that tries
to break the work, and a guard that will not let the loop call itself done until a
human has signed off.

| Loop Engineering (article) | This extension |
|---|---|
| A loop = a recursive goal, defined once | `/speckit.loop.define` writes the goal + checkable done-criteria as a contract |
| Automations drive the loop unattended | The contract's automation trigger + `/speckit.loop.run` as the driveable maker step |
| Worktrees isolate parallel agents | `loop.isolation: worktree` — each iteration in its own git worktree |
| Skills capture reusable knowledge | `memory.md` — durable decisions and dead ends, carried across runs |
| Plugins & connectors integrate tools | The contract's allowed-tools allow-list the maker must stay inside |
| Sub-agents verify, separate from the maker | `/speckit.loop.check` — independent, adversarial, with an independence gate |
| Memory on disk (the model forgets between runs) | All loop state is `specs/<feature>/loop/*.md`; the conversation is disposable |
| Don't surrender judgment | `/speckit.loop.guard` — debt sweep, anti-surrender questions, human sign-off gate |

## What you gain

The loop does the iterating; you keep the authority. Concretely:

| With the loop extension | An ad-hoc "keep prompting until it works" loop |
|---|---|
| **A stop condition** — checkable done-criteria fixed before the loop runs | the loop ends when you get tired or the context fills |
| **No self-graded work** — the maker can't mark its own output `done`; an independent checker must pass it | the model that wrote it cheerfully declares it correct |
| **Adversarial verdicts on file** — every criterion carries pass/fail/uncertain + method + confidence | "looks done to me," unrecorded |
| **Comprehension debt made visible** — a ledger of what changed that you haven't understood, gating done | the gap between what shipped and what you grasp stays invisible until it bites |
| **A real sign-off gate** — done requires a human who can explain the change | the loop self-certifies and you hope for the best |
| **Session immortality** — resume after a restart/compaction with one `status` call | whatever fell out of the window is gone |
| **An audit trail** — contract, iterations, verdicts, debt, sign-offs are diffable markdown in the repo | the reasoning lived in one expired chat |

## Installation

This extension is bundled with the `jiwu-robotics/spec-kit` distribution. In an
initialized project, install it together with either bundled workflow:

```bash
specify extension add loop
specify workflow add speckit-loop
# or: specify workflow add speckit-loop-yolo
```

`speckit-loop` pauses for specification, plan, and completion approval.
`speckit-loop-yolo` has no human gates, but retains independent checker-pass,
blocking-debt, and hard-budget enforcement. The bundled `loop-state` step is
registered by the CLI and projects durable workflow/loop outcome state.

Verify:

```bash
specify extension list
#  ✓ Loop Engineering (v1.0.0)
#     loop
#     Commands: 6 | Hooks: 2 | Priority: 10 | Status: Enabled
```

Requires Spec Kit `>=1.0.2.dev0`. Works with any agent Spec Kit supports (Claude Code,
GitHub Copilot, Cursor, Gemini CLI, …) — commands are plain prompt files; no
external tools, MCP servers, or network access required.

## Commands at a glance

| Command | Role | What it does | Touches disk |
|---|---|---|---|
| `/speckit.loop.define [purpose] [key=value…]` | contract | Write the recursive goal + checkable done-criteria, budget, roles, guardrails | creates `loop/` (never overwrites) |
| `/speckit.loop.run [criteria \| n=k]` | **maker** | Produce one increment toward the goal; record it; hand off — never self-grades | `iterations.md`, `loop.md`, `memory.md` |
| `/speckit.loop.check [criteria]` | **checker** | Independently, adversarially grade the latest iteration against the criteria | `verdicts.md`, `loop.md`, `debt.md` |
| `/speckit.loop.guard [signoff]` | guard | Comprehension-debt sweep + anti-surrender prompt + human sign-off gate | `debt.md`, `loop.md` |
| `/speckit.loop.status [full \| topic]` | render | Compact snapshot + one recommended next action; session resume | **read-only** |

State lives in `specs/<feature>/loop/` (or `.specify/loops/global/` when no
feature directory exists).

## Where it fits in the Spec Kit workflow

The loop does not replace any core stage. It wraps the **build-and-verify** part
of the flow — turning `tasks.md`/`implement` into a bounded, graded, signed-off
loop instead of an open-ended prompting session.

```text
/speckit.specify ──▶ spec.md
/speckit.plan    ──▶ plan.md
/speckit.tasks   ──▶ tasks.md
        │  └─ hook after_tasks → /speckit.loop.define        (optional prompt)
        │        └─ writes specs/<feature>/loop/{loop, iterations,
        │           verdicts, debt, memory}.md — purpose + done-criteria fixed
        │
        │  ┌─ THE LOOP ─────────────────────────────────────────────────┐
        │  │  /speckit.loop.run     maker: one increment, externalized  │
        │  │       ↳ appends iterations.md · updates loop.md counter     │
        │  │  /speckit.loop.check   checker: independent, adversarial    │
        │  │       ↳ appends verdicts.md · pass / fail / uncertain       │
        │  │     (fail → back to run · uncertain → debt for a human)     │
        │  └────────────────────────────────────────────────────────────┘
        │
/speckit.implement                  build work the loop drives
        │  └─ hook after_implement → /speckit.loop.check      (optional prompt)
        │
/speckit.loop.guard ──▶ debt sweep + human sign-off ──▶ Phase: done
```

Stage by stage:

| Core stage | Loop command | How it is used |
|---|---|---|
| After `/speckit.tasks` | `define` (the `after_tasks` hook offers it) | Turn the task list into a loop contract: the recursive goal plus checkable done-criteria and a budget. |
| The build loop | `run` → `check` (→ `run` on fail) | The maker produces increments; an independent checker grades each against the criteria. Failures cycle back; uncertainties become debt. |
| After `/speckit.implement` | `check` (the `after_implement` hook offers it) | Grade the implementation with a checker that did not write it — the maker/checker split applied to the build. |
| Before calling it done | `guard` | The only path to `done`: comprehension-debt sweep, unattended-verification flags, anti-surrender questions, recorded human sign-off. |
| Any time | `status` | Read-only snapshot + exactly one recommended next action; the session-resume entry point. |

Two rules keep it safe: the loop **never edits** `spec.md`, `plan.md`, or
`tasks.md`, and only `guard` (with human sign-off) can declare the loop `done`.

## Usage

### 1. `/speckit.loop.define` — write the contract

```text
/speckit.loop.define Drive every task in tasks.md to a passing acceptance check max_iterations=10
```

- The free text is the **purpose** — the recursive goal. Inline `key=value`
  tokens override budget/policy (`max_iterations`, `isolation`, …).
- You will be asked for **done-criteria** — explicit, checkable conditions. The
  command refuses an open-ended loop: "it works" is not a criterion, "`npm test`
  exits 0 and `/health` returns 200" is.
- Creates `loop.md`, `iterations.md`, `verdicts.md`, `debt.md`, `memory.md`.
- **Idempotent**: if a loop already exists it shows status instead of
  overwriting; a new purpose is appended as an additional goal.

### 2. `/speckit.loop.run` — the maker

```text
/speckit.loop.run            # target the highest-priority unmet criteria
/speckit.loop.run D2 D3      # target specific criteria
/speckit.loop.run n=3        # up to 3 iterations, then one checker handoff
```

Each iteration the maker makes the smallest coherent increment toward a criterion,
isolated in a worktree if configured, then **externalizes** it: a record in
`iterations.md`, an incremented counter in `loop.md`, a durable note in
`memory.md` if a decision was made. It marks criteria `maker-ready` — never
`checker-pass`, never `done` — and stops with an explicit handoff to the checker.
`max_iterations` is a hard ceiling: hit it and the loop demands review, not more
making.

### 3. `/speckit.loop.check` — the independent checker

```text
/speckit.loop.check          # grade everything maker-ready
/speckit.loop.check D2       # grade one criterion
```

Run this **in a fresh session or as a separate sub-agent** — the checker has an
independence gate and will tell you to re-run it elsewhere if it shares the
maker's context. For each criterion it *tries to make it fail*, at the primary
source (run the test, hit the endpoint, open the file), and records a verdict:

```markdown
| ID | Iteration | Criterion | Method (primary source) | Verdict | Confidence | Date |
|----|-----------|-----------|-------------------------|---------|------------|------|
| D2 | 3 | `npm test` exits 0 | ran `npm test` in iter-3 worktree → 41 passed | pass | high | 2026-06-14 |
| D3 | 3 | `/health` returns 200 | curl localhost:3000/health → 500 (db not wired) | fail | high | 2026-06-14 |
```

`pass` → `checker-pass`; `fail` → `checker-fail` (back to the maker); `uncertain`
→ stays `maker-ready` **and** opens a comprehension-debt item for a human. A clean
sweep does **not** mean done — it routes you to `guard`.

### 4. `/speckit.loop.guard` — stay the engineer

```text
/speckit.loop.guard          # render the guard report
/speckit.loop.guard signoff  # record a human sign-off (after reviewing)
```

The only command that can close the loop. It sweeps every change since the last
sign-off into the comprehension-debt ledger, flags verifications a human hasn't
actually confirmed, and asks pointed, answerable questions about the real changes:

```text
⚠ Comprehension debt (2 open, 1 blocking)
  • iter-4 rewrote retry logic in api/client.ts — can you explain why in one sentence?
⚠ Unattended verification
  • D5 passed at medium confidence — have you seen it work yourself?

Done-gate:
  [x] all criteria checker-pass
  [ ] no blocking debt open     ← 1 open
  [ ] human sign-off recorded
→ Not done. Resolve the blocking debt item, then /speckit.loop.guard signoff.
```

Done requires all three: checker-pass on every criterion, no open blocking debt,
and a recorded human sign-off. The sign-off is logged, never fabricated — the
command surfaces the decision; you make it.

### 5. `/speckit.loop.status` — resume, or decide what's next

```text
/speckit.loop.status         # compact snapshot
/speckit.loop.status full    # 3× larger slices
```

Read-only. Renders the purpose, the done-criteria with per-criterion status,
iterations run / budget, latest verdicts, open debt, and **one** recommended next
action. This is the session-resume entry point: open a fresh agent, run it, and
continue exactly where the loop stopped — nothing depended on the old context.

## Tutorial — driving a feature's tasks to done

A minimal end-to-end pass. The feature: a `/health` endpoint backed by a real DB
connection, with tests.

### 0. Up to tasks, as usual

```bash
specify init health-svc --integration claude && cd health-svc
specify extension add loop          # see Installation for the one-time catalog opt-in
# /speckit.specify … /speckit.plan … /speckit.tasks
```

### 1. Define the loop (via the `after_tasks` hook)

```text
Define an autonomous loop to drive these tasks to completion? → yes

/speckit.loop.define Drive tasks.md to done max_iterations=8
→ Done-criteria:
  D1  `npm test` exits 0
  D2  GET /health returns 200 with {status:"ok"}
  D3  health check pings the DB (not a hardcoded 200)
→ specs/001-health-svc/loop/ created; budget 8; isolation worktree; sign-off required
```

### 2. Run the maker

```text
/speckit.loop.run
→ iter-1 (worktree ../loop-iter-1): added /health returning {status:"ok"}; D2 maker-ready
→ handoff: ready-for-check · budget 7 left
```

### 3. Check — in a fresh session

```text
/speckit.loop.check
→ D2 pass (high): curl /health → 200 {status:"ok"}
→ D3 fail (high): returns 200 unconditionally; DB never queried
→ D1 fail: no tests yet
→ routes back to /speckit.loop.run for D1, D3
```

### 4. Iterate until the checker is satisfied

```text
/speckit.loop.run D1 D3
→ iter-2: real DB ping + 2 tests; D1, D3 maker-ready
/speckit.loop.check       (fresh session)
→ D1 pass · D2 pass · D3 pass (verified: kills DB → /health returns 503)
→ all criteria checker-pass → recommends /speckit.loop.guard
```

### 5. Guard — and only now, done

```text
/speckit.loop.guard
→ debt: iter-2 changed connection-pool size — why? (open, non-blocking)
→ D3 confirmed by killing the DB locally → no unattended verification
→ Done-gate: [x] checker-pass  [x] no blocking debt  [ ] sign-off
/speckit.loop.guard signoff
→ sign-off logged (you, 2026-06-14) · Phase: done
```

The loop iterated to completion; every criterion was graded by something other
than its author; and the thing that flipped it to *done* was a human who could
explain what shipped.

## State files

`specs/<feature>/loop/` (or `.specify/loops/global/`):

| File | Role | Invariants |
|---|---|---|
| `loop.md` | The contract + live status | done-criteria are checkable; only `guard` sets `done` |
| `iterations.md` | Maker's persistent memory | append-only; maker never records a verdict |
| `verdicts.md` | Checker's verdicts | written only by `check`; primary-source method per row |
| `debt.md` | Comprehension-debt ledger + sign-off log | debt acknowledged, never deleted; sign-offs are real |
| `memory.md` | Durable decisions / dead ends | short, durable, carried across runs |

Ordinary markdown in your repo: diffable, reviewable in PRs, shared by every
agent and teammate on the feature.

## Patterns & recipes

**Light vs. heavy autonomy** — the budget is the lever:

```text
/speckit.loop.define quick spike: get the parser compiling max_iterations=3
/speckit.loop.define full migration of the auth module max_iterations=20
```

**Genuinely independent checking** — always run `/speckit.loop.check` in a fresh
session or as a sub-agent. Same-context checking inherits the maker's blind spots;
the independence gate nudges you, but you own the separation.

**Unattended / scheduled loops** — record the trigger in the contract and wire a
scheduler or CI to call `run` then `check`. Keep the `guard` sign-off human: that
gate is what stops "scheduled" from becoming "unsupervised."

**Comprehension-debt budget** — treat open debt like any other backlog. Review
`debt.md` in PRs; `block_done_on_open_debt` keeps high-severity items from being
waved through.

**Team workflow** — commit `loop/` with the feature branch. Reviewers see the
contract, every iteration, every verdict, and who signed off — the loop's full
reasoning, not a summary.

## Hooks

Both optional (you are prompted):

- `after_tasks` → `speckit.loop.define` — turn the task list into a loop contract.
- `after_implement` → `speckit.loop.check` — grade the implementation with a
  checker that did not write it.

## Configuration

Copy `config-template.yml` to `.specify/extensions/loop/loop-config.yml` and
adjust budgets, the maker/checker policy, guardrails, and slice sizes:

```yaml
loop:
  max_iterations: 8
  done_requires_checker_pass: true
  isolation: worktree          # worktree | none
checker:
  independent: true
  adversarial: true
  votes: 1
guard:
  require_human_signoff: true
  track_comprehension_debt: true
  block_done_on_open_debt: true
rendering:
  iterations_slice: 6
  debt_slice: 8
  context_tokens: 4000
```

Precedence (lowest → highest): extension defaults → config file →
`SPECKIT_LOOP_*` environment variables → per-invocation `key=value` arguments to
`define`.

## Troubleshooting & FAQ

**`define` refuses my loop ("no checkable done-criteria").** By design — a loop
with no testable definition of "complete" has no stop condition. Give each
criterion a primary-source check (a test, an endpoint, a file shape).

**`check` says it isn't independent.** You ran it in the same session that just
made the change. Re-run `/speckit.loop.check` in a fresh session or as a separate
sub-agent so the checker doesn't inherit the maker's assumptions.

**`guard` won't mark the loop done.** It tells you which condition is unmet:
a criterion not `checker-pass`, blocking debt still open, or no recorded sign-off.
Resolve that one and re-run.

**The loop hit `max_iterations` with work left.** That ceiling is the guardrail
firing. Run `/speckit.loop.guard` for human review, raise `max_iterations`
deliberately if the goal genuinely needs more room, or sharpen the criteria.

**No `specs/` feature directory yet?** Commands fall back to
`.specify/loops/global/`.

**Does it call any external services?** No. The commands are prompt files; all
"infrastructure" is markdown in your repo. The only network access in the whole
lifecycle is your own `specify extension add --from <url>` download.

See [docs/concepts.md](docs/concepts.md) for the full mapping from Loop
Engineering to this extension and its honest limits.

## License

[MIT](LICENSE) © 2026 formin

Credits: *Loop Engineering* by Addy Osmani
([addyo.substack.com/p/loop-engineering](https://addyo.substack.com/p/loop-engineering));
[Spec Kit](https://github.com/github/spec-kit) by GitHub.
