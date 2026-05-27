# Product Vision PRD — OnCallPilot

> 本 PRD 描述 OnCallPilot 作为企业级 on-call 智能调查平台的**长期愿景**。具体里程碑（v0.1、v0.2、…）由独立 PRD 拆解定义。本文件是产品边界的“北极星”，给所有里程碑提供取舍依据。

## Problem Statement

凌晨三点，支付服务 5xx 告警炸出。值班工程师被叫醒后做的事大同小异：

- 切到 Grafana 看一眼指标，再切到 Loki 翻日志关键字，再切到 GitHub 看最近合并的 PR，再翻 Confluence/Notion 找运行手册，再问群里“上次这个问题是谁解决的？”
- 多个数据源之间没有自动关联，注意力被频繁切换碎片化。
- 团队的事故经验只存在少数老员工脑子里，新人遇到同类问题要从零摸索。
- 修复方案的提案需要人在精疲力尽时手写。
- 主动巡检（“今天我们的核心服务还好吗？”）几乎没人做，因为没人愿意手动执行那一长串命令。

更糟的是：随着服务数量增长，on-call 的认知负担呈线性甚至非线性增长，但人的精力上限是常数。SRE 团队要么扩编，要么靠侥幸不出事，要么主动接受 MTTR 持续恶化。

## Solution

OnCallPilot 是一个**部署在 Kubernetes 上的云原生 on-call 智能调查平台**。它把上面那条人肉链路，变成一条由 AI agent 自动跑、对人可见、可审计、可干预的流水线：

1. 接告警（或 K8s `HealthCheck` CRD），自动建一个 incident 和 investigation session。
2. LangGraph 驱动的单 agent 调用真实工具——Prometheus、Loki、运行手册 RAG、事故记忆、GitHub、连通性检查——逐步收集证据。
3. 每一次工具调用都进审计表，前端 SSE 实时展示工具链时间线，运维能随时看到 “AI 现在在查什么、为什么查”。
4. 调查结束输出一份结构化报告：症状、可疑根因、证据链、影响面、推荐动作、置信度、相关 runbook、相似历史事件、修复提案。
5. 高置信度场景下自动起草 GitHub Issue 或 PR 提案；低置信度场景下落 manual action 等人决策。
6. 事故经验作为 incident memory 自动沉淀，经审阅后进入团队知识库，被未来调查的 RAG 召回。
7. 通过 `ScheduledHealthCheck` 把“主动巡检”变成自动定时任务，发现退化时自闭环触发完整 investigation 流程。
8. 一切都通过 K8s CRD 声明式管理，Helm Chart 一键部署，Langfuse trace 提供深度可观测，Service Catalog 提供服务级元数据治理。

产品定位口径：**这是一个面向真实企业生产环境的产品**，所有验证用例称为“参考场景（reference scenario）”、被监控应用称为“参考工作负载（reference workload）”，不出现弱化产品定位的临时性表述。

## User Stories

### 接入与告警侧

1. 作为 SRE，我希望把 OnCallPilot 接到我现有的 Alertmanager 后面作为一个 webhook receiver，这样我不用改告警规则就能让 AI 介入调查。
2. 作为 SRE，我希望同一个告警在多次重发时（Alertmanager 默认行为）只产生一个 incident，避免被同一事件刷屏。
3. 作为 SRE，我希望 firing → resolved → firing 这样的事件流被识别为多次独立 incident（保留历史 timeline），而不是一团模糊的“同一个问题”。
4. 作为 SRE，我希望告警 payload 里没带规范的 `service` label 时，OnCallPilot 给出明确的 400 错误，提示我哪个字段缺失。
5. 作为 Platform Engineer，我希望通过 `kubectl apply HealthCheck` 提交一次自然语言巡检（"payment-api 现在是否健康？"），并通过 `kubectl describe` 看到 pass/fail/error 结果和 AI 的判定理由。
6. 作为 Platform Engineer，我希望通过 `ScheduledHealthCheck` 配置 cron 表达式定时执行巡检，并在 `status.history` 里看到最近 10 次执行结果。
7. 作为 Platform Engineer，我希望 `HealthCheck.spec.mode=alert` 时，failed 的巡检能自动以告警形式回灌到 incident 流，让"主动发现"和"被动接告警"汇合到同一处理流程。

### 调查 / 工具调用侧

8. 作为 on-call 工程师，我希望 incident 创建后 AI 自动开始调查，不需要我手动按按钮。
9. 作为 on-call 工程师，我希望 AI 调查不阻塞 webhook，Alertmanager 收到 200 立刻返回，调查在后台跑。
10. 作为 on-call 工程师，我希望 AI 第一步先做基础设施健康探测，如果 Prom/Loki 自己挂了，能立刻告诉我"无法调查"而不是浪费几十步在错误数据上推理。
11. 作为 on-call 工程师，我希望 AI 在 10 步内（可配置工作预算）完成调查，且有硬上限不会跑飞烧 token。
12. 作为 on-call 工程师，我希望同一个工具不会被 AI 重复调用同样的参数（无效绕圈）。
13. 作为 on-call 工程师，我希望某类工具连续失败若干次后被自动禁用，AI 会换其他思路。
14. 作为 SRE，我希望工具调用都用真实数据源，不是 mock；Prometheus 真查、Loki 真查、GitHub 真访问。
15. 作为 SRE，我希望工具失败（如 Loki 临时不可用）不会让整个 graph 崩溃，AI 会把"信号缺失"作为一条 evidence 记录下来。

### 证据与报告侧

16. 作为 on-call 工程师，我希望 incident 详情页能实时（SSE）看到 AI 当前在第几步、调了什么工具、工具返回了什么 summary。
17. 作为 on-call 工程师，我希望每条证据都带类型（metric / log / runbook / memory / github / connectivity / signal_missing）、来源、置信度。
18. 作为 on-call 工程师，我希望最终报告显式给出 verdict（healthy / unhealthy / inconclusive）和 verdict_reason，不要让我自己从一堆指标里拼答案。
19. 作为 on-call 工程师，我希望报告引用的 runbook 是稳定 ID（不是 path），点进去能跳转到对应章节，而不是只丢一个文件名。
20. 作为 on-call 工程师，我希望报告关联的"相似历史事件"被显式列出，并能跳到那次历史 incident 详情。
21. 作为 audit 团队，我希望每一次工具调用都落库（参数、结果摘要、状态、耗时、错误信息、step_index），并且可被永久回放（不被自动清理）。
22. 作为 audit 团队，我希望刷新页面或断网重连后，SSE 时间线能从断点恢复而不是从头开始。

### 知识与修复侧

23. 作为 SRE，我希望团队的 runbook 用 Markdown 写在仓库里，按统一 frontmatter + 固定章节结构，OnCallPilot 自动入库并按章节切分供 RAG 召回。
24. 作为 SRE，我希望 runbook 加载时如果格式不合规会立刻 fail-fast，而不是污染向量索引导致后续召回出乱。
25. 作为 SRE，我希望某条 runbook 显式声明它覆盖哪些 service / alertname，OnCallPilot 调查相应 service 时优先召回它。
26. 作为 on-call 老员工，我希望我处理过的事故自动变成 incident memory 草稿（draft），我有时间时去审阅一下，verify 或 reject，被 verify 的进入团队知识库被未来调查复用。
27. 作为 on-call 工程师，我希望默认只看到 verified 的历史事故记忆，避免被 AI 半信半疑的猜测污染判断；但能在配置上打开包含 draft（带 confidence_penalty 标记）以备需要。
28. 作为 Tech Lead，我希望团队多次发现的同一类根因不会反复被 AI 当作"新发现"重复写入，需要按 service+alertname+root_cause 自动去重。
29. 作为 Service Owner，我希望高置信度的根因判定能自动生成 GitHub Issue（含证据链 + 推荐 action），并把 issue URL 落回 OnCallPilot；如果 GitHub 写权限没开，则落一份草稿 issue 文本（pr_proposal）等我手动建。
30. 作为 Service Owner，我希望 GitHub 工具默认指向我自己的 GHE 或 GitHub.com，**不假设外网可达**，所有 endpoint 都可配置。

### Chat / 主动查询侧

31. 作为 on-call 工程师，我希望除了"事件驱动调查"外，还能主动 chat 问 "payment-api 过去 1 小时怎么样"，AI 调用同一套工具回我 markdown 形式的总结。
32. 作为 on-call 工程师，我希望 chat 是多轮的，AI 记得我前一句问了什么。
33. 作为 on-call 工程师，我希望 chat 时 AI 调的工具同样被 audit、同样能在 SSE 时间线里看到。
34. 作为 on-call 工程师，我希望 chat 时 AI 如果判断"这看起来是个事故"，能给我一个按钮把当前 chat 上下文升级为正式 investigation。

### 治理 / 元数据侧

35. 作为 Platform Engineer，我希望通过 `kubectl apply ServiceCatalog` 注册服务（tier / owner_team / GitHub repo / runbook 关联 / Prom & Loki label 覆盖），OnCallPilot 自动同步并影响后续工具调用与 RAG 召回。
36. 作为 Platform Engineer，我希望某个服务的 Prom 实际用 `job` 而不是 `service` label 时，能在 ServiceCatalog 里覆盖标签名，不强制业务侧统一改 label。
37. 作为 Platform Engineer，我希望 Service Catalog 是产品的权威源（CRD），后端只读同步，不存在"两份配置打架"。

### 部署与运维侧

38. 作为 Platform Engineer，我希望通过 `helm install` 一键部署 OnCallPilot，所有组件（api、worker、controller、web）+ RBAC + CRD + 数据库迁移 Job 一次到位。
39. 作为 Platform Engineer，我希望 OnCallPilot 不打包基础设施（Postgres、Redis、Prometheus、Loki、LLM endpoint 全部由我自己提供），通过统一 YAML 配置文件注入。
40. 作为 Platform Engineer，我希望敏感信息（DB 密码、API key、GitHub token）走 K8s Secret，YAML 配置里只有 `*_env: VAR_NAME` 占位，不会被误提交到 git。
41. 作为 Platform Engineer，我希望配置文件缺失关键字段时进程 fail-fast 立刻报错，而不是用静默缺省值掩盖问题。
42. 作为 SRE，我希望 LLM endpoint 走 OpenAI 协议，能任意切换 OpenAI / Azure / vLLM / DeepSeek / 私有模型，**只改配置不改代码**。
43. 作为 SRE，我希望集群无外网时所有工具（GitHub / LLM）能指向内部部署的 endpoint（GHE / 私有模型），整套产品仍可运行。
44. 作为 SRE，我希望某个数据源 endpoint 缺失（如未配置 Loki）时，相应工具家族自动不注册，整个 graph 仍能跑，不崩溃。
45. 作为 SRE，我希望 Helm chart 提供 `/readyz` 探针，K8s 会真的等 PG/Redis/LLM 可达后才把流量打进来。
46. 作为 SRE，我希望日志全部 stdout + JSON 结构化，被集群日志栈统一收集。

### 可观测 / 调试侧

47. 作为 AI 平台工程师，我希望 LangGraph 内每一次 LLM 调用 / 工具调用 / 节点流转都被 trace 到 Langfuse，能看到完整 prompt、completion、token usage。
48. 作为 AI 平台工程师，我希望 Dashboard 投资 detail 页能跳到 Langfuse 看对应 session 的 trace，不必复制 session_id 自己搜。
49. 作为 AI 平台工程师，我希望 Langfuse 与产品业务数据严格解耦（业务可审计数据在 DB，trace 可关），未来要换成 OpenTelemetry 时只换 Tracer 实现。
50. 作为 audit 团队，我希望"业务可审计"的数据（tool_calls / evidence / report）永远在 DB，与 Langfuse trace 是两套独立职责。

### 人工干预侧

51. 作为 on-call 工程师，我希望能从 Dashboard 关闭一个 incident（带 reason），状态变 resolved。
52. 作为 on-call 工程师，我希望能从 Dashboard 重开一个已关闭的 incident（带 reason），并能看到 reopen_count 增长。
53. 作为 on-call 工程师，我希望能在 Dashboard 对同一个 incident 触发再次调查（比如第一次证据不充分），新 session 与旧 session 并列展示。
54. 作为 on-call 老员工，我希望能在 Dashboard 上对 incident memory draft 做 verify / reject / edit，决定哪些被沉淀进知识库。

### 国际化与可读性

55. 作为中文使用者，我希望 Dashboard UI、runbook、AI 报告默认中文，但每一处文案都走 i18n 字典 key（不硬编码），未来加英文 / 日文不需要重写。
56. 作为 SRE，我希望 LLM 用户可见输出语言可配置（默认 zh / auto / en），auto 模式跟随告警语言自适应。
57. 作为 AI 平台工程师，我希望 System prompt 强制英文（instruction following 稳定性最佳实践），与界面语言无关。

### 验证与端到端

58. 作为新接入运营者，我希望仓库自带一个参考工作负载（`samples/payment-api`），跑起来就能在没有真实业务的情况下验证 OnCallPilot 端到端正确性。
59. 作为新接入运营者，我希望仓库提供一个文档化的参考场景（payment-api HighErrorRate）描述如何手动触发故障、看到完整调查链路。
60. 作为 QA，我希望参考场景能用 chaos-mesh 一键自动触发 + 自动验证（不再依赖手工 kubectl 操作）。

## Implementation Decisions

### 整体架构

5 个独立进程，进程边界与代码包 1:1：

- **api**：FastAPI 模块化单体。HTTP API、SSE、把 investigation 任务入 arq 队列、对 CRD 控制器与前端的统一接口。
- **worker**：arq worker。从 Redis 队列取 investigation 任务执行 LangGraph，写 DB + 事件总线。
- **controller**：kopf 控制器。watch `ServiceCatalog` / `HealthCheck` / `ScheduledHealthCheck` 三个 CRD，调 api 接口。
- **web**：Next.js App Router。纯前端，仅消费 api + SSE。
- **samples/payment-api**：参考工作负载，仅正常态；生产环境部署可选启用。

Helm Chart 是**唯一**交付形态，不维护裸 manifests，避免双轨。

OnCallPilot **不打包**基础设施（Postgres + pgvector、Redis、Prometheus、Loki、OpenAI 兼容 LLM endpoint、可选 Langfuse、可选 GitHub），运营者通过统一 YAML 配置文件 + K8s Secret 注入。

### Deep Modules（需要在 OnCallPilot 内长期稳定的核心抽象）

以下模块是产品的"深模块"——接口简单稳定、内部封装大量逻辑、可独立测试、可在不替换上层代码的前提下替换实现：

1. **`ToolRegistry` + `ToolResult` 契约**：所有工具实现同一签名（async callable + 统一返回），上层 graph 与 audit 完全不感知工具种类。
2. **`Tracer`**：observability 抽象。NoOp / Langfuse / 未来 OTel 实现，graph 与 LLM 调用层不耦合具体 SDK。
3. **`EventBus`**：实时事件总线抽象。首发用 Redis Streams（保证 history replay + Last-Event-ID），未来可换 NATS/Kafka。
4. **`ServiceCatalogRepository`**：服务元数据读取抽象。首发实现是"DB 表（被 CRD 控制器同步进来）"，未来可加多源合并。
5. **`EmbeddingClient`**：OpenAI 协议兼容 embeddings 客户端，模型与维度由配置驱动。
6. **`InvestigationGraph` / `ChatGraph`**：两套 LangGraph，共享 ToolRegistry / LLM client / audit / Tracer / EventBus。
7. **`AuditService`**：所有工具调用统一落库的窄接口，节点不直接写 DB。
8. **`RemediationService`**：根据 verdict / confidence / write_enabled 决策 GitHub Issue / PR proposal / Manual Action 的策略层。
9. **`HealthCheckResultMapper`**：把 final_report.verdict 映射到 CRD `status.result`（pass/fail/error）的纯函数层。
10. **`AlertFingerprintDeduper`**：基于 Alertmanager fingerprint 的 incident 状态机决策层。

### 关键技术决策

- **执行模型**：API 层不执行 graph，全部入 arq 队列，worker 独立进程消费。job_id = `investigation:{session_id}`，靠 session_id 自然唯一保证幂等。
- **决策机制**：LangGraph 单 agent loop。开局固定健康探测，主循环 LLM tool calling 决策，三条护栏（去重、家族禁用阈值、连续 finish 收敛）。`MAX_TOOL_STEPS=10`（工作预算）、`HARD_STEP_CAP=20`（防御上限）。
- **持久化**：PostgreSQL + pgvector，SQLAlchemy 2.x async + Alembic。incident 用 alert fingerprint 做部分唯一索引实现幂等；tool_calls 跨指 investigation_session / chat_session 通过 CHECK 约束二选一；runbook 切 chunk 按章节，retrieval 用稳定 runbook_id 引用；incident_memory dedup_key = sha256(service|alertname|normalize(root_cause))。
- **LLM**：纯 OpenAI 协议（`openai` SDK），通过 `base_url / api_key / model` 三件套配置，支持 OpenAI / Azure / vLLM / DeepSeek / 私有模型任意切换。Embedding 同理走 `/v1/embeddings`，模型与维度（首次建表即固化）由配置驱动。
- **实时性**：Redis Streams + SSE，事件类型 `session.started/step.planned/tool.started/tool.completed/evidence.added/session.completed/session.failed`，支持 Last-Event-ID 重连与历史 replay。
- **CRD**：`ServiceCatalog`（治理）/ `HealthCheck`（单次巡检）/ `ScheduledHealthCheck`（cron 巡检）。控制器单 replica + Recreate + kopf `@timer + croniter`。多副本 + peering 留待后续。
- **修复策略**：confidence ≥ 0.7 + write_enabled → GitHub Issue + 落 url；write_enabled 关 → pr_proposal 草稿；confidence 低 → manual_action。
- **配置**：单 YAML 文件 + `ONCALLPILOT_CONFIG` env 指向 + `*_env: VAR_NAME` 占位敏感信息。fail-fast，不内置缺省。
- **Runbook 契约**：强 frontmatter（id/title/services/alertnames/tier/related_runbooks/owner_team/version/language）+ 7 个固定章节（Symptoms / Common Causes / Prometheus Queries / Loki Queries / Immediate Mitigation / Long-term Remediation / Escalation）。按章节切 chunk，`runbook_id#section` 稳定引用。
- **i18n**：dashboard 默认 `zh-CN`，next-intl 字典；System prompt 全英；LLM 用户可见输出 `output_language_policy` 配置（默认 zh）。
- **观测**：DB audit（业务可审计，永久）+ Langfuse trace（开发运维诊断，可关）严格分职。
- **部署**：Helm Chart 唯一形态，migration Job 用 Helm hook pre-install/pre-upgrade 跑 alembic upgrade。

### Final Report Schema（产品核心数据契约）

```
{
  summary, verdict (healthy|unhealthy|inconclusive), verdict_reason, confidence,
  suspected_root_cause, impact,
  evidence: [{ type, summary, source, confidence }],
  recommended_actions: [string],
  related_runbook: [{ runbook_id, title }],
  related_historical_incidents: [{ id, summary }],
  remediation_proposal: { type, title, description, url?, diff? }
}
```

### Incident 状态机

`open / investigating / resolved / error`。webhook firing 进入 open；worker 拉起后 investigating；webhook resolved 或人工 close 进入 resolved；hard cap / unhandled error 进入 error。re-investigate 不改 incident 状态，只新增 session。

## Testing Decisions

### 好测试的判定标准

- 只测**外部可观察行为**（HTTP 响应、DB 落地行、Redis Stream 事件、SSE 事件序列），不测私有实现细节。
- 不测 LLM 的"质量"（"AI 是不是真的诊断对了"），只测产品契约（"工具被调了、evidence 被写了、report schema 校验通过、verdict 字段存在"）。LLM 质量回归通过 Langfuse 持续 prompt eval 单独治理。
- 同一行为只在最贴近的层测一次；不在 unit 与 integration 之间复制覆盖。
- 测试失败的报告必须明确指出"哪个外部行为被破坏"，不是"哪个内部变量值不对"。

### 测试分层

- **unit**：纯函数与边界逻辑。HTTP 客户端边界用 `respx` 之类做 unit 范围 mock。秒级反馈，CI 默认运行。
- **integration**：直连真实基础设施（PG+pgvector / Redis / Prom / Loki / 真 LLM endpoint）。endpoint 从 `ONCALLPILOT_CONFIG` 读；缺失则 `skip` 并明确打印缺失项，不引入假 fixture（与"不打包基础设施"原则一致）。
- **end-to-end 参考场景**：基于 `samples/payment-api` + 手工故障操作（或 chaos-mesh 自动化）跑一次完整链路，对照 `docs/scenarios/.../validation.md` 验收清单逐项核查。

### 重点要测试的模块

- `AlertFingerprintDeduper`：fingerprint 幂等 + firing/resolved 状态机的全部分支必须有 integration 覆盖（最容易因实现细节回归）。
- `ToolRegistry` 注册 / 禁用 / 家族阈值熔断：unit。
- 每个 tool 适配器：unit（respx mock）+ integration（真 endpoint）。
- `EventBus` Redis Streams 实现：integration（含 Last-Event-ID 重连）。
- LangGraph happy path：integration，工具用 fixture-replaced fake registry（避免 LLM 不确定性），断言 audit 写入 + 报告 schema + verdict 存在 + SSE 事件序列。
- `HealthCheckResultMapper`：pure unit，覆盖三档映射。
- Runbook 解析与 RAG 召回：unit（解析校验失败必须 raise）+ integration（pgvector 真召回）。
- Incident memory dedup + draft/verified 过滤：integration。
- CRD 控制器三套 handler：unit（cron + verdict 映射）+ integration（真集群 / kind）。
- Helm chart 渲染：`helm template` + `kubectl apply --dry-run=server` 在 CI 跑通即可，不做 e2e。

### 测试基础设施立场

- **OnCallPilot 不在仓库内打包基础设施**：不引入 testcontainers、不内置 docker-compose、不写假 exporter fixture。这与产品级"基础设施由运营者提供"的口径一致。
- 运营者 / 开发者在 `ONCALLPILOT_CONFIG` 指定的真实基础设施上运行 integration 套件。CI 环境同理（在 CI 起一组真服务，或指向预备测试环境）。

## Out of Scope

以下能力**长期内**也不计划做（即使到产品成熟阶段也不做，除非市场强烈要求）：

- **自动生产变更**：OnCallPilot 长期保持只读 + 提案，不直接 kubectl apply / scale / restart 生产资源。`create_issue` 是唯一的写操作。
- **多 agent 编排**：单 agent + 工具调用是核心架构，不做规划者 + 执行者 + 评审者这种复杂多 agent 链。
- **自动 PR diff 生成**：MVP 不做，长期也只做"提案文本 + 建议 diff 片段"，不做端到端的代码生成 + 提交。
- **内置身份系统**：OnCallPilot 不做自有用户/角色/权限，长期通过 OIDC / mTLS / 集成既有 IdP 解决，不重造 ITSM 账号体系。
- **完整 ITSM 替代**：assignee 自动分派、SLA timer、postmortem 模板编辑器、merge incidents 这些重 ITSM 功能不做，OnCallPilot 与 PagerDuty / Opsgenie / Jira 协同，不替代。
- **告警规则编辑**：OnCallPilot 不管告警规则配置，是 Alertmanager / Prom 的下游消费者。
- **多租户硬隔离**：长期通过 K8s namespace + RBAC 提供软隔离，不做应用层的 tenant_id 字段穿透。
- **自有 trace 后端 / Dashboard 复刻 Langfuse**：observability 用 Langfuse / OTel，不自造。
- **闭源**：产品定位为开源 + 企业增强，核心一直 OSS。

## Further Notes

### 里程碑切分原则

后续每个版本（v0.1、v0.2、…）以独立 PRD 切分，遵循：

- **v0.1（首个可发布开源版本）**：能让用户部署、发一条告警、看到完整 AI 调查链路 + 报告。不做 GitHub、不做 ServiceCatalog、不做 ScheduledHealthCheck、不做 Chat、不做 Langfuse、不做多语言、不做 chaos-mesh、不做多副本。详见独立 PRD `2026-05-27-v0.1-open-source.md`。
- **v0.2+**：按用户反馈与社区压力排序补齐 Vision 中的剩余能力。

### 与上游设计文档的关系

- 长期完整设计权威源：`docs/superpowers/specs/2026-05-27-oncallpilot-mvp-design.md`
- 长期完整实施任务源：`docs/superpowers/plans/2026-05-27-oncallpilot-mvp-implementation.md`
- 本 PRD 是 Vision 层"产品意图"的浓缩，遇与 spec/plan 冲突时以 spec/plan 为准（spec/plan 经过详细 grill 与决策收敛）。

### 命名与口径

- 一律产品级措辞，避免出现弱化产品定位的临时性表述。
- "参考场景"对应英文 "reference scenario"，"参考工作负载"对应 "reference workload"。
- v0.1 等版本号是工程里程碑命名，不出现在产品对外描述中。
