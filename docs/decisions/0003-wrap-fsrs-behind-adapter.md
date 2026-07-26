# 0003. Wrap FSRS behind adapter

## Context

FSRS library types should not leak into domain logic.

## Decision

Define `ReviewScheduler` protocol and implement `FSRSReviewScheduler` adapter. Persist cards/logs as JSON.

## Consequences

- Domain/tests can mock scheduler
- Library upgrades stay localized
