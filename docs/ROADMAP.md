# 优化路线图 / Roadmap

> 状态截至 2026-07-26。已完成的能力在下方"已完成"清单;其余按优先级排列,
> 每项都标注了动机与落点,方便任何一次会话直接接手。

## 已完成 (Done)

- **Wiki 主线**:Overview / Architecture / Reading Guide / 模块页 / 词条页;
  目录树 + ⌘K 全文搜索 + 页内 TOC + 面包屑 + 上一页/下一页;
  mermaid 架构图(按 PageRank 取最重的 12 个模块)+ 每个模块页自带依赖邻域图;
  源码引用点击内联展开(SourcePeek)。
- **Ask(DeepWiki 式向仓库提问)**:检索 top-4 页面 → LLM 带引用回答,
  无 key 时退化为抽取式答案;支持多轮追问(带上下文)。
- **学习辅助**:概念抽取、学习路径、词条页内 30 秒自测、FSRS 间隔复习;
  新概念自动进入复习队列(Anki 式),复习会话按概念串题。
- **流水线体验**:后台分析 + 轮询、逐模块进度('已分析模块 7/24')、
  中断任务启动时自动标记失败。
- **i18n 基建**:`frontend/src/lib/i18n.ts`(`useT()` 内联 zh/en 对,
  localStorage 持久化,顶栏 EN/中 切换);后端进度消息经 `t(en, zh)` 本地化。
  已覆盖:AppShell、AskPanel、CommandPalette、CodeBlock、MermaidDiagram、
  SourcePeek、TableOfContents、WikiContent、ConceptPracticePanel、FolderPicker、
  InlineProbe、DashboardPage、ReviewPage、RepositoryPage。

## 待办 (Planned)

### 1. i18n 收尾 — ConceptPage / LearningSessionPage
两个页面还是纯中文(各 ~44 条串)。照现有模式办:文件顶部
`import { tNow, useT } from "../lib/i18n";`,组件内 `const t = useT();`,
错误文案用 `tNow`。翻完后用
`grep -P "[\x{4e00}-\x{9fff}]"` 复查,中文只应出现在 `t("…", "…")` 第一参数里。

### 2. Wiki 内容语言跟随 UI 语言
后端 `RECALLSTACK_CONTENT_LANG` 已存在但只在分析时生效。计划:
`POST /analyze` 接受 `lang` 参数写进 version,前端重新扫描时带上当前语言;
Ask 已按提问语言回答,无需改动。

### 3. Ask 流式输出
`LLMClient.stream()` 已存在(httpx SSE)。给 `/ask` 加 SSE 端点,
AskPanel 用 EventSource 渐进渲染;保留现有非流式端点做降级。
注意 curl-first 的 TLS 说明:流式走 httpx,失败时回退非流式。

### 4. 词条页正文加深(向 DeepWiki 的长文看齐)
现在词条页较短。计划在 LLM enrich 阶段给高重要度概念生成
"实现细节 + 关键调用链 + 边界条件"三段,引用具体行号;
无 key 时保持现状(确定性内容不缩水)。

### 5. GitHub 仓库分析的健壮性
浅克隆缓存、分支选择、私有仓库 token(读 env,不入库);
失败时给出可操作的错误(当前只有 500 文本)。

### 6. 打包与分发
`pip install recallstack` 后 `recallstack serve` 一条命令可用;
前端构建产物已内嵌 `src/repowiki/server/static/`,补 entry_points 即可。

## 工程约定 (Conventions)

- 测试:`PYTHONPATH=src python -m pytest tests/ -q`;lint:`python -m ruff check .`;
  前端:`cd frontend && npx tsc --noEmit && npm run build`。
- 秘密:API key 只住 `.env`(已 gitignore),提交前
  `git grep -c --cached "sk-"` 应为 0。
- 确定性优先:任何 LLM 功能必须有无 key 降级路径。
- i18n:内联 `t(zh, en)` 对,不建 key 注册表;模块级常量存 `[zh, en]` 元组,
  渲染时经 `t(...pair)` 取值。
