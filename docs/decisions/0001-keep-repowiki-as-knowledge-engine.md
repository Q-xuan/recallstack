# 0001. Keep RepoWiki as knowledge engine

## Context

RecallStack needs repository scanning, dependency graphs, and optional wiki generation.

## Decision

Keep `src/repowiki` intact as the knowledge engine. Add `src/recallstack` for learning workflows.

## Consequences

- No large-scale rename of RepoWiki modules
- `repowiki scan/serve` continue to work
- Learning features integrate via public imports
