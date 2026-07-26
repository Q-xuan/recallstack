# Data Model

Primary entities:

- `repositories` / `repository_versions`
- `concepts` / `concept_edges`
- `learning_paths` / `learning_path_nodes`
- `learning_items`
- `attempts`
- `mastery`
- `review_logs`
- `users` (default single user)

All source-backed content stores `source_references`:

```json
{
  "path": "src/example.py",
  "start_line": 10,
  "end_line": 36,
  "symbol": "ExampleService.run",
  "commit_sha": "..."
}
```

Alembic migration: `alembic/versions/0001_initial_recallstack.py`.
