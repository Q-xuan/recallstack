# Overview

Relevant source files

DeepSeek Harness (`dsh`) is an open-source, plugin-based agent harness developed by DeepSeek AI. It is designed to be a flexible and extensible foundation for building, testing, and deploying LLM agents.

At its core, `dsh` adopts an everything-is-a-plugin philosophy. It is powered by a vendored version of the Cordis framework, which allows every component—from model adapters and tool registries to the agent loop itself—to be replaced or extended through configuration.

### Core Philosophy: The Capability Seam

The architecture is built around "Capability Seams." A seam is a swappable capability defined by three roles:

1. Service Definition: Declares the interface (e.g., `ctx.llm`, `ctx.fs`).
2. Service Provider: Implements the interface (e.g., `llm-deepseek`, `fs-local`).
3. Consumer: Uses the capability, often a model-facing tool (e.g., `tool-bash` consuming the shell capability).

This pattern allows the entire behavior of the agent to change by swapping a single provider, such as moving from a local filesystem to a remote sandboxed environment.

### System Architecture: Code to Concept Map

The following diagram bridges the high-level concepts of the agent's "Natural Language Space" with the "Code Entity Space" (the specific classes and services implementing them).

### Monorepo Layout & Navigation

`dsh` is organized as a pnpm monorepo. It separates core logic, API layers, UI components, and various capability providers into distinct package families.

#### Key Directories:

- `apps/`: Entry points like the `dsh` CLI
- `packages/core/`: The product API spine including the session log and agent loop
- `packages/llm/`: LLM service definitions and provider adapters
- `vendor/`: The internal source of the Cordis framework
