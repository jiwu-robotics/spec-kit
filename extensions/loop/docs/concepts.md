# Concepts: from Loop Engineering to Spec Kit

This document explains how the extension maps the ideas in **Loop Engineering**
(Addy Osmani, [addyo.substack.com/p/loop-engineering](https://addyo.substack.com/p/loop-engineering))
onto spec-driven development — and where it deliberately narrows them.

## The core idea

Loop Engineering names a shift: instead of prompting an agent by hand through
each turn, you *design the system that prompts the agent instead*. The unit of
that system is a **loop** — a recursive goal where you define a purpose and the
AI iterates until complete. The skill stops being "what do I type next" and
becomes "what loop did I build, and can I still stand behind what it ships."

The article pairs that with a warning it keeps returning to. Autonomy sharpens
three failure modes:

1. **Unattended verification** — work gets graded by no one, or by the very model
   that produced it ("the model that wrote the code is way too nice grading its
   own homework").
2. **Comprehension debt** — the loop changes more than you understand, and the
   gap compounds run over run.
3. **Cognitive surrender** — the slow drift toward accepting whatever the loop
   produced because checking it is work.

Its prescription: *build the loop, but build it like someone who intends to stay
the engineer.* This extension is that prescription turned into Spec Kit commands.
Spec-driven development already has a long-horizon, iterate-until-done shape
(make tasks pass, satisfy a spec); the extension gives that shape a contract, a
maker/checker split, externalized memory, and a sign-off gate.

## The components, mapped

The article lists the building blocks of a real loop. Here is where each lands.

| Loop Engineering component | In this extension |
|---|---|
| **Automations** — a loop runs without you holding the tool each turn | The contract's *automation trigger* + `/speckit.loop.run` as the driveable step; the extension records the intended trigger but schedules nothing itself |
| **Worktrees** — isolation so parallel agents don't collide | `loop.isolation: worktree`; `run` makes each iteration in its own git worktree and records the path |
| **Skills** — reusable project knowledge, so conventions aren't re-explained each cycle | `memory.md` — durable decisions, conventions, and dead ends carried across runs |
| **Plugins & connectors** — integrate the tools the work needs (MCP, etc.) | The contract's *allowed tools / connectors* allow-list; the maker may only reach for what is listed |
| **Sub-agents** — a separate agent for verification, so work isn't self-graded | `/speckit.loop.check` — an independent, adversarial checker with an explicit independence gate |
| **Persistent memory** — on disk, because the model forgets between runs | All loop state is `specs/<feature>/loop/*.md`; nothing of value lives in the conversation |

And the three failure modes map to the guardrails:

| Failure mode | Guardrail |
|---|---|
| Unattended verification | The maker/checker split + `verdicts.md`; `guard` flags low-confidence or non-independent passes |
| Comprehension debt | `debt.md` ledger; `guard`'s debt sweep; `block_done_on_open_debt` |
| Cognitive surrender | `guard`'s anti-surrender questions + the human sign-off gate that closes the loop |

## Mechanism notes

### A loop is a contract, written before it runs

`/speckit.loop.define` refuses to create a loop without **checkable
done-criteria**. "The AI iterates until complete" is only meaningful if
"complete" is defined as something a checker can pass or fail against a primary
source. An open-ended loop with no stop condition is precisely the shape that
drifts — so the contract is mandatory, not decorative.

### The maker never grades itself

`run` (maker) produces and records; it may mark a criterion `maker-ready` but
never `checker-pass` and never `done`. `check` (checker) is the only writer of
`verdicts.md`, runs adversarially against primary sources, and has an
independence gate that asks to be re-run in a fresh session when it shares the
maker's context. This is the article's central practice — splitting the maker
from the checker — enforced by which command may write which file.

### Closure is a human act

A passing checker is necessary but not sufficient. `/speckit.loop.guard` is the
only command that can set `Phase: done`, and only when checker-pass, no open
blocking debt, and a recorded human sign-off all hold. The sign-off is logged,
never fabricated — the agent surfaces the decision; the human makes it.

### State on disk, context disposable

Like any agent, each session starts empty — nothing changes that. What changes is
that the loop never kept its state in the conversation: the contract, every
iteration, every verdict, and every debt item are files. `/speckit.loop.status`
re-renders a bounded working slice into any new session, so a restart, a
compaction, or a teammate's agent resumes the loop without loss.

## Deliberate differences and honest limits

| | Loop Engineering (article) | This extension |
|---|---|---|
| Scope | General agentic engineering across a codebase and tools | The iterate-until-done loop inside one Spec Kit feature |
| Automations | Real schedulers, triage inboxes, PR bots | Records the intended trigger; does not schedule, open PRs, or run CI itself |
| Sub-agents | Genuinely separate processes | A convention + independence gate; true separation depends on the user running `check` in a fresh session/sub-agent |
| Enforcement | Whatever your harness enforces in code | Prompt-only: rules are mechanical and append-only, so drift is visible in the diff, but not impossible |

The honest caveat is the last row: a prompt-only extension cannot *force* the
maker and checker to be different processes, or force a human to truly read a
diff before signing off. What it can do is make the split, the budget, the debt,
and the sign-off **explicit and recorded**, so that skipping a guardrail is a
visible choice rather than a silent default. That visibility is the strongest
guarantee available without owning the runtime — and it is exactly the discipline
the article asks for.

## Relation to core Spec Kit artifacts

The loop never edits `spec.md`, `plan.md`, or `tasks.md`. It wraps the
build-and-verify portion of the workflow with discipline and records everything
beside the feature:

```
/speckit.tasks ──▶ tasks.md
                    │ (hook: after_tasks → loop.define)
        loop/  ◀── /speckit.loop.run   (maker iterations, externalized)
          │   ──▶ /speckit.loop.check  (independent adversarial verdicts)
          │
/speckit.implement ─┐ (hook: after_implement → loop.check)
                    ▼
            /speckit.loop.guard ──▶ comprehension-debt + human sign-off ──▶ done
```

Done means: criteria checker-passed, debt acknowledged, and a human who can still
explain what shipped. The loop did the iterating; you stayed the engineer.
