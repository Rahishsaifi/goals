# Agent notes

Product: recruitment-intelligence. Workspace root is the monorepo.

## Non-negotiable

- Azure free tier only. Read `.cursor/rules/azure-free-tier.mdc` before any Azure command.
- Subscription is pay-as-you-go with spending limit Off. Do not create paid resources.
- Do not claim a feature, test, or deployment works unless it was executed.
- Do not fabricate token counts, scores, search hits, or benchmark results.
- Tenant id, role, and ownership come from the server session, never from the browser.
- Deterministic Python owns weighted scores. Models may only extract and assess evidence.
- Missing evidence is unknown, not a failed qualification.
- Mock AI is allowed only when explicitly configured, and it must be visible. Never fall back to it when a live call fails.

## Resume here

`docs/implementation-plan.md` is the checkpoint. Continue at the "Next action" in that file. Do not redo finished phases.
