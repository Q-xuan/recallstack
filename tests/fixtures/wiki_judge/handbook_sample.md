# Agent Loop

> Agent Loop 是 harness 里跑一轮对话的驱动：收输入、调模型、执行 tool call、写回，再决定是否进入下一轮。

**相关源码:** `packages/core/agent-loop/src/loop.ts:40 ReactLoopAgent`

## 概述

DeepSeek Harness（`dsh`）把 Agent Loop 做成可替换 plugin。默认驱动挂在 `ctx.agentLoop`，实现 `Agent` 接口。

## 架构

架构围绕 Capability Seam。一个 seam 是可替换能力，三角色是 Service Definition、Service Provider、Consumer。

## 关键类型

- `ReactLoopAgent` — 默认驱动 — `packages/core/agent-loop/src/loop.ts:40 ReactLoopAgent`
- `Agent` — 接口，不是「代理人」这个译名

## 边界

这页讲循环本身，不讲 filesystem / sandbox 那些 execution seam。plugin 在官方中文里写作插件，identifier 仍是 plugin。
