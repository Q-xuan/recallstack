# Demo Walkthrough

## Prerequisites

```bash
python -m pip install -e ".[web,dev]"
cd frontend && npm install && cd ..
```

## Start

Terminal 1:

```bash
python -m recallstack.cli serve --port 8000
```

Terminal 2:

```bash
cd frontend && npm run dev
```

Open `http://127.0.0.1:5173/learn`.

## Flow

1. Go to **仓库** (`/learn/repositories`)
2. Source type = 本地目录
3. Path = this project root (or `fixtures/mini_repo` if present)
4. Create repository
5. Click **扫描 / 重新分析**
6. Wait until status = `ready`
7. Confirm ≥ 5 concepts and a learning path
8. Open first concept → **开始练习**
9. Request one hint
10. Submit an answer with confidence
11. Observe structured feedback, mastery, `next_review_at`
12. Open Dashboard / 今日复习

## API-only demo

```bash
curl -s http://127.0.0.1:8000/api/recallstack/health
curl -s -X POST http://127.0.0.1:8000/api/recallstack/repositories \
  -H "content-type: application/json" \
  -d "{\"source_type\":\"local\",\"source_location\":\".\"}"
```

Then call `/analyze?wait=true`, `/concepts`, `/items/{id}/attempts`.
