# Changelog

All notable changes to the Loop Engineering extension are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-08-26

### Added

- Bundle the extension with `jiwu-robotics/spec-kit`, including the governed and
  yolo workflow assets and the built-in `loop-state` workflow step.
- `/speckit.loop.flow` — a Codex-session bridge that starts or resumes the
  registered `speckit-loop` and `speckit-loop-yolo` workflows.

## [1.0.0] - 2026-06-14

### Added

- Initial release, operationalizing **Loop Engineering** (Addy Osmani,
  [addyo.substack.com/p/loop-engineering](https://addyo.substack.com/p/loop-engineering))
  for spec-driven development: a loop is a recursive goal you define once and an
  agent iterates until complete — built "like someone who intends to stay the engineer."
- `/speckit.loop.define` — capture a loop as a contract (purpose, explicit
  done-criteria, iteration budget, maker/checker roles, allowed tools, guardrails)
  and create the externalized state files (`loop.md`, `iterations.md`,
  `verdicts.md`, `debt.md`, `memory.md`).
- `/speckit.loop.run` — run maker iterations toward the goal, externalizing each
  iteration to disk; the maker never grades itself and stops to hand off to the checker.
- `/speckit.loop.check` — independent, adversarial checker pass that grades the
  latest iteration against every done-criterion and records a durable verdict;
  enforces the maker/checker split.
- `/speckit.loop.guard` — stay-the-engineer checkpoint: surfaces comprehension
  debt and unattended-verification risk, and gates "done" behind explicit human sign-off.
- `/speckit.loop.status` — compact, budget-aware rendering of loop state with one
  recommended next action; safe session resume.
- Optional hooks: `after_tasks` → `speckit.loop.define`,
  `after_implement` → `speckit.loop.check`.
- `config-template.yml` for iteration budgets, maker/checker policy, guardrail
  toggles, and rendering slice sizes.
