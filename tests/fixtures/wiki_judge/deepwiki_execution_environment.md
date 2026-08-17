# Execution Environment

Relevant source files

The execution environment is the sandboxed world an agent acts in. Filesystem, shell, and terminal capabilities are Capability Seams: a Service Definition (`ctx.fs`, `ctx.shell`, `ctx.terminals`), a Service Provider (`fs-local`, `shell-local`), and Consumers (`tool-bash`, `tool-read`).

Swapping the provider — local disk to a remote sandbox — moves Bash, PTY, and LSP with it. The loop does not import those backends.

## Architecture

A call that needs the filesystem goes: tool schema on `ctx.tools` → Consumer (`tool-read`) → Service Definition (`ctx.fs`) → Service Provider. The same seam pattern applies to `ctx.shell` and `ctx.subprocess`.

## Key types

- `ctx.fs` — filesystem Service Definition
- `ctx.shell` — shell Service Definition; the local backend spawns through `ctx.subprocess`
- `ctx.sandbox` — confines spawned processes; consumers wrap argv before spawn

## Boundaries

This page is the execution world, not the Agent Loop. The loop asks for a tool; the seam decides where bytes and processes actually go.
