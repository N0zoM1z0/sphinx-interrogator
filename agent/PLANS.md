# Execution plans for this repository

An **ExecPlan** is a self-contained, living implementation document for work that spans several modules, requires design discovery, or cannot be completed safely in one small edit. The active full-system plan is `agent/plans/0001-full-system.md`.

## When an ExecPlan is required

Use an ExecPlan for:

- a new milestone in `agent/CODEX_TASK_SPEC.md`;
- semantic or protocol changes;
- a new synthesis/statistics/learning backend;
- substantial refactors;
- benchmark-driven tuning;
- work expected to need multiple test/repair cycles.

Tiny local fixes may update only `agent/STATUS.md`, but they must still preserve the active plan's assumptions.

## Operating rules

1. Read this file and the full active plan before implementation.
2. Keep the plan usable by a developer who has only the repository and no conversation history.
3. State the user-visible behavior and evidence before listing code edits.
4. Define unfamiliar terms in place.
5. Name concrete files, functions, commands, and expected observations.
6. Break work into independently verifiable milestones.
7. Update progress, discoveries, decisions, and outcomes as facts change.
8. Resolve ordinary ambiguities using the product specification and record the decision.
9. Do not stop after writing a plan; execute it through the next unblocked milestone.
10. Never claim completion from code inspection alone. Run the stated verification surface.

## Required sections

Every plan contains:

- `Purpose / Big Picture`
- `Scope and Non-Goals`
- `Current Repository State`
- `Progress` with timestamped checkboxes
- `Surprises & Discoveries`
- `Decision Log`
- `Milestones`
- `Concrete Implementation Steps`
- `Validation and Acceptance`
- `Recovery and Idempotence`
- `Artifacts and Evidence`
- `Interfaces and Dependencies`
- `Outcomes & Retrospective`

## Content standards

### Purpose and behavior

Explain what a user/researcher can do after completion and the shortest demonstration that proves it. Avoid framing the outcome only as files or classes.

### Progress

Use checkboxes with UTC dates. Split partially completed work into completed and remaining items. Keep this section current after every meaningful work interval.

### Discoveries

Record unexpected behavior, performance results, failed assumptions, and small command excerpts that justify course changes. Do not hide negative results.

### Decisions

For each material decision, record:

```text
Decision:
Rationale:
Alternatives considered:
Date/author:
Consequences:
```

### Milestones

Each milestone states:

- outcome;
- files/components involved;
- implementation sequence;
- tests/commands;
- observable acceptance condition;
- dependencies and rollback path.

Milestones should demonstrate working vertical slices where possible. For algorithmic uncertainty, include a reduced-domain prototype before the production implementation.

### Concrete steps

Name repository-relative paths and symbols. Commands are shown as indented text with their working directory and expected success/failure. Do not rely on external context that is absent from the repository.

### Validation

Distinguish:

- unit/property tests;
- cross-language/process tests;
- formal checks;
- end-to-end demos;
- benchmark/evaluation evidence;
- safety/boundary audits.

If a tool is unavailable, record the attempted command and implement/execute every fallback that still provides useful evidence. Unavailable evidence remains a blocker, not a pass.

### Recovery

Steps should be safe to repeat. Describe how to resume after an interrupted database migration, campaign, or generated artifact. Never require deleting uncommitted user work.

## Plan format

Each checked-in ExecPlan should be a single Markdown document. To make accidental nesting or truncation unlikely in agent prompts, this repository's plans place their full contents inside one outer fenced block labeled `md`. Commands and snippets inside use indentation rather than nested fences.

## Template

Copy the following structure into a new file under `agent/plans/` and fill every section.

    # <Action-oriented plan title>

    This ExecPlan is maintained under `agent/PLANS.md`.

    ## Purpose / Big Picture

    <Behavior and demonstration.>

    ## Scope and Non-Goals

    <Included and explicitly excluded work.>

    ## Current Repository State

    <Relevant files, behavior, and known gaps.>

    ## Progress

    - [ ] (YYYY-MM-DD HH:MMZ) <work item>

    ## Surprises & Discoveries

    - Observation: <fact>
      Evidence: <command/output/artifact>

    ## Decision Log

    - Decision: <choice>
      Rationale: <why>
      Alternatives considered: <others>
      Date/author: <date and agent/human>
      Consequences: <follow-on effects>

    ## Milestones

    ### Milestone 1 — <vertical outcome>

    <Implementation and acceptance.>

    ## Concrete Implementation Steps

    <Ordered edits and commands with working directories.>

    ## Validation and Acceptance

    <Exact commands and observed behavior.>

    ## Recovery and Idempotence

    <Safe retry/resume/rollback guidance.>

    ## Artifacts and Evidence

    <Run directories, reports, logs, and hashes.>

    ## Interfaces and Dependencies

    <Stable APIs, schemas, dependency choices.>

    ## Outcomes & Retrospective

    <Completed behavior, remaining gaps, lessons.>
