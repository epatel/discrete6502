---
name: backward-planning
description: Plan by reasoning backwards from a vivid success outcome to the goals that produce it. Use when the user wants to "plan", "figure out how to get to X", "work backward", "start with the end in mind", "what needs to be true for", or when scoping a feature, project, migration, or roadmap. Especially useful when the destination is clearer than the path, or when forward brainstorming is producing scattered tasks without a shared target.
---

# Backward Planning

Forward planning ("what should we do next?") tends to drift — tasks accumulate without a shared target. Backward planning fixes the destination first, then derives the goals that must be true to reach it. This skill enforces that order.

## When to use

- User asks: "how do I get to X", "plan this", "what's the path to Y", "work backwards from", "what would it take to ship Z".
- Scoping a non-trivial feature, migration, refactor, launch, or research initiative.
- A forward task list is sprawling and you suspect the goal is fuzzy.
- Decisions feel arbitrary because there's no defined "done."

Skip for one-shot fixes, single-file edits, or anything where the action is the goal.

## The method

Run these four phases **in order**. Do not skip phase 1 — without a concrete success picture, the rest collapses into ordinary forward planning.

### Phase 1 — Visualize the outcome

Write a vivid, concrete description of the world *after* this is successful. Force specificity:

- **What does a user/operator/reader observe?** (Screens, logs, metrics, behaviors, artifacts.)
- **What is measurably true?** (Numbers, thresholds, SLAs, coverage, dollars, users.)
- **What is no longer true?** (Pain that's gone, code that's deleted, alerts that stopped firing.)
- **Who notices, and how?** (Stakeholders, customers, on-call.)

Output 3–7 bullets. If you can't picture it sharply, ask the user clarifying questions before continuing — a vague outcome guarantees a vague plan.

### Phase 2 — Define success criteria

Convert the visualization into checkable criteria. Each criterion must be:

- **Observable** — someone could verify it without asking the implementer.
- **Binary or thresholded** — done/not-done, or `≥ N`, not "better."
- **Independent of the path** — describes the *end state*, not the work.

Bad: "Refactored the auth module." Good: "All login flows route through `AuthService.authenticate`; no callsite imports `legacy_auth.*`; p95 login latency ≤ 200ms."

### Phase 3 — Reason backwards (preconditions chain)

Starting from each success criterion, repeatedly ask: **"What must be true immediately before this is true?"** Keep asking until you hit something that is true today or is a trivial first step.

Build a tree (or DAG if branches converge). Nodes are *states*, not actions. Example:

```
Success: Users can log in via SSO
  ← SSO provider returns valid tokens for our app
    ← App is registered with provider + secrets in vault
      ← Vault entry exists (today: doesn't)
    ← Callback route validates tokens
      ← JWT verification library wired up (today: not installed)
  ← Legacy login still works during cutover
    ← Feature flag gates the new path (today: flag doesn't exist)
```

Two rules that keep this honest:

1. **State, not verb.** "Tokens are validated" not "validate tokens." States compose; verbs hide assumptions.
2. **Stop at the truth boundary.** When a precondition is already true, mark it and stop expanding that branch. That's your starting edge.

### Phase 4 — Derive goals from the chain

Walk the tree from the leaves (true-today) toward the root (success). Each *edge* — the transition from one state to the next — becomes a goal.

For each goal, capture:

- **Name** — short, outcome-shaped ("Vault entry provisioned", not "do vault stuff").
- **Done when** — the precondition state it produces, copied from the tree.
- **Depends on** — the upstream nodes that must already be true.
- **Roughly** — size estimate (S/M/L) and one-line approach.

Order goals by dependency. Parallelizable branches surface naturally — call them out so the user can fan out work.

## Output format

Return four sections in this order:

1. **Outcome** — the visualization (phase 1).
2. **Success criteria** — checkable list (phase 2).
3. **Precondition tree** — mermaid graph or indented bullets (phase 3). Use mermaid if there are branches; bullets if linear.
4. **Goals** — ordered list with the four fields above (phase 4). Mark independent branches `[parallel: A]`, `[parallel: B]`.

Keep each section tight. The point is clarity of destination and dependency, not exhaustive detail — implementation specifics belong in the goals' own plans, not here.

## Anti-patterns to refuse

- **Skipping phase 1.** "Let's just list tasks" is forward planning in disguise. Push back and visualize first.
- **Verbs as nodes.** "Write tests," "refactor module" — these don't compose into a precondition chain. Rephrase as states ("tests exist and pass," "module exposes only the new API").
- **Infinite regress.** If the tree keeps expanding, you're either at the wrong altitude (zoom out) or the outcome isn't actually defined (return to phase 1).
- **Goal = outcome.** If your only goal restates the success criterion, you haven't decomposed anything. Find at least one non-trivial precondition.

## Quick mode

For small tasks (≤ half a day of work) the user can ask for "quick backward planning." Compress to:

1. One-sentence outcome.
2. 2–3 success criteria.
3. Linear precondition list (no tree).
4. Ordered goals, no size estimates.

Still phase 1 first. The shortcut is in depth, not in order.
