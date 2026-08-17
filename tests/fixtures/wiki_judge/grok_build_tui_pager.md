# TUI Pager

Relevant source files

- `crates/codegen/xai-grok-pager`
- `crates/codegen/xai-grok-pager-bin`

The `xai-grok-pager` crate implements the interactive interface, including the scrollback buffer, prompt input, modal dialogs, and rendering of Markdown and Mermaid diagrams.

## Overview

The pager is the TUI canvas. Streaming model output lands in the scrollback buffer; the prompt is a separate input surface. TUI is one door onto the same turn — it does not own a second model call.

## Architecture

`xai-grok-pager` paints tokens as they arrive. ACP `connect` is the other door. Both doors share later turn, tools, and write-back.

## Key types

- `xai-grok-pager` — TUI implementation: scrollback, prompt, modals, rendering
- `xai-grok-pager-bin` — composition-root package that builds the pager binary
