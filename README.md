# RecallStack（回栈）

**把代码仓库转化为可学习、可练习、可复习的知识系统。**

- 中文宣传语：从调用栈，到知识栈。
- 英文宣传语：Turn codebases into lasting knowledge.

> RecallStack is built on top of [RepoWiki](https://github.com/he-yufeng/RepoWiki).

## 与普通代码 Wiki 的区别

| | 普通代码 Wiki | RecallStack |
|---|---|---|
| 目标 | 生成可读文档 | 形成可迁移的理解能力 |
| 交互 | 浏览 | 主动回忆、追踪、Teach Back |
| 反馈 | 无 / 弱 | 基于 rubric 的结构化评价 |
| 记忆 | 无 | FSRS 间隔复习 |
| 证据 | 可选 | 每个概念/题目必须有源码引用 |

## 与 RepoWiki 的关系

- `src/repowiki`：仓库知识引擎（扫描、依赖图、PageRank、Wiki、RAG、LiteLLM、缓存）
- `src/recallstack`：学习系统（概念图谱、学习路径、题目、提示、评价、掌握度、FSRS）
- 保留 RepoWiki 的 `repowiki scan` / `repowiki serve` 能力

## 当前功能（v0.1.0）

- 导入本地仓库或 HTTPS GitHub 仓库
- 扫描并生成概念图谱与“核心理解路径”
- 主动回忆 / 源码追踪 / Teach Back 题目
- 分级提示（1–5）与作答评价
- 掌握度 + FSRS 复习调度
- Dashboard 今日到期复习
- 版本变化时标记 stale 内容

## 架构

详见 [docs/architecture.md](docs/architecture.md)。

```
frontend (React/Vite)
   └─ /api/recallstack/*  →  recallstack application services
                              ├─ repowiki.core (scan/graph)
                              └─ learning DB (SQLite/Postgres)
```

## 安装

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[web,dev]"
cd frontend && npm install && cd ..
```

或：

```bash
make install
```

## 环境变量

复制 `.env.example`：

```bash
RECALLSTACK_DATABASE_URL=sqlite:///./data/recallstack.db
RECALLSTACK_DEFAULT_USER_ID=00000000-0000-4000-8000-000000000001
RECALLSTACK_FSRS_DESIRED_RETENTION=0.9
RECALLSTACK_MAX_REPOSITORY_SIZE_MB=200
RECALLSTACK_MAX_FILE_SIZE_KB=200
REPOWIKI_MODEL=
REPOWIKI_API_KEY=
REPOWIKI_API_BASE=
REPOWIKI_LLM_TIMEOUT_SECONDS=60
REPOWIKI_LLM_MAX_RETRIES=3
REPOWIKI_LANG=en
# optional override of REPOWIKI_LANG for learning/wiki templates:
# RECALLSTACK_CONTENT_LANG=zh
```

LLM key 可选：无 key 时仍可确定性生成概念/路径/题目。

内容语言与 RepoWiki 一致（`en` / `zh` / `ja` / `ko`），默认英文。改语言后需重新扫描仓库。

## 启动

后端：

```bash
python -m recallstack.cli serve --port 8000
# 或
repowiki serve --port 8000
```

前端：

```bash
cd frontend
npm run dev
```

- RepoWiki 首页：http://127.0.0.1:5173/
- RecallStack 学习：http://127.0.0.1:5173/learn

## 扫描本地仓库（学习流）

1. 打开 `/learn/repositories`
2. 选择「本地目录」，填入路径（可用 `fixtures/mini_repo`）
3. 创建 → 扫描/重新分析
4. 打开概念 → 开始练习 → 申请提示 → 提交

API：

```bash
curl -X POST http://127.0.0.1:8000/api/recallstack/repositories \
  -H "content-type: application/json" \
  -d "{\"source_type\":\"local\",\"source_location\":\"fixtures/mini_repo\"}"
```

## 数据库迁移

```bash
alembic upgrade head
# 开发态也会在服务启动时 bootstrap create_all
```

## 测试

```bash
make test
# 或
python -m pytest -q
```

## Lint / 构建

```bash
make lint
make frontend-build
```

## 已知限制

- 单用户模式（预留 `user_id`）
- 无 LLM 时题目文案为确定性模板
- 练习页源码片段预览目前主要支持本地仓库
- 评价默认确定性 rubric；LLM 评价脚手架已有但未接入主路径
- 符号级失效留待后续版本

## 路线图（按第一性原理排序）

1. **证据闭环**（已落地）：提示读码、练习页证据窗、路径/符号评分
2. **会话连贯性**（已落地）：概念练习队列 + 复习队列 + 下一题
3. **LLM 增强评价**（已落地，可选）：结构化评分 + 确定性回退；生成侧仍待接入
4. **LLM 增强概念/题目生成**（结构化缓存）
5. **符号级 stale 检测** + 版本 diff 学习
6. 多用户与进度同步；概念图可视化

## License

MIT（继承 RepoWiki）
