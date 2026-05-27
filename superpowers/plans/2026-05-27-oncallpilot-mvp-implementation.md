# OnCallPilot 首发版本实施计划

> **执行者须知**：本计划按 Phase / Task / Step 三级组织，使用 `- [ ]` 复选框跟踪。建议配合 superpowers `subagent-driven-development` 或 `executing-plans` 技能逐 Task 推进。每个 Task 内的 Step 都按 TDD（先写失败测试 → 实现 → 复跑通过 → commit）展开。

**目标**：交付一个企业级 on-call 智能调查平台首发版本，覆盖告警接入、异步 LangGraph 调查、证据链审计、运行手册 RAG、事故记忆、GitHub 修复建议、HealthCheck / ScheduledHealthCheck / ServiceCatalog 三 CRD、SSE 实时 dashboard，以及参考工作负载与端到端验证。

**架构**：FastAPI 模块化单体（apps/api）+ arq Worker（apps/worker）+ kopf Controller（apps/controller）+ Next.js Dashboard（apps/web）+ 参考工作负载（samples/payment-api）+ Helm Chart 唯一交付形态。

**技术栈**：Python 3.12、FastAPI、SQLAlchemy 2.x async、Alembic、PostgreSQL + pgvector、Redis、arq、LangGraph、`openai` SDK（OpenAI 协议兼容）、Langfuse、kopf、Next.js（App Router）+ pnpm + next-intl、Helm。所有外部基础设施由运营者自行准备并通过 `config/oncallpilot.yaml` 注入。

**Phase 列表**：

1. Backend Skeleton & Config
2. Persistence Schema
3. Tool Layer Foundation
4. Worker & Async Investigation Pipeline
5. Alertmanager Webhook & Incident APIs
6. RAG & Incident Memory
7. LangGraph Investigation Loop
8. GitHub Tool & Remediation
9. CRDs & Controller
10. Helm Chart & Kubernetes Delivery
11. Reference Workload (samples/payment-api)
12. Dashboard
13. End-to-End Reference Scenario Validation
14. Scenario Automation with chaos-mesh （Deferred，不计入 MVP 验收）

---

## 全局 File Map

- `apps/api/` — FastAPI 服务、tool 适配器、agent、持久化、observability。
- `apps/worker/` — arq worker，复用 `apps/api` 的 agent / tools / repositories。
- `apps/controller/` — kopf controller，watch 三个 CRD。
- `apps/web/` — Next.js Dashboard。
- `samples/payment-api/` — 参考工作负载。
- `deploy/helm/oncallpilot/` — 唯一交付形态。
- `deploy/scenarios/payment-api-high-error-rate/` — Phase 14 chaos-mesh 资源。
- `config/oncallpilot.example.yaml` — 配置示例。
- `docs/runbooks/*.md` — 内置 5 篇中文 runbook。
- `docs/scenarios/payment-api-high-error-rate/` — 端到端验证文档。
- `scripts/seed_runbooks.py` / `scripts/seed_incident_memory.py` / `scripts/run_scenario_payment_api_high_error_rate.py`。

---

## Phase 1: Backend Skeleton & Config

**目标**：FastAPI 进程能起来、能加载 YAML 配置、提供 `/healthz` 与 `/readyz`，Tracer 与 EventBus 接口骨架到位（NoOp 实现），Dockerfile 完成。

**Files：**

- Create `apps/api/pyproject.toml`
- Create `apps/api/oncallpilot_api/__init__.py`
- Create `apps/api/oncallpilot_api/main.py`
- Create `apps/api/oncallpilot_api/config.py`
- Create `apps/api/oncallpilot_api/dependencies.py`
- Create `apps/api/oncallpilot_api/observability/tracer.py`
- Create `apps/api/oncallpilot_api/services/event_bus.py`
- Create `apps/api/oncallpilot_api/api/__init__.py`
- Create `apps/api/oncallpilot_api/api/routes_health.py`
- Create `apps/api/Dockerfile`
- Create `config/oncallpilot.example.yaml`
- Test `apps/api/tests/unit/test_health.py`
- Test `apps/api/tests/unit/test_config_loader.py`

### Task 1.1 失败优先的健康检查 API

- [ ] **Step 1**：写失败测试

```python
# apps/api/tests/unit/test_health.py
from fastapi.testclient import TestClient
from oncallpilot_api.main import create_app

def test_healthz_returns_ok(monkeypatch, tmp_path):
    cfg = tmp_path / "oncallpilot.yaml"
    cfg.write_text(MINIMAL_VALID_YAML)
    monkeypatch.setenv("ONCALLPILOT_CONFIG", str(cfg))
    monkeypatch.setenv("POSTGRES_URL", "postgresql+asyncpg://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")

    client = TestClient(create_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2**：跑测试确认失败
  - 命令：`cd apps/api && uv run pytest tests/unit/test_health.py -v`
  - 期望：因为 `oncallpilot_api.main` 不存在而失败。

- [ ] **Step 3**：建 pyproject 与依赖

```toml
[project]
name = "oncallpilot-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.110",
  "uvicorn[standard]>=0.27",
  "pydantic>=2.6",
  "pydantic-settings>=2.2",
  "pyyaml>=6.0",
  "structlog>=24.1",
  "sqlalchemy[asyncio]>=2.0",
  "asyncpg>=0.29",
  "alembic>=1.13",
  "pgvector>=0.2",
  "httpx>=0.27",
  "redis>=5.0",
  "arq>=0.25",
  "openai>=1.30",
  "langgraph>=0.0.40",
  "langchain-core>=0.2",
  "langfuse>=2.0",
]

[dependency-groups]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21", "ruff>=0.4"]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 4**：实现 `config.py`、`main.py`、`routes_health.py`（含 `/healthz` 与 `/readyz` 骨架；`/readyz` 暂只检查配置加载成功）。

- [ ] **Step 5**：跑测试确认通过。

- [ ] **Step 6**：commit

```bash
git add apps/api config/oncallpilot.example.yaml
git commit -m "feat(api): bootstrap fastapi skeleton with healthz"
```

### Task 1.2 YAML 配置加载器（含 env_ref 与 fail-fast）

- [ ] **Step 1**：写失败测试覆盖

  - 缺 `ONCALLPILOT_CONFIG` → 启动失败并报清晰错误。
  - 配置中 `*_env: VAR_NAME` 字段在缺失环境变量时 → fail-fast。
  - 数据源、LLM、agent、worker、observability、i18n、events 各节字段被正确解析。
  - `embedding_dim` 与 `embedding_model` 同时存在。

- [ ] **Step 2**：跑测试确认失败。

- [ ] **Step 3**：实现 `YamlConfigSettingsSource`（基于 pydantic-settings 自定义 source），约 50 行代码；`Settings` 顶层模型对应 spec §5.2 schema。

- [ ] **Step 4**：实现 `dependencies.py` 提供 `get_settings()` 单例。

- [ ] **Step 5**：跑测试通过；同时手动 `uv run python -c "from oncallpilot_api.config import get_settings; print(get_settings())"` 验证。

- [ ] **Step 6**：commit

```bash
git add apps/api/oncallpilot_api/config.py apps/api/oncallpilot_api/dependencies.py apps/api/tests/unit/test_config_loader.py
git commit -m "feat(api): yaml config loader with env_ref and fail-fast"
```

### Task 1.3 Tracer / EventBus 接口骨架（NoOp 默认实现）

- [ ] **Step 1**：写测试，验证 `NoOpTracer` 所有方法可调用不抛、`NoOpEventBus.publish/subscribe` 行为符合 Protocol。

- [ ] **Step 2**：跑测试确认失败。

- [ ] **Step 3**：实现 `observability/tracer.py`（`Tracer` Protocol + `NoOpTracer` + `LangfuseTracer` stub，stub 仅在 Phase 6/7 真接 Langfuse SDK 时实装）。

- [ ] **Step 4**：实现 `services/event_bus.py`（`EventBus` Protocol + `NoOpEventBus` + `RedisPubSubEventBus` stub，stub 在 Phase 4 真接 Redis）。

- [ ] **Step 5**：在 `dependencies.py` 中根据配置选择 Tracer/EventBus 实现，默认 NoOp。

- [ ] **Step 6**：测试通过 → commit

```bash
git add apps/api/oncallpilot_api/observability apps/api/oncallpilot_api/services/event_bus.py apps/api/tests
git commit -m "feat(api): tracer and event_bus protocol skeleton"
```

### Task 1.4 Dockerfile 与最小可运行验证

- [ ] **Step 1**：写 `apps/api/Dockerfile`（multi-stage、`uv sync --frozen`、非 root、暴露 8080）。

- [ ] **Step 2**：本地构建：`docker build -t oncallpilot-api:dev apps/api`。

- [ ] **Step 3**：用临时配置文件 + env 启动镜像，curl `/healthz`，确认 200。

- [ ] **Step 4**：commit

```bash
git add apps/api/Dockerfile
git commit -m "build(api): add multi-stage dockerfile"
```

---

## Phase 2: Persistence Schema

**目标**：初始 Alembic migration 一次性建出 spec §7 中**不含向量列**的所有表（含 fingerprint 幂等索引、verdict 字段、tool_calls 跨指 CHECK 等），SQLAlchemy 模型与基础 repository 函数到位。

**Files：**

- Create `apps/api/oncallpilot_api/db/__init__.py`
- Create `apps/api/oncallpilot_api/db/session.py`
- Create `apps/api/oncallpilot_api/db/models.py`
- Create `apps/api/oncallpilot_api/db/repositories.py`
- Create `apps/api/alembic.ini`
- Create `apps/api/oncallpilot_api/db/migrations/env.py`
- Create `apps/api/oncallpilot_api/db/migrations/versions/<rev>_initial.py`
- Test `apps/api/tests/unit/test_models_shape.py`
- Test `apps/api/tests/integration/test_migrations.py`

### Task 2.1 模型与基础约束

- [ ] **Step 1**：写测试，断言每个模型的关键列、UNIQUE/CHECK、关系映射存在（如 `tool_calls` 的 `investigation_session_id` 与 `chat_session_id` 互斥约束、`incidents` 的 fingerprint 部分唯一索引）。

- [ ] **Step 2**：跑测试确认失败。

- [ ] **Step 3**：实现 `session.py`（async engine + sessionmaker + `get_db_session` 依赖）。

- [ ] **Step 4**：实现 `models.py`：`DatasourceStatus`、`Incident`、`InvestigationSession`、`ChatSession`、`ChatMessage`、`ToolCall`、`RunbookDocument`、`IncidentMemory`（暂不带 embedding 列）、`RemediationAction`、`ServiceCatalogEntry`。
  - 所有状态字段使用 Python 端常量集合做校验（如 `INCIDENT_STATUSES = {"open","investigating","resolved","error"}`），不引入数据库 ENUM。
  - JSONB 字段使用 `sqlalchemy.dialects.postgresql.JSONB`。

- [ ] **Step 5**：测试通过 → 进入下一 Task。

### Task 2.2 Alembic 初始 migration

- [ ] **Step 1**：`uv run alembic init oncallpilot_api/db/migrations`，配置 `env.py` 使用 async engine + autogen 关闭（手写 migration 更可控）。

- [ ] **Step 2**：写集成测试 `tests/integration/test_migrations.py`：
  - 依据 `ONCALLPILOT_CONFIG` 取真实 Postgres URL；缺失则 `pytest.skip`。
  - 在 schema 空库执行 `alembic upgrade head`，断言所有表与索引均创建成功，可成功 downgrade。

- [ ] **Step 3**：手写 `versions/<rev>_initial.py`，按 spec §7 创建所有非向量表 + 部分唯一索引 + CHECK 约束 + 必要的二级索引。
  - 启用 `CREATE EXTENSION IF NOT EXISTS "pgcrypto";`（UUID 生成）。
  - 不启用 pgvector（留待 Phase 6）。

- [ ] **Step 4**：本地准备 Postgres，跑：`INTEGRATION_TESTS=1 ONCALLPILOT_CONFIG=... uv run pytest tests/integration/test_migrations.py -v`，确认 upgrade/downgrade 都成功。

- [ ] **Step 5**：commit

```bash
git add apps/api/oncallpilot_api/db apps/api/alembic.ini apps/api/tests
git commit -m "feat(db): initial schema with idempotency indexes and verdict fields"
```

### Task 2.3 基础 Repository 函数

- [ ] **Step 1**：写集成测试覆盖 repository：`create_incident_with_fingerprint_dedup`、`upsert_datasource_status`、`create_investigation_session`、`append_tool_call`、`mark_incident_resolved`、`list_recent_incidents`、`get_investigation_detail`、`create_chat_session/append_chat_message`。

- [ ] **Step 2**：跑测试确认失败。

- [ ] **Step 3**：实现 `repositories.py`，全部使用 async API。
  - `create_incident_with_fingerprint_dedup`：返回 `(incident, created: bool)`；命中已有 open/investigating → 不重建，只刷新 `last_seen_at`。

- [ ] **Step 4**：测试通过 → commit

```bash
git add apps/api/oncallpilot_api/db/repositories.py apps/api/tests
git commit -m "feat(db): repository helpers for incidents, sessions, tool_calls, chat"
```

---

## Phase 3: Tool Layer Foundation

**目标**：`ToolResult` 接口、`ToolRegistry`、Prometheus / Loki / Connectivity 真实适配器（HTTP via httpx）、`audit_service` 全部到位；单元测试用 `respx` mock HTTP，集成测试连真 Prom/Loki。

**Files：**

- Create `apps/api/oncallpilot_api/tools/__init__.py`
- Create `apps/api/oncallpilot_api/tools/base.py`
- Create `apps/api/oncallpilot_api/tools/registry.py`
- Create `apps/api/oncallpilot_api/tools/prometheus.py`
- Create `apps/api/oncallpilot_api/tools/loki.py`
- Create `apps/api/oncallpilot_api/tools/connectivity.py`
- Create `apps/api/oncallpilot_api/services/audit_service.py`
- Create `apps/api/oncallpilot_api/services/datasource_service.py`
- Create `apps/api/oncallpilot_api/api/routes_datasources.py`
- Test `apps/api/tests/unit/test_tool_result.py`
- Test `apps/api/tests/unit/test_prometheus_tool.py`（respx mock）
- Test `apps/api/tests/unit/test_loki_tool.py`
- Test `apps/api/tests/unit/test_connectivity_tool.py`
- Test `apps/api/tests/integration/test_prometheus_live.py`
- Test `apps/api/tests/integration/test_loki_live.py`
- Test `apps/api/tests/integration/test_audit_service.py`

### Task 3.1 `ToolResult` 与 Registry

- [ ] **Step 1**：写测试覆盖 `ToolResult` 字段约束（summary ≤ 280 chars、status 枚举、raw_output_ref 默认 None）和 `ToolRegistry.register/get/names/families`。

- [ ] **Step 2**：跑测试确认失败。

- [ ] **Step 3**：实现 `base.py`、`registry.py`，registry 额外暴露 `disable_family(family)` 与 `available_families()`，配合 graph 工具禁用策略。

- [ ] **Step 4**：测试通过。

### Task 3.2 Prometheus 适配器

- [ ] **Step 1**：写 unit test 用 respx mock `/api/v1/query`、`/-/healthy`，覆盖：
  - `check_prometheus_health` 成功 / 失败。
  - `get_service_error_rate(service=payment-api, window=5m)` 拼接的 PromQL 正确（按 service_catalog 的 `prometheus_label`）。
  - 错误响应转 `ToolResult(status=error)` 而非抛异常。

- [ ] **Step 2**：跑测试失败。

- [ ] **Step 3**：实现 `tools/prometheus.py`：
  - 内部 `_PromClient`（持 httpx AsyncClient）。
  - PromQL 模板（error rate / latency / qps / cpu / memory）按 spec §9.1。
  - 工具方法返回结构化 `data`（如 `PrometheusInstantResult` Pydantic model）。

- [ ] **Step 4**：写 integration test（`tests/integration/test_prometheus_live.py`）：依赖 `ONCALLPILOT_CONFIG`，从配置取 `prometheus.url`，对真实 Prom 实例执行 `query_prometheus("up")`，断言返回非空。配置缺失 → skip 并打印指引。

- [ ] **Step 5**：unit 通过，integration 在配好的真实环境下跑通。

- [ ] **Step 6**：commit

```bash
git add apps/api/oncallpilot_api/tools/prometheus.py apps/api/tests
git commit -m "feat(tools): prometheus adapter with health, error rate, latency, qps"
```

### Task 3.3 Loki 适配器

- [ ] **Step 1**：unit test 覆盖 `query_logs_by_service`、`query_error_logs`、`query_logs_around_time` 的 LogQL 拼接（按 service_catalog 的 `loki_label`），respx mock `/loki/api/v1/query_range`、`/ready`。

- [ ] **Step 2**：跑测试失败。

- [ ] **Step 3**：实现 `tools/loki.py`，注意：
  - 时间窗口参数支持 `(now - lookback, now)` 与 `(ts ± delta)` 两种语义。
  - `summarize_log_patterns` 在 Phase 3 内仅实现“按行频率简单聚类 top N”，留 TODO 等 Phase 7 LangGraph 接入时再替换为 LLM 辅助。

- [ ] **Step 4**：integration test 连真 Loki。

- [ ] **Step 5**：通过 → commit

```bash
git add apps/api/oncallpilot_api/tools/loki.py apps/api/tests
git commit -m "feat(tools): loki adapter with service/error/time-window queries"
```

### Task 3.4 Connectivity 适配器

- [ ] **Step 1**：unit test 用 respx + 本地 asyncio TCP server fixture。

- [ ] **Step 2**：实现 `check_http_endpoint`（httpx）与 `check_tcp_port`（`asyncio.open_connection`）。

- [ ] **Step 3**：通过 → commit

```bash
git add apps/api/oncallpilot_api/tools/connectivity.py
git commit -m "feat(tools): connectivity adapter (http, tcp)"
```

### Task 3.5 audit_service 与 datasource_service

- [ ] **Step 1**：integration test 覆盖 `audit_service.record_tool_call(session_id_kind, session_id, tool_name, parameters, ToolResult, step_index)`，断言 `tool_calls` 行落地 + step_index 写入 + 跨指 CHECK 不违反。

- [ ] **Step 2**：实现 `services/audit_service.py`。

- [ ] **Step 3**：实现 `services/datasource_service.py`：聚合 Prom / Loki / Postgres / Redis / LLM endpoint / GitHub endpoint 健康检查，写 `datasource_status` 表（upsert by name）。

- [ ] **Step 4**：实现 `api/routes_datasources.py`：`GET /api/v1/datasources/status`、`POST /api/v1/datasources/check`。

- [ ] **Step 5**：补 `/readyz` 检查依赖：在 Phase 1 的基础上接入真实 ping（Postgres `SELECT 1`、Redis `PING`、LLM endpoint `models.list` 或 `chat.completions` 试探）。

- [ ] **Step 6**：通过 → commit

```bash
git add apps/api/oncallpilot_api/services/audit_service.py apps/api/oncallpilot_api/services/datasource_service.py apps/api/oncallpilot_api/api/routes_datasources.py
git commit -m "feat(services): audit_service, datasource health, readyz wired"
```

---

## Phase 4: Worker & Async Investigation Pipeline

**目标**：`apps/worker` 独立项目 + arq 配置完成；API 不再直接执行 investigation，而是入队；`event_bus` Redis 实现到位，graph 节点空壳能 publish 事件；session 状态机切换正确。

**Files：**

- Create `apps/worker/pyproject.toml`
- Create `apps/worker/oncallpilot_worker/__init__.py`
- Create `apps/worker/oncallpilot_worker/main.py`        # arq settings
- Create `apps/worker/oncallpilot_worker/jobs.py`        # investigation job entry
- Create `apps/worker/Dockerfile`
- Modify `apps/api/oncallpilot_api/services/event_bus.py`（落地 RedisPubSubEventBus）
- Create `apps/api/oncallpilot_api/services/investigation_service.py`
- Test `apps/api/tests/integration/test_event_bus_redis.py`
- Test `apps/api/tests/integration/test_investigation_enqueue.py`
- Test `apps/worker/tests/unit/test_job_wiring.py`

### Task 4.1 Worker 项目骨架

- [ ] **Step 1**：建 `apps/worker/pyproject.toml`，依赖：`arq`、`oncallpilot-api`（通过 `tool.uv.sources` 指向相对路径，monorepo 复用 agent / tools / repositories）、`pydantic-settings`、`structlog`。

- [ ] **Step 2**：实现 `main.py`：arq `WorkerSettings`，`queue_name` 与 `redis_settings` 从 `oncallpilot_api.config.get_settings()` 取。

- [ ] **Step 3**：实现 `jobs.py`：定义异步 `run_investigation(ctx, session_id: str)` 入口（首发版本空壳：标 session 为 running，sleep，标 completed，publish 一条 `session.completed` 事件），后续 Phase 7 替换为真正的 LangGraph 调用。

- [ ] **Step 4**：写 `apps/worker/Dockerfile`，与 api 同步。

- [ ] **Step 5**：commit

```bash
git add apps/worker
git commit -m "feat(worker): arq worker skeleton with investigation job stub"
```

### Task 4.2 RedisPubSubEventBus

- [ ] **Step 1**：写集成测试：起真 Redis（依赖 `ONCALLPILOT_CONFIG`），publish 一组事件，另一个 task 用 `subscribe(channel, last_event_id=None)` 接收，断言顺序与 payload 一致。

- [ ] **Step 2**：实现 `RedisPubSubEventBus`：
  - publish：`xadd` 写入 `oncallpilot:events:investigation:<session_id>` Redis Stream（用 Stream 而非 pub/sub，保证 history replay 与 Last-Event-ID）。
  - subscribe：先 `xrange` 取 `(last_event_id, +)` 历史，再 `xread block`。
  - 备注：spec 描述用 “Redis pub/sub”，实施时升级为 Redis Streams 以满足 §11.3 的 history replay 与 Last-Event-ID 语义，spec 表述等价（pub/sub 是“实时事件总线”的抽象语，Streams 是具体实现）。

- [ ] **Step 3**：测试通过 → commit

```bash
git add apps/api/oncallpilot_api/services/event_bus.py apps/api/tests/integration/test_event_bus_redis.py
git commit -m "feat(events): redis-streams backed event_bus with history replay"
```

### Task 4.3 InvestigationService.enqueue / Worker.execute 切分

- [ ] **Step 1**：integration test：调用 `InvestigationService.enqueue(incident_id, source, query)` 后断言 `investigation_sessions` 行已写 `status=pending`，arq 队列 length=1；worker 拉一次后 session 变 `running → completed`，事件 stream 至少含 `session.started` 与 `session.completed`。

- [ ] **Step 2**：实现 `services/investigation_service.py`：
  - `enqueue(...)`：创建 session、入 arq 队列（`job_id=f"investigation:{session_id}"`，幂等 by job_id）。
  - 不在 API 进程内执行 graph。
- 实现 worker `jobs.run_investigation`：仅做状态机切换 + event publish，留 graph 占位。

- [ ] **Step 3**：跑测试通过 → commit

```bash
git add apps/api/oncallpilot_api/services/investigation_service.py apps/worker/oncallpilot_worker/jobs.py apps/api/tests
git commit -m "feat(pipeline): split investigation enqueue (api) and execute (worker)"
```

---

## Phase 5: Alertmanager Webhook & Incident APIs

**目标**：Alertmanager webhook + 全部 incident/investigation/chat（chat 仅 API，不接 graph，graph 在 Phase 7 接入）的 REST API + SSE 端点（消费 Phase 4 的 event_bus）。完成 incident 状态机所有人工干预接口。

**Files：**

- Create `apps/api/oncallpilot_api/api/routes_alerts.py`
- Create `apps/api/oncallpilot_api/api/routes_incidents.py`
- Create `apps/api/oncallpilot_api/api/routes_investigations.py`
- Create `apps/api/oncallpilot_api/api/routes_chat.py`
- Create `apps/api/oncallpilot_api/api/routes_events.py`           # SSE
- Create `apps/api/oncallpilot_api/api/schemas.py`                 # 请求/响应模型
- Modify `apps/api/oncallpilot_api/main.py`（注册路由）
- Test `apps/api/tests/unit/test_alert_webhook.py`
- Test `apps/api/tests/unit/test_incident_routes.py`
- Test `apps/api/tests/integration/test_alert_to_session_flow.py`
- Test `apps/api/tests/integration/test_sse_replay.py`

### Task 5.1 Alertmanager Webhook + fingerprint 幂等

- [ ] **Step 1**：unit + integration 测试覆盖：
  - 单 firing alert → 新建 incident + enqueue → 返回 `created=true`。
  - 同 fingerprint 再次 firing → 不新建，返回原 incident，`created=false`，不重复 enqueue。
  - status=resolved alert → incident 置 resolved，不 enqueue。
  - resolved 后再 firing → 新建 incident。
  - 缺 `service` label → 400。

- [ ] **Step 2**：实现 `routes_alerts.py`，调用 `repositories.create_incident_with_fingerprint_dedup` + `InvestigationService.enqueue`。

- [ ] **Step 3**：测试通过 → commit

### Task 5.2 Incident 读写与人工干预 API

- [ ] **Step 1**：测试覆盖：
  - `GET /api/v1/incidents`、`GET /api/v1/incidents/{id}` 字段。
  - `POST /api/v1/incidents/{id}/close` 写 `closed_at` / `closed_reason` / status=resolved。
  - `POST /api/v1/incidents/{id}/reopen` `reopen_count += 1` / status=open。
  - `POST /api/v1/incidents/{id}/investigations` 创建新 session 不改 incident 状态。

- [ ] **Step 2**：实现 `routes_incidents.py` + `routes_investigations.py`。

- [ ] **Step 3**：通过 → commit

### Task 5.3 Chat API（无 graph，占位）

- [ ] **Step 1**：测试覆盖：
  - `POST /api/v1/chat/sessions` 创建会话。
  - `POST /api/v1/chat/sessions/{id}/messages` 接受用户消息，落 `chat_messages`，**首发 Phase 5 内**响应固定 echo（“chat graph 在 Phase 7 接入”）；这一步避免阻塞 API 形态收敛。
  - `GET /api/v1/chat/sessions/{id}/messages` 列出历史。

- [ ] **Step 2**：实现 `routes_chat.py`。`InvestigationService` 不接管 chat；新建 `services/chat_service.py` 暂只做 DB CRUD。

- [ ] **Step 3**：通过 → commit

### Task 5.4 SSE 事件流

- [ ] **Step 1**：integration test：
  - 启动一次 investigation enqueue → worker 处理 → 通过 `GET /api/v1/investigations/{id}/events` SSE 接收，断言收到 `session.started`、`session.completed`。
  - 用 `Last-Event-ID` 重连只收到该 ID 之后的事件。
  - session 已完成时连接，能收到全量历史后立刻 close。

- [ ] **Step 2**：实现 `routes_events.py`：StreamingResponse + `text/event-stream`，先从 `tool_calls` + `investigation_sessions` 回放历史事件（生成 `step.planned/tool.completed/evidence.added` 等），再切到 EventBus `subscribe`。

- [ ] **Step 3**：通过 → commit

```bash
git add apps/api/oncallpilot_api/api apps/api/tests
git commit -m "feat(api): alertmanager webhook, incident lifecycle, chat skeleton, sse events"
```

---

## Phase 6: RAG & Incident Memory

**目标**：pgvector 启用 + embedding 列 migration；OpenAI 兼容 embeddings 客户端；`search_runbook` / `search_incident_memory` / `save_incident_memory` 三工具上线；按 frontmatter + 章节切分 runbook；seed 脚本。`include_drafts` 与 dedup_key 行为按 spec 实装。

**Files：**

- Create `apps/api/oncallpilot_api/db/migrations/versions/<rev>_add_vector_columns.py`
- Modify `apps/api/oncallpilot_api/db/models.py`（追加 `embedding` 列、`runbook_chunks` 表）
- Create `apps/api/oncallpilot_api/services/embedding_client.py`
- Create `apps/api/oncallpilot_api/tools/runbook_rag.py`
- Create `apps/api/oncallpilot_api/tools/incident_memory.py`
- Create `apps/api/oncallpilot_api/api/routes_incident_memories.py`
- Create `docs/runbooks/payment-service-runbook.md`
- Create `docs/runbooks/db-connection-timeout.md`
- Create `docs/runbooks/high-error-rate.md`
- Create `docs/runbooks/high-latency.md`
- Create `docs/runbooks/deployment-regression.md`
- Create `scripts/seed_runbooks.py`
- Create `scripts/seed_incident_memory.py`
- Test `apps/api/tests/unit/test_runbook_frontmatter.py`
- Test `apps/api/tests/integration/test_rag_search.py`
- Test `apps/api/tests/integration/test_incident_memory_dedup.py`

### Task 6.1 pgvector migration 与 models 更新

- [ ] **Step 1**：写 integration test 在干净库上执行 `alembic upgrade head`，断言：
  - `CREATE EXTENSION IF NOT EXISTS vector` 已执行。
  - `runbook_chunks` 表存在，含 `embedding VECTOR(<dim>)`，dim 取自 `Settings().llm.embedding_dim`。
  - `incident_memories` 含 `embedding VECTOR(<dim>)` + `dedup_key` 唯一索引。

- [ ] **Step 2**：写新 migration，从 `Settings` 读 `embedding_dim`，硬编码到 SQL（首次建表后**不可改**——spec §5.2 / §7.7 已显式声明）。

- [ ] **Step 3**：测试通过 → commit。

### Task 6.2 Embedding 客户端

- [ ] **Step 1**：unit test 用 respx mock `/v1/embeddings`，验证 `EmbeddingClient.embed(["text"])` 返回 dim 与配置一致；批量调用 chunk-size 拆分。

- [ ] **Step 2**：实现 `services/embedding_client.py`，依赖 `openai` SDK，base_url / api_key 从配置取。

- [ ] **Step 3**：通过 → commit。

### Task 6.3 Runbook 文档与契约校验

- [ ] **Step 1**：写 unit test：`load_runbook(path)` 对缺 frontmatter / 缺章节的文档抛 `RunbookFormatError`；合规文档返回结构化 `Runbook(id, frontmatter, sections, content)`。

- [ ] **Step 2**：实现 `tools/runbook_rag.py` 的解析器（含 frontmatter 校验 + 章节顺序校验，参考 spec §20）。

- [ ] **Step 3**：写 5 篇内置 runbook（中文）。

- [ ] **Step 4**：实现 `scripts/seed_runbooks.py`：解析所有 `docs/runbooks/*.md` → 写 `runbook_documents` + 按章节切 chunk + 调 embedding 入 `runbook_chunks`。fail-fast。

- [ ] **Step 5**：commit

```bash
git add apps/api/oncallpilot_api/tools/runbook_rag.py docs/runbooks scripts/seed_runbooks.py apps/api/tests
git commit -m "feat(rag): runbook contract, chunker, seed pipeline with embeddings"
```

### Task 6.4 RAG 搜索工具

- [ ] **Step 1**：integration test：
  - seed 完成后 `search_runbook("payment-api 数据库连接超时")` 返回的 top-1 命中 `payment-service-runbook` 或 `db-connection-timeout` 的相应章节。
  - 提供 `services=["payment-api"]` 时 boost 后排序更稳定。

- [ ] **Step 2**：实现 `search_runbook` 工具：构造 query embedding → pgvector `<->` cosine 距离查 top_k → 命中 service_catalog 的 runbook 给加权 → 返回 `ToolResult`。

- [ ] **Step 3**：通过 → commit。

### Task 6.5 Incident Memory 工具 + Review API

- [ ] **Step 1**：integration test：
  - `save_incident_memory(...)` 写 status=draft + 计算 dedup_key。
  - 同 dedup_key 二次 save：覆盖最新内容（保持 draft）。
  - 已存在 verified → 不写。
  - `search_incident_memory` 默认仅返 verified；`include_drafts_in_search=true` 时 draft 命中带 `confidence_penalty`。
  - `POST /api/v1/incident-memories/{id}/review action=verify` 行为正确。

- [ ] **Step 2**：实现 `tools/incident_memory.py` + `routes_incident_memories.py`。

- [ ] **Step 3**：写 `scripts/seed_incident_memory.py`：预灌 1 条 payment-api DB 超时的 verified 记忆。

- [ ] **Step 4**：通过 → commit

```bash
git add apps/api/oncallpilot_api/tools/incident_memory.py apps/api/oncallpilot_api/api/routes_incident_memories.py scripts/seed_incident_memory.py apps/api/tests
git commit -m "feat(memory): incident_memory tool with draft/verified review"
```

---

## Phase 7: LangGraph Investigation Loop

**目标**：完整 investigation graph + chat graph 上线，替换 Phase 4 的 worker stub；OpenAI 协议 function calling 驱动 plan_next_step；三条护栏 + 双步预算 + verdict 输出；Langfuse Tracer 真实接入；event_bus 在每个节点 publish 事件。

**Files：**

- Create `apps/api/oncallpilot_api/agent/__init__.py`
- Create `apps/api/oncallpilot_api/agent/state.py`
- Create `apps/api/oncallpilot_api/agent/report_schema.py`
- Create `apps/api/oncallpilot_api/agent/prompts.py`        # 英文 system + 输出语言指令
- Create `apps/api/oncallpilot_api/agent/policies.py`      # 步数 / 工具禁用 / 去重
- Create `apps/api/oncallpilot_api/agent/llm.py`           # OpenAI 协议 wrapper
- Create `apps/api/oncallpilot_api/agent/investigation_graph.py`
- Create `apps/api/oncallpilot_api/agent/chat_graph.py`
- Create `apps/api/oncallpilot_api/services/chat_service.py`（升级 Phase 5 的占位）
- Modify `apps/worker/oncallpilot_worker/jobs.py`
- Modify `apps/api/oncallpilot_api/observability/tracer.py`（落地 LangfuseTracer）
- Test `apps/api/tests/unit/test_policies.py`
- Test `apps/api/tests/unit/test_state_reducers.py`
- Test `apps/api/tests/integration/test_investigation_loop_happy_path.py`
- Test `apps/api/tests/integration/test_chat_graph_multi_turn.py`

### Task 7.1 State / FinalReport / Policies

- [ ] **Step 1**：unit test：
  - `should_disable_tools(step_index, max_tool_steps)` 在倒数第 1 步返回 True。
  - `hard_cap_breached(step_index, hard_cap)` 行为正确。
  - `is_duplicate_call(history, tool, args)` 同 `(tool, hash(args))` 第二次返回 True。
  - `should_disable_family(history, family, threshold)` 在连续 N 次 error 后 True。

- [ ] **Step 2**：实现 `state.py`（Pydantic `InvestigationState` / `EvidenceItem` / `ToolCallRecord` 等）、`report_schema.py`（`FinalReport` 严格匹配 spec §10.4）、`policies.py`。

- [ ] **Step 3**：通过 → commit。

### Task 7.2 LLM wrapper（OpenAI 协议）

- [ ] **Step 1**：unit test 用 respx mock `/v1/chat/completions`：
  - tool calling 返回 `selected_tool` + `tool_args`。
  - 多轮 messages 拼接正确。
  - 错误响应转抛 `LLMCallError`。

- [ ] **Step 2**：实现 `agent/llm.py`：基于 `openai.AsyncOpenAI(base_url, api_key)`，封装 `plan(messages, tools_schema)` 与 `summarize(messages, schema)`（`response_format=json_schema`）。

- [ ] **Step 3**：通过 → commit。

### Task 7.3 Investigation Graph

- [ ] **Step 1**：integration test `test_investigation_loop_happy_path.py`：
  - 准备一份 alert（payment-api HighErrorRate）。
  - Mock 各工具的返回（pytest fixture 替换 registry 中的工具为返回固定数据的 fake）。
  - 入队一次 investigation → worker 跑完 → 断言：
    - graph 调到了 ≥ 1 metric + 1 log + 1 runbook + 1 memory 类工具；
    - final_report.verdict in {`unhealthy`}；confidence ≥ 0.5；
    - persist_result 写入 session + 1 条 draft incident_memory；
    - event stream 包含 `session.started → step.planned → tool.completed → session.completed`。

- [ ] **Step 2**：实现 `investigation_graph.py`：节点按 spec §10.1 / §10.2，工具调用前后落 audit + publish 事件 + Tracer 上报。

- [ ] **Step 3**：实现 `propose_remediation`（GitHub 调用 stub，等 Phase 8 真接 → 现在落 `manual_action`）。

- [ ] **Step 4**：用 Phase 4 已存在的 RedisStreams event_bus 真发事件。

- [ ] **Step 5**：通过 → commit

```bash
git add apps/api/oncallpilot_api/agent apps/worker/oncallpilot_worker/jobs.py apps/api/tests
git commit -m "feat(agent): investigation graph with planner, policies, verdict, sse events"
```

### Task 7.4 Chat Graph

- [ ] **Step 1**：integration test `test_chat_graph_multi_turn.py`：
  - 创建 chat session → 发用户消息 → assistant 响应含 markdown；
  - 多轮历史会被 LLM 看到；
  - `chat_max_tool_steps` 限制生效；
  - tool 调用 audit + 事件流通过 `/api/v1/chat/sessions/{id}/events` 可见。

- [ ] **Step 2**：实现 `chat_graph.py`（共享 registry / llm / audit / tracer / event_bus；不写 incident_memory）。

- [ ] **Step 3**：升级 `services/chat_service.py`：消息追加时调用 chat_graph，**同步**返回（不入 arq 队列）。

- [ ] **Step 4**：升级 `routes_chat.py`：返回 assistant 消息体；同时 SSE 端点 `/api/v1/chat/sessions/{id}/events` 与 investigation SSE 共用 `routes_events.py` 的通用逻辑。

- [ ] **Step 5**：通过 → commit。

### Task 7.5 Langfuse Tracer 真接

- [ ] **Step 1**：integration test（需 `LANGFUSE_*` env）：跑一次 graph，断言 Langfuse SDK 收到 trace（用 Langfuse `get_trace` 或本地 sink mock）。

- [ ] **Step 2**：实现 `LangfuseTracer`：trace_id = session_id，span 覆盖每个 graph 节点 + LLM 调用 + tool 调用 + usage 计数。

- [ ] **Step 3**：未配置 Langfuse env → 自动退化 NoOp，不抛异常。

- [ ] **Step 4**：commit

```bash
git add apps/api/oncallpilot_api/observability apps/api/tests
git commit -m "feat(obs): langfuse tracer with graph and llm spans"
```

---

## Phase 8: GitHub Tool & Remediation

**目标**：GitHub REST 适配器（与 MCP 接口对齐）+ `create_issue` 受 `github.write_enabled` 保护 + `RemediationService` 决策落 `remediation_actions`。replace Phase 7 的 manual_action stub。

**Files：**

- Create `apps/api/oncallpilot_api/tools/github.py`
- Create `apps/api/oncallpilot_api/tools/github_mcp.py`（可选；首发只要接口对齐，实现可后置）
- Create `apps/api/oncallpilot_api/services/remediation_service.py`
- Test `apps/api/tests/unit/test_github_write_guard.py`
- Test `apps/api/tests/integration/test_github_search.py`
- Test `apps/api/tests/integration/test_remediation_proposal.py`

### Task 8.1 GitHub REST 适配器

- [ ] **Step 1**：unit test 用 respx mock GitHub `/search/commits`、`/search/issues`、`/repos/{owner}/{repo}/issues`：
  - service 在 service_catalog 缺失时返回 `ToolResult(status=error, error_message=...)`。
  - 写 `create_issue` 在 `github.write_enabled=false` 时抛 `GitHubWriteDisabledError`。
  - 写启用且 200 时返回 issue url。

- [ ] **Step 2**：实现 `tools/github.py`：根据 `service` 从 `service_catalog` 读 `github_owner/github_repo`；`github_mcp.py` 可暂时只暴露接口签名 + raise `NotImplementedError`。

- [ ] **Step 3**：integration test（需 `GITHUB_TOKEN` + 真可读 repo）：对 `octocat/Hello-World` 类公开 repo 调 search_recent_commits 成功。

- [ ] **Step 4**：commit。

### Task 8.2 RemediationService

- [ ] **Step 1**：integration test：
  - confidence ≥ 0.7 + `write_enabled=true` → 创建 GitHub issue + 写 `remediation_actions(type=github_issue, status=created, url=...)`。
  - confidence ≥ 0.7 + `write_enabled=false` → 落 `remediation_actions(type=pr_proposal, status=proposed)`，含 issue 草稿正文。
  - confidence < 0.7 → 落 `manual_action`。

- [ ] **Step 2**：实现 `services/remediation_service.py`，替换 graph 中 `propose_remediation` 节点的 stub。

- [ ] **Step 3**：通过 → commit

```bash
git add apps/api/oncallpilot_api/tools/github.py apps/api/oncallpilot_api/services/remediation_service.py apps/api/tests
git commit -m "feat(github): github tool and remediation policy"
```

---

## Phase 9: CRDs & Controller

**目标**：三个 CRD 定义 + kopf 控制器三套 handler + 与后端 API 的客户端 + ScheduledHealthCheck cron 触发 + ServiceCatalog 同步。

**Files：**

- Create `deploy/helm/oncallpilot/templates/crds/oncallpilot.io_healthchecks.yaml`
- Create `deploy/helm/oncallpilot/templates/crds/oncallpilot.io_scheduledhealthchecks.yaml`
- Create `deploy/helm/oncallpilot/templates/crds/oncallpilot.io_servicecatalogs.yaml`
- Create `apps/controller/pyproject.toml`
- Create `apps/controller/oncallpilot_controller/__init__.py`
- Create `apps/controller/oncallpilot_controller/main.py`
- Create `apps/controller/oncallpilot_controller/client.py`
- Create `apps/controller/oncallpilot_controller/cron.py`
- Create `apps/controller/oncallpilot_controller/handlers_healthcheck.py`
- Create `apps/controller/oncallpilot_controller/handlers_scheduled_healthcheck.py`
- Create `apps/controller/oncallpilot_controller/handlers_service_catalog.py`
- Create `apps/controller/Dockerfile`
- Create `apps/api/oncallpilot_api/api/routes_service_catalog.py`（内部 PUT sync 端点 + 公开 GET）
- Test `apps/controller/tests/unit/test_cron.py`
- Test `apps/controller/tests/unit/test_verdict_mapping.py`

### Task 9.1 CRD manifests

- [ ] 写三个 CRD YAML（schema 与 spec §13 一致），用 Helm 模板 `{{- if .Values.installCrds }}` 包裹（运营者可关）。
- [ ] commit。

### Task 9.2 controller 项目骨架

- [ ] `pyproject.toml` 依赖：`kopf`、`kubernetes`、`croniter`、`httpx`、`pydantic`、`structlog`。
- [ ] `main.py` 注册三个 handler 模块。
- [ ] `client.py`：`OnCallPilotClient`，封装 `start_investigation`、`get_investigation`、`sync_service_catalog`、`submit_synthetic_alert` 四个 API。
- [ ] Dockerfile（multi-stage + uv）。

### Task 9.3 ServiceCatalog handler

- [ ] **Step 1**：unit test：CRD create/update → 调 `sync_service_catalog`（用 respx mock backend）。
- [ ] **Step 2**：实现 handler，spec_version 单调递增。
- [ ] **Step 3**：commit。

### Task 9.4 HealthCheck handler

- [ ] **Step 1**：unit test 覆盖 verdict → result 映射：healthy→pass / unhealthy→fail / inconclusive→error；超时与异常路径都置 error。
- [ ] **Step 2**：实现 handler：create → `status.phase=Running` → 调 backend → 轮询 → patch status。
- [ ] **Step 3**：`mode=alert` 且 fail → 调 `submit_synthetic_alert` 自闭环（HealthCheckFailed 告警）。
- [ ] **Step 4**：commit。

### Task 9.5 ScheduledHealthCheck handler

- [ ] **Step 1**：unit test `test_cron.py`：
  - `should_run("* * * * *", last=None, now=...)` True。
  - `should_run("0 * * * *", last=2026-05-27T03:00:00Z, now=2026-05-27T03:30:00Z)` False。
  - 距 `lastScheduleTime < timeout` → skip。
- [ ] **Step 2**：实现 `cron.py`。
- [ ] **Step 3**：`@kopf.timer(interval=30, idle=30)` 周期扫；触发时创建子 `HealthCheck`（OwnerReference 指向 SHC）。
- [ ] **Step 4**：`status.history` 环形 10 条。
- [ ] **Step 5**：commit

```bash
git add apps/controller deploy/helm/oncallpilot/templates/crds apps/api/oncallpilot_api/api/routes_service_catalog.py
git commit -m "feat(controller): healthcheck, scheduled, service catalog handlers"
```

---

## Phase 10: Helm Chart & Kubernetes Delivery

**目标**：完整 Helm chart 渲染 4 个 Deployment + Service + ConfigMap + RBAC + Ingress + migration Job；`values.example.yaml` / `values.scenario.yaml` 完成；本地 kind/minikube 上 `helm install` 一遍能跑起来（手工验证）。

**Files：**

- Create `deploy/helm/oncallpilot/Chart.yaml`
- Create `deploy/helm/oncallpilot/values.yaml`
- Create `deploy/helm/oncallpilot/values.example.yaml`
- Create `deploy/helm/oncallpilot/values.scenario.yaml`
- Create `deploy/helm/oncallpilot/templates/_helpers.tpl`
- Create `deploy/helm/oncallpilot/templates/configmap.yaml`
- Create `deploy/helm/oncallpilot/templates/secret-ref.yaml`     # 仅占位，运营者用 existingSecret
- Create `deploy/helm/oncallpilot/templates/rbac.yaml`
- Create `deploy/helm/oncallpilot/templates/api-deployment.yaml`
- Create `deploy/helm/oncallpilot/templates/worker-deployment.yaml`
- Create `deploy/helm/oncallpilot/templates/controller-deployment.yaml`
- Create `deploy/helm/oncallpilot/templates/web-deployment.yaml`
- Create `deploy/helm/oncallpilot/templates/services.yaml`
- Create `deploy/helm/oncallpilot/templates/ingress.yaml`
- Create `deploy/helm/oncallpilot/templates/migration-job.yaml`

### Task 10.1 Chart 骨架与 ConfigMap

- [ ] `Chart.yaml` 元信息。
- [ ] `_helpers.tpl`：`fullname`、`labels`、`selectorLabels`。
- [ ] `configmap.yaml`：把 `.Values.oncallpilotConfig` 整体作为 YAML 字符串渲染到 ConfigMap `data."config.yaml"`，与 spec §5.2 schema 对齐。
- [ ] `values.yaml` 含全部默认。

### Task 10.2 RBAC（最小权限）

- [ ] controller ServiceAccount：仅 `oncallpilot.io/*` CRD CRUD + status + events create，按 spec §13.4。
- [ ] api / worker / web 无额外权限。

### Task 10.3 4 个 Deployment + Service

- [ ] api / worker / web：单 replica 起步（Helm `replicaCount` 可配）。
- [ ] controller：固定 `replicas: 1`，`strategy: Recreate`。
- [ ] 每个容器都挂 ConfigMap 到 `/etc/oncallpilot/config.yaml` + `ONCALLPILOT_CONFIG` 环境变量 + 从 `existingSecret` 注入所有 `*_env` 引用的环境变量。
- [ ] Service：api/web/controller 暴露 ClusterIP；worker 不暴露端口。
- [ ] Ingress：默认 nginx；提供 basic auth annotation 模板 + SSE 必需的 `proxy-buffering: off` / `proxy-read-timeout: 3600`。

### Task 10.4 Migration Job

- [ ] `migration-job.yaml` 用 helm hook `pre-install,pre-upgrade`，运行 `alembic upgrade head`；`backoffLimit: 3`。

### Task 10.5 验证

- [ ] **Step 1**：本地 kind 集群准备 Postgres + Redis（用户自行准备的真实基础设施，符合 spec §2 中“OnCallPilot 不打包基础设施”原则）。
- [ ] **Step 2**：填好 `values.example.yaml` + 创建 Secret，`helm install oncallpilot ./deploy/helm/oncallpilot -f values.example.yaml -n oncallpilot --create-namespace`。
- [ ] **Step 3**：`kubectl rollout status` 全部 Deployment OK；`curl` api `/healthz` 200。
- [ ] **Step 4**：commit

```bash
git add deploy/helm
git commit -m "feat(deploy): helm chart with all components, rbac, migration job, sse-ready ingress"
```

---

## Phase 11: Reference Workload `samples/payment-api`

**目标**：随仓库分发的样例上游服务（仅正常态），用于 Phase 13 端到端验证。Phase 14 chaos 才把故障注入声明化。

**Files：**

- Create `samples/payment-api/pyproject.toml`
- Create `samples/payment-api/app/__init__.py`
- Create `samples/payment-api/app/main.py`
- Create `samples/payment-api/app/db.py`
- Create `samples/payment-api/app/metrics.py`
- Create `samples/payment-api/app/logging.py`
- Create `samples/payment-api/Dockerfile`
- Create `samples/payment-api/README.md`
- Create `deploy/helm/oncallpilot/templates/sample-payment-api.yaml`（可选，受 `.Values.samples.paymentApi.enabled` 开关控制；默认关闭）

### Task 11.1 应用骨架

- [ ] FastAPI + asyncpg + `prometheus_client` + `structlog`。
- [ ] 暴露 `/healthz` + `/metrics` + 业务路由 `/orders`、`/orders/{id}`、`/payments`（全部 200 路径）。
- [ ] 指标：`http_requests_total{service="payment-api", method, status}`、`http_request_duration_seconds{service="payment-api"}` Histogram、`db_connections_in_use{service="payment-api"}` Gauge、`db_connection_errors_total{service="payment-api"}` Counter。
- [ ] JSON 结构化日志到 stdout，含 `service="payment-api"`。

### Task 11.2 README 与定位说明

- [ ] README 明确："Reference workload distributed with OnCallPilot to validate end-to-end investigation pipelines. Production-grade fault injection (chaos-mesh) is delivered in Phase 14. Manual fault triggers used for end-to-end validation prior to Phase 14 are documented in `docs/scenarios/payment-api-high-error-rate/manual-trigger.md`."

### Task 11.3 Helm 可选启用

- [ ] `templates/sample-payment-api.yaml` 仅在 `.Values.samples.paymentApi.enabled=true` 时渲染，包含 Deployment + Service + ServiceMonitor 样板（或 scrape annotation）。
- [ ] `values.scenario.yaml` 把它打开。

### Task 11.4 commit

```bash
git add samples/payment-api deploy/helm/oncallpilot/templates/sample-payment-api.yaml
git commit -m "feat(samples): payment-api reference workload (healthy-path only)"
```

---

## Phase 12: Dashboard

**目标**：Next.js App Router + next-intl（默认 `zh-CN`）+ React Query + Tailwind，6 个页面 + 完整 SSE 消费 + 全字符串走字典 key。

**Files：**

- Create `apps/web/package.json`
- Create `apps/web/next.config.mjs`
- Create `apps/web/tsconfig.json`
- Create `apps/web/app/layout.tsx`
- Create `apps/web/app/page.tsx`                                      # 首页
- Create `apps/web/app/incidents/page.tsx`
- Create `apps/web/app/incidents/[id]/page.tsx`
- Create `apps/web/app/investigations/[id]/page.tsx`
- Create `apps/web/app/chat/page.tsx`
- Create `apps/web/app/chat/[id]/page.tsx`
- Create `apps/web/app/incident-memories/page.tsx`
- Create `apps/web/app/service-catalog/page.tsx`
- Create `apps/web/components/*.tsx`
- Create `apps/web/lib/api.ts`
- Create `apps/web/lib/sse.ts`
- Create `apps/web/messages/zh-CN.json`
- Create `apps/web/messages/en.json`           # 占位
- Create `apps/web/Dockerfile`

### Task 12.1 项目骨架与 i18n

- [ ] `pnpm` workspace；Next.js App Router；next-intl 配置 `defaultLocale: 'zh-CN'`。
- [ ] `messages/zh-CN.json` 准备所有 UI 字符串 key。

### Task 12.2 API / SSE 客户端

- [ ] `lib/api.ts`：基于 `fetch` 封装 GET/POST，base url 从 `NEXT_PUBLIC_ONCALLPILOT_API_URL` 读。
- [ ] `lib/sse.ts`：基于浏览器原生 `EventSource`，支持 `Last-Event-ID`、自动重连。
- [ ] React Query 全局 provider。

### Task 12.3 页面实现

- [ ] **首页**：最近 incident（GET /incidents）+ 数据源健康（GET /datasources/status）+ 最近 ScheduledHealthCheck 状态。
- [ ] **Incidents 列表 + 详情**：含 close/reopen/re-investigate 按钮（confirm dialog 收 reason）。
- [ ] **Investigation 详情**：SSE 时间线（按 step 分组）+ 证据卡片 + final report 区块 + 修复提案 + “在 Langfuse 中查看”按钮（仅 observability 启用时显示）。
- [ ] **Chat 列表 + 详情**：多轮对话；assistant 消息可展开证据；`suggest_upgrade_to_investigation=true` 时展示按钮触发 `POST /api/v1/investigations`。
- [ ] **Incident Memories**：列表 + Verify/Reject/Edit。
- [ ] **Service Catalog**：只读。

### Task 12.4 构建与验证

- [ ] **Step 1**：`pnpm install && pnpm run build` 通过。
- [ ] **Step 2**：本地起 backend + web，端到端点一遍每个页面。
- [ ] **Step 3**：Dockerfile + Helm `web-deployment.yaml` 镜像替换并 rollout。
- [ ] **Step 4**：commit

```bash
git add apps/web
git commit -m "feat(web): dashboard with sse timeline, chat, memory review, service catalog"
```

---

## Phase 13: End-to-End Reference Scenario Validation

**目标**：通过手工故障操作（`kubectl scale postgres --replicas=0` 等），让 payment-api 自然产出 5xx + `DB_CONN_TIMEOUT` 日志，触发 Alertmanager 规则向 OnCallPilot 发告警，端到端验证整条链路；产出可重复执行的验证文档与脚本。

**Files：**

- Create `docs/scenarios/payment-api-high-error-rate/manual-trigger.md`
- Create `docs/scenarios/payment-api-high-error-rate/validation.md`
- Create `examples/alertmanager/payment-api-high-error-rate.json`
- Create `examples/crds/healthcheck-payment-api.yaml`
- Create `examples/crds/scheduled-healthcheck-payment-api.yaml`
- Create `examples/crds/service-catalog-payment-api.yaml`
- Create `scripts/run_scenario_payment_api_high_error_rate.py`
- Modify `README.md`

### Task 13.1 准备 CRD / 告警 / 配置 fixtures

- [ ] 写 `service-catalog-payment-api.yaml`：把 payment-api 注册进 ServiceCatalog（含 github owner/repo、runbookIds、tier）。
- [ ] 写 `healthcheck-payment-api.yaml`、`scheduled-healthcheck-payment-api.yaml`。
- [ ] 写 `payment-api-high-error-rate.json`：标准 Alertmanager 格式（status=firing、含 fingerprint、service、severity、startsAt）。

### Task 13.2 验证脚本

- [ ] `scripts/run_scenario_payment_api_high_error_rate.py`：
  1. 读 `--api-base-url`、`--config` 参数。
  2. POST 告警 payload。
  3. 轮询 GET `/api/v1/investigations/{id}` 直到 status=completed 或超时。
  4. 打印 verdict / confidence / 主要 evidence summary / remediation url。
  5. 退出码反映 verdict（unhealthy=0 验证成功；其他=非 0）。

### Task 13.3 验证文档

- [ ] `manual-trigger.md`：步骤化文档，指导运营者：
  1. `helm install oncallpilot -f values.scenario.yaml` + 部署 samples/payment-api。
  2. `kubectl apply -f examples/crds/service-catalog-payment-api.yaml`。
  3. seed runbooks + incident memory。
  4. 让 payment-api 跑 ≥ 5 分钟产生正常态指标。
  5. 制造故障：`kubectl -n payments scale deploy/payment-db --replicas=0`。
  6. 等 ~2 分钟，触发告警（自动从 Alertmanager 或手工跑脚本）。
  7. 打开 dashboard 看 incident / investigation / SSE 时间线。
- [ ] `validation.md`：spec §16.2 验收清单逐项 checkbox。

### Task 13.4 端到端跑一次

- [ ] **Step 1**：在已部署的 kind / 真实集群上按 `manual-trigger.md` 走一遍。
- [ ] **Step 2**：对照 `validation.md` 勾选每一项是否通过；不通过的项回溯到对应 Phase 修。
- [ ] **Step 3**：把 `manual-trigger.md` 中发现的实际坑（命令、等待时长、容差）写回文档。

### Task 13.5 README 与最终 commit

- [ ] README 重写为产品介绍 + 部署 + 参考场景验证三段式（中文），按产品语义口径表述。
- [ ] commit

```bash
git add docs/scenarios examples scripts/run_scenario_payment_api_high_error_rate.py README.md
git commit -m "docs: reference scenario validation (payment-api HighErrorRate)"
```

---

## Phase 14: Scenario Automation with chaos-mesh （Deferred，不计入 MVP 验收）

**目标**：把 Phase 13 的手工故障操作声明化为 chaos-mesh `NetworkChaos`，让参考场景一键可重复触发。此 Phase **不影响 MVP 验收**，作为后续增量交付。

**Files：**

- Create `deploy/scenarios/payment-api-high-error-rate/NetworkChaos.yaml`
- Create `deploy/scenarios/payment-api-high-error-rate/Workflow.yaml`
- Modify `scripts/run_scenario_payment_api_high_error_rate.py`（增加 `--use-chaos-mesh` 模式）
- Modify `docs/scenarios/payment-api-high-error-rate/manual-trigger.md`（追加 chaos-mesh 自动化章节）

### Task 14.1 NetworkChaos 资源

- [ ] 选择 selector：targets payment-api → postgres 的网络流，注入 `delay: 5s` + `loss: 80%`。

### Task 14.2 触发与清理

- [ ] `scripts/run_scenario_payment_api_high_error_rate.py --use-chaos-mesh` 自动 `kubectl apply NetworkChaos` → 等触发告警 → 等 investigation 完成 → 自动 `kubectl delete` 清理。

### Task 14.3 commit

```bash
git add deploy/scenarios scripts docs
git commit -m "feat(scenarios): chaos-mesh automation for payment-api HighErrorRate"
```

---

## 自审清单

- 产品语义一致：全文统一使用“参考场景 / 参考工作负载 / 端到端验证”这套口径。
- Phase 顺序与依赖：每 Phase 引用的前置组件已在前面 Phase 落地（如 Phase 4 event_bus 在 Phase 5 SSE 之前；Phase 6 RAG 在 Phase 7 LangGraph 之前；Phase 8 GitHub 真接在 Phase 7 graph 之后；Phase 9 CRD 控制器在 Phase 8 之后避免 service_catalog 双源）。
- 任务粒度：每个 Task 控制在“一次 TDD 提交可完成”的尺度，避免单 Task 内塞 4+ 件事。
- 测试边界：unit 用 `respx` 边界 mock；integration 全部依赖真实基础设施（由 `ONCALLPILOT_CONFIG` 提供），未配置即 `skip`，不内置假 fixture，符合 spec §2 / §18。
- 推迟项：chaos-mesh 自动化、多 replica controller、ITSM 完整功能、OIDC、数据自动清理、多 agent、自动 PR diff 均在 spec §23.2 显式列推迟，本计划中亦不混入。
- 抽象克制：仅 `Tracer` / `EventBus` / `ServiceCatalogRepository`（后者在 Phase 9 通过 CRD 同步表落地）三处接口抽象，每处都有 spec 中标注的启用条件，符合“不引入无明确价值的双轨 / 抽象”。
