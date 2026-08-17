# Overview

Relevant source files

The `grok-build` codebase is a terminal-based AI coding assistant and agentic harness. It provides a stateful, tool-augmented environment for interacting with Large Language Models (LLMs). The system is used as an interactive Terminal User Interface (TUI), a headless CLI, or a backend agent service over the Agent Client Protocol (ACP).

### Primary Operational Modes

- Interactive TUI: a full-screen terminal application for conversational coding
- Headless Mode: a non-interactive mode for scripting and CI
- Agent Mode: ACP over `stdio`, so IDEs can drive the agent

## Major Subsystems

### 1. The Shell and Session Layer

The `xai-grok-shell` crate manages the lifecycle of a session. It coordinates session state, persistence, and communication between the user and the LLM.

### 2. The Agent and Prompting System

Agents are defined and orchestrated within `xai-grok-agent`, which handles system prompt assembly and agent discovery.

### 3. Tool Runtime and Sandboxing

Grok executes actions through a unified tool runtime in `xai-grok-tools`, including `bash`, `read_file`, and `search_replace`. Safety is managed via `xai-grok-sandbox`.

### 4. Workspace and Worktrees

The `xai-grok-workspace` crate abstracts the host filesystem, VCS, execution environments, and checkpoints.

### 5. TUI Pager

The `xai-grok-pager` crate implements the interactive interface: scrollback buffer, prompt input, modal dialogs, and rendering of Markdown and Mermaid diagrams.

## Repository Organization

| Directory | Purpose |
| --- | --- |
| `crates/codegen/xai-grok-pager` | TUI: scrollback, prompt, modals, rendering |
| `crates/codegen/xai-grok-shell` | Agent runtime and leader/stdio/headless entry |
| `crates/codegen/xai-grok-tools` | Tool implementations |
| `crates/codegen/xai-grok-workspace` | Host filesystem, VCS, execution, checkpoints |
