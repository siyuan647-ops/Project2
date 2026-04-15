# 多智能体金融决策平台 - 技术文档

## 目录

- [一、项目概述](#一项目概述)
- [二、技术栈详解](#二技术栈详解)
- [三、系统架构设计](#三系统架构设计)
- [四、项目文件详解](#四项目文件详解)
- [五、核心技术流程](#五核心技术流程)
- [六、Agent 深度技术解析](#六agent-深度技术解析)
- [七、扩展面试专题](#七扩展面试专题)

---

## 一、项目概述

本项目是一个 **多智能体金融决策平台**，包含两大核心模块：

1. **多智能体投资顾问** — 用户输入股票代码，三个 AI 智能体（研究分析师、财务分析师、投资顾问）协同工作，自动搜集新闻、分析财务数据，生成完整的投资建议报告。支持多轮对话追问，采用同步 API 设计（非流式）。

2. **AI 信用风险预测引擎** — 用户上传贷款申请人名单，基于 XGBoost 模型批量预测信用等级（P1-P4），辅助放贷决策。

---

## 二、技术栈详解

### 2.1 前端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **Vue 3** | 3.5+ | 前端框架，Composition API (`<script setup>`) |
| **Vite** | 6.x | 构建工具，热更新与打包优化 |
| **Vue Router 4** | 4.5+ | 前端路由，History 模式 |
| **Element Plus** | 2.9+ | UI 组件库 |
| **Axios** | 1.7+ | HTTP 客户端，同步 API 调用 |
| **Marked.js** | 15.x | Markdown 渲染器 |

### 2.2 后端技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **Python** | 3.11 | 后端语言 |
| **FastAPI** | 0.115+ | Web 框架，异步支持，自动 OpenAPI 文档 |
| **Uvicorn** | 0.34+ | ASGI 服务器 |
| **Pydantic Settings** | 2.x | 类型安全的配置管理 |
| **SlowAPI** | 0.1.9+ | 请求限流（基于 IP） |

### 2.3 AI / 智能体技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| **AutoGen** | 0.4+ | 多智能体编排框架，`SelectorGroupChat` / `RoundRobinGroupChat` |
| **Kimi K2.5** | — | LLM，兼容 OpenAI API 协议（Moonshot） |
| **sentence-transformers** | 3.x | 文本嵌入模型 (`all-MiniLM-L6-v2`)，384 维向量 |

### 2.4 数据库

| 技术 | 版本 | 用途 |
|------|------|------|
| **PostgreSQL** | 16 | 关系型数据库 |
| **pgvector** | — | PostgreSQL 向量扩展，支持向量相似度搜索 |
| **asyncpg** | 0.29+ | 异步 PostgreSQL 驱动 |

### 2.5 机器学习

| 技术 | 用途 |
|------|------|
| **XGBoost** | 梯度提升树模型，多分类信用评估 (P1-P4) |
| **scikit-learn** | 数据预处理、评估指标 |
| **Pandas / NumPy** | 数据处理与特征工程 |
| **Joblib** | 模型序列化 |

### 2.6 数据源

| 技术 | 用途 |
|------|------|
| **yfinance** | Yahoo Finance 数据获取 |
| **DuckDuckGo Search** | 新闻搜索（无需 API Key） |
| **Tavily API** | 高级新闻搜索（可选，需配置） |
| **Polygon.io** | 专业股票数据（可选，需配置） |

---

## 三、系统架构设计

### 3.1 整体架构

```
用户浏览器
   │
   ▼
┌─────────────────────────────────────────────────────┐
│ Nginx (前端容器 port 80)                             │
│  ├─ /          → Vue 3 SPA 静态文件                  │
│  └─ /api/*     → 反向代理到 Backend:8000             │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP (同步 API)
                       ▼
┌─────────────────────────────────────────────────────┐
│ FastAPI Backend (port 8000)                          │
│                                                      │
│  中间件层:                                           │
│  ├─ CORSMiddleware        (跨域)                     │
│  ├─ AuditMiddleware       (审计日志)                 │
│  ├─ API Key Auth          (认证)                     │
│  └─ SlowAPI Limiter       (限流)                     │
│                                                      │
│  路由层:                                             │
│  ├─ /api/advisor/*  → advisor.py (同步 API)          │
│  ├─ /api/credit/*   → credit.py                      │
│  └─ /api/health     → 健康检查                       │
│                                                      │
│  业务层:                                             │
│  ├─ agents/parallel_analysis.py  (并行分析优化)      │
│  ├─ agents/group_chat.py         (智能体编排)        │
│  ├─ routing/router.py            (意图路由)          │
│  └─ ml/predict.py                (信用预测)          │
│                                                      │
│  存储层:                                             │
│  └─ storage.py → asyncpg 连接池                      │
└──────────────────────┬──────────────────────────────┘
                       │ asyncpg
                       ▼
┌─────────────────────────────────────────────────────┐
│ PostgreSQL 16 + pgvector (port 5432)                 │
│  ├─ conversations 表 (含 last_compressed_turn,      │
│  │                    last_reflection_turn 字段)      │
│  ├─ messages 表 (含 embedding vector(384) 列)        │
│  ├─ memory_chunks 表 (RAG 向量检索)                  │
│  ├─ **conversation_summaries** 表 (记忆压缩摘要)     │
│  ├─ **meta_memories** 表 (元认知记忆:偏好/修正/模式) │
│  └─ **tool_call_logs** 表 (工具调用日志，幻觉审计)   │
└─────────────────────────────────────────────────────┘
```

### 3.2 多智能体协作流程（并行优化版）

```
用户输入股票代码 (如 AAPL)
         │
         ▼
┌─────────────────────────────────────────────┐
│  Phase 1: 并行执行 ( asyncio.gather )        │
│                                             │
│  ┌─────────────────┐  ┌─────────────────┐   │
│  │ Research_Analyst│  │Financial_Analyst│   │
│  │                 │  │                 │   │
│  │ • 搜索新闻       │  │ • 财务报表       │   │
│  │ • 公司信息       │  │ • 价格历史       │   │
│  │ • 行业趋势       │  │ • 估值分析       │   │
│  │                 │  │                 │   │
│  └────────┬────────┘  └────────┬────────┘   │
│           │                    │            │
│           └────────┬───────────┘            │
│                    │                       │
│                    ▼                       │
│         Phase 2: 综合报告                   │
│                                             │
│         Investment_Advisor                  │
│         • 整合研究与财务分析                 │
│         • 生成投资建议报告                   │
│                                             │
└─────────────────────────────────────────────┘
         │
         ▼
    返回完整报告 (同步响应)
```

**关键优化**：
- Research 和 Financial Analyst **并行执行**，减少总耗时约 40-50%
- 使用 `RoundRobinGroupChat` 单智能体模式，避免 `SelectorGroupChat` 单 participant 报错

### 3.3 增强版混合意图路由管线（追问场景）

```
用户追问 "PE是多少？"
         │
   ┌─────▼──────┐
   │ Stage 1:   │ Embedding 粗筛
   │ 向量相似度  │ 与5类例句做余弦相似度
   │            │ → {financial: 0.82, research: 0.35, ...}
   └─────┬──────┘
         │
   ┌─────▼──────┐
   │ Stage 2:   │ 规则引擎
   │ 硬规则匹配  │ "PE" 命中 financial_keywords
   │ 软规则打分  │ → soft_scores={financial: 0.7}
   │            │ 如果 ≥ 0.7 → 直接决策
   └─────┬──────┘
         │ (规则不够自信)
   ┌─────▼──────┐
   │ Stage 3:   │ **RAG意图召回** ⭐新增
   │ 向量检索    │ 从42条意图案例库检索相似案例
   │            │ 相似度≥0.75 → 直接决策
   └─────┬──────┘
         │ (无高置信度匹配)
   ┌─────▼──────┐
   │ Stage 4:   │ **Few-shot LLM** ⭐新增
   │ 意图分类器  │ 基于召回案例构建Few-shot Prompt
   │            │ 支持意图澄清引导
   └─────┬──────┘
         │ (LLM调用失败)
   ┌─────▼──────┐
   │ Stage 5:   │ Fallback LLM
   │ 原始分类器  │ 基础JSON路由决策
   └─────┬──────┘
         │
         ▼
   路由到对应智能体组合执行
   • advisor_only: 仅投资顾问回答
   • research: 研究分析师获取新数据
   • financial: 财务分析师获取新数据
   • full: 重新执行完整三智能体分析
   • unknown: 拒绝非股票相关问题
```

**意图知识库覆盖**：
- 财务指标类（8条）：PE、ROE、现金流、毛利率、EPS等
- 财务风险类（6条）：现金流风险、应收账款、存货、减持等
- 研究分析类（8条）：新闻催化剂、竞争分析、宏观影响、护城河等
- 投资建议类（8条）：择时、仓位管理、止损、目标价等
- 模糊/歧义类（5条）：意图不明确、多因素权衡、跨会话对比等
- 非股票相关（7条）：天气、计算、加密货币、券商推荐等

### 3.4 RAG 五层上下文系统 ⭐升级

```
追问时上下文构建 (_build_context):

Layer 0: Meta-memories (元认知) ⭐新增
         ┌──────────────────────┐
         │ 【用户偏好】关注长期价值 │ ← 从 meta_memories 表
         │ 【自我修正】之前PE算错   │    检索高置信度元记忆
         │ 【互动模式】经常追问细节 │
         └──────────┬───────────┘
                    │
Layer 1: 压缩历史摘要 ⭐升级
         ┌──────────────────────┐
         │ 【历史摘要 | 轮次1-10】│ ← 从 conversation_summaries
         │  "用户分析了AAPL..."   │    表向量检索相关摘要
         └──────────┬───────────┘
                    │
Layer 2: 最近消息（滑动窗口）
         ┌──────────────────────┐
         │ 【近期对话 | 最近8轮】 │ ← 保持最近8轮原始消息
         │ [User] PE是多少？     │    超过阈值触发压缩
         │ [Advisor] AAPL的PE... │
         └──────────┬───────────┘
                    │
Layer 3: 语义检索（RAG）
         ┌──────────────────────┐
         │ 【历史记忆】根据embedding│ ← 从 memory_chunks 表
         │  检索语义相关历史片段    │    余弦距离排序，top-5
         └──────────┬───────────┘
                    │
Layer 4: 工具调用日志 ⭐新增
         ┌──────────────────────┐
         │ 【数据来源】工具调用记录 │ ← 从 tool_call_logs 表
         │  原始数据用于幻觉核查   │    溯源验证Agent回答
         └──────────┬───────────┘
                    │
                    ▼
            拼接为完整上下文
            注入到 Agent prompt
```

**记忆压缩策略**：
- 滑动窗口：保留最近8轮对话原始内容
- 触发阈值：每8轮触发一次LLM摘要生成
- 摘要存储：压缩后的历史存入 conversation_summaries 表
- 向量索引：摘要向量化支持语义检索

---

## 四、项目文件详解

### 4.1 根目录

| 文件 | 作用 |
|------|------|
| `docker-compose.yml` | Docker 三服务编排：PostgreSQL + Backend + Frontend |
| `README.md` | 项目简介与快速启动指南 |
| `CLAUDE.md` | Claude Code 协作配置 |

### 4.2 后端核心 — `backend/app/`

| 文件 | 行数 | 作用 |
|------|------|------|
| `main.py` | ~110 | FastAPI 应用入口，注册中间件， lifespan 管理，路由挂载 |
| `config.py` | ~40 | Pydantic Settings 全局配置（LLM 密钥、数据库 URL、限流等） |
| `storage.py` | ~392 | PostgreSQL + pgvector 存储层，ConversationStore 类，异步 CRUD | 负责：建扩展/表/索引、连接池、会话与消息、向量记忆块、工具审计日志、压缩摘要、元记忆、压缩/反思进度字段。
| `memory_ingest.py` | ~240 | RAG 写入管线，消息分块、embedding、摘要更新 |  如何将对话存入记忆库，确定发送者/消息类型是否为琐碎消息（太短，套话，太长则截断）
| `memory_compression.py` | ~223 | **新增**：滑动窗口记忆压缩，LLM摘要生成 | 保留窗口数为8，窗口>8则压缩
| `memory_reflection.py` | ~340 | **新增**：元认知自省系统，用户偏好/自我修正/互动模式 |

### 4.3 智能体 — `backend/app/agents/`

| 文件 | 行数 | 作用 |
|------|------|------|
| `llm_config.py` | ~18 | Kimi K2.5 OpenAI 兼容客户端工厂 |
| `research_analyst.py` | ~42 | 研究分析师智能体（工具：新闻搜索、公司信息） |
| `financial_analyst.py` | ~44 | 财务分析师智能体（工具：财务报表、价格历史） |
| `investment_advisor.py` | ~40 | 投资顾问智能体（纯推理，综合报告） |
| `parallel_analysis.py` | ~184 | **核心优化**：并行执行研究+财务分析，再综合 |
| `group_chat.py` | ~220 | 编排中心：追问处理、上下文构建、路由分发 |

### 4.4 路由系统 — `backend/app/routing/`

| 文件 | 行数 | 作用 |
|------|------|------|
| `types.py` | ~40 | 路由类型定义（Route、RoutingDecision 等） |
| `embeddings.py` | ~170 | 向量粗筛层，sentence-transformers 封装 |
| `rules.py` | ~110 | 规则引擎层，硬规则+软规则匹配 |
| `router.py` | ~195 | 路由管线编排器（embedding → rules → LLM → fallback） |
| `enhanced_router.py` | ~383 | **新增**：增强版路由，集成RAG意图识别和Few-shot学习 |
| `intent_knowledge_base.py` | ~471 | **新增**：42条垂类意图案例库（财务/研究/建议/模糊/无关） |
| `rag_intent_retriever.py` | ~297 | **新增**：RAG意图召回，基于向量相似度的案例检索 |
| `intent_prompt_builder.py` | ~296 | **新增**：Few-shot Prompt构建器，支持意图澄清引导 |

### 4.5 API 端点 — `backend/app/routers/`

| 文件 | 行数 | 作用 |
|------|------|------|
| `advisor.py` | ~164 | **投资顾问同步 API**：创建会话、初始分析、追问、一次性分析 |
| `credit.py` | ~120 | 信用预测 API：上传预测、下载结果、下载模板 |

**API 变更（重要）**：
- 从 SSE 流式改为 **同步 REST API**
- `POST /conversations/{conv_id}/initial` → 返回 `InitialAnalysisResponse`
- `POST /conversations/{conv_id}/messages` → 返回 `FollowUpResponse`（含 routing 元数据）

### 4.6 数据模型 — `backend/app/schemas/`

| 文件 | 行数 | 作用 |
|------|------|------|
| `models.py` | ~100 | Pydantic 模型，含 Prompt 注入防护验证器 |

### 4.7 工具 — `backend/app/tools/`

| 文件 | 行数 | 作用 |
|------|------|------|
| `stock_data.py` | ~240 | 股票数据获取（yfinance + Polygon.io 双源） | 优先走 Polygon REST,可获得公司概况、财务报表摘要、价格历史。
| `news_search.py` | ~120 | 新闻搜索（Tavily + DuckDuckGo 双源） | 先用 Tavily，失败或未配置 key 时 退回 DuckDuckGo。返回 Markdown 风格字符串，供模型直接读。

### 4.8 前端 — `frontend/`

| 文件 | 作用 |
|------|------|
| `src/api/index.js` | API 客户端（Axios，非 SSE） |
| `src/views/AdvisorView.vue` | 投资顾问页面（同步加载状态展示） |
| `src/views/CreditView.vue` | 信用预测页面 |

---

## 五、核心技术流程

### 5.1 RAG意图识别管线 ⭐新增

```python
# enhanced_router.py 五级路由管线

async def enhanced_route_followup(ticker, question, ...):
    # Stage 1: Embedding 粗筛
    emb_signal = emb_service.compute_signal(query=question)

    # Stage 2: 规则引擎（硬规则/软规则）
    rule_signal = evaluate_rules(question)
    if rule_signal.hard_route:  # 直接返回
        return RoutingDecision(route=rule_signal.hard_route, ...)

    # Stage 3: RAG意图召回 ⭐
    retrieved_cases = await retriever.retrieve_similar_intents(
        query=question, top_k=5, similarity_threshold=0.5
    )
    high_confidence_route = retriever.get_high_confidence_route(
        retrieved_cases, threshold=0.75
    )
    if high_confidence_route:  # 直接决策
        return RoutingDecision(route=high_confidence_route, source="rag_direct")

    # Stage 4: Few-shot LLM意图识别 ⭐
    prompt = build_few_shot_intent_prompt(
        user_query=question,
        retrieved_cases=retrieved_cases,  # 注入相似案例
        ...
    )
    llm_result = await client.create([UserMessage(content=prompt)])
    parsed = parse_intent_response(llm_result.content)

    # Stage 5: Fallback到原始LLM
    return await _original_llm_route(...)
```

**关键设计**：
- 80%简单问题在前两级快速决策（<10ms）
- RAG召回使用内存模式，无需数据库依赖
- Few-shot Prompt包含3个多样化案例
- 支持意图澄清引导（needs_clarification）

---

### 5.2 记忆压缩与滑动窗口 ⭐新增

```python
# memory_compression.py 核心逻辑

MAX_WINDOW_SIZE = 8      # 保留最近8轮原始消息
COMPRESSION_THRESHOLD = 8  # 每8轮触发压缩

async def check_and_compress_memory(conversation_id: str) -> bool:
    # 计算需要压缩的轮次
    turns_to_compress = latest_turn - last_compressed - MAX_WINDOW_SIZE

    if turns_to_compress >= COMPRESSION_THRESHOLD:
        # 获取待压缩消息
        messages = await store.get_messages_in_range(
            start_turn=last_compressed + 1,
            end_turn=latest_turn - MAX_WINDOW_SIZE
        )

        # LLM生成摘要
        summary = await generate_llm_summary(conversation_id, messages)

        # 保存摘要和embedding
        await store.save_summary(
            conversation_id=conversation_id,
            content=summary,
            summary_type="compressed_history",
            turn_range=f"{start}-{end}",
            message_count=len(messages)
        )

        # 更新最后压缩轮次
        await store.update_last_compressed_turn(conv_id, end_turn)
```

**压缩策略**：
- 保留最近8轮：保证短期记忆完整
- LLM摘要：提取关键信息（关注维度、偏好、结论）
- 启发式Fallback：LLM失败时拼接最长3条消息
- 向量索引：摘要向量化支持语义检索

---

### 5.3 元认知自省系统 ⭐新增

```python
# memory_reflection.py 三种反射类型

async def trigger_reflection(conversation_id: str, current_turn: int):
    if current_turn - last_reflection < REFLECTION_INTERVAL:
        return  # 每10轮触发一次

    # 并行执行三种反射
    reflections = await asyncio.gather(
        reflect_user_preferences(conversation_id, messages),
        reflect_self_corrections(conversation_id, messages),
        reflect_interaction_patterns(conversation_id, messages),
        return_exceptions=True
    )

    # 保存高置信度元记忆（confidence >= 0.6）
    for reflection in valid_reflections:
        await store.save_meta_memory(
            conversation_id=conversation_id,
            memory_type=reflection["type"],  # user_preference/self_correction/interaction_pattern
            content=reflection["content"],
            evidence=reflection["evidence"],
            confidence=reflection["confidence"]
        )
```

**元记忆类型**：
| 类型 | 描述 | 应用场景 |
|------|------|----------|
| `user_preference` | 用户偏好（详细vs简洁、关注维度） | 调整回答风格 |
| `self_correction` | 自我修正（错误数据、误解问题） | 避免重复错误 |
| `interaction_pattern` | 互动模式（追问频率、质疑倾向） | 调整交互策略 |

---

### 5.5 并行分析优化

```python
# parallel_analysis.py 核心逻辑

async def run_parallel_analysis(ticker: str) -> str:
    # Phase 1: Research 和 Financial 并行执行
    research_task = _run_research_analysis(ticker)
    financial_task = _run_financial_analysis(ticker)

    research_result, financial_result = await asyncio.gather(
        research_task, financial_task, return_exceptions=True
    )

    # Phase 2: Investment Advisor 综合
    report = await _run_investment_synthesis(
        ticker, research_result, financial_result
    )
    return report
```

**性能提升**：
- 串行执行：Research (2-3min) → Financial (2-3min) → Advisor (1min) = **5-7min**
- 并行执行：max(Research, Financial) + Advisor = **3-4min**（节省 40-50%）

### 5.6 字数控制优化

```python
# group_chat.py 中的 prompt 优化

"Provide a comprehensive and detailed answer (at least 300 words). "
"CRITICAL: Always respond to the user in fluent Professional Chinese."
```

### 5.7 SelectorGroupChat 单 Participant 修复

**问题**：`SelectorGroupChat` 要求至少 2 个 participants，单 advisor 场景报错

**解决**：使用 `RoundRobinGroupChat` 替代（支持单 participant）

```python
# 修复前（报错）
team = SelectorGroupChat(participants=[advisor], ...)  # ❌ ValueError

# 修复后（正常）
team = RoundRobinGroupChat(participants=[advisor], ...)  # ✅ 支持单 participant
```

### 5.8 Prompt 注入防护

```python
# schemas/models.py

@field_validator("question")
def reject_prompt_injection(cls, v: str) -> str:
    _INJECTION_PATTERNS = re.compile(
        r"ignore\s+(previous|above|all)\s+instructions"
        r"|system\s*:\s*you\s+are"
        r"|忽略.{0,6}(指令|规则|约束)",
        re.IGNORECASE,
    )
    if _INJECTION_PATTERNS.search(v):
        raise ValueError("输入内容包含不允许的指令")
    return v
```

### 5.9 向量检索 (pgvector)

```sql
-- 余弦距离搜索最相似的记忆片段
SELECT content, (embedding <=> $1::vector) AS distance
FROM memory_chunks
WHERE conversation_id = $2 AND embedding IS NOT NULL
ORDER BY distance ASC
LIMIT 5;
```

---

## 六、Agent 深度技术解析

### 6.1 AutoGen 架构与 Agent 类型

#### AssistantAgent 内部机制

```python
# AutoGen AssistantAgent 执行流程

用户 Task
    │
    ▼
┌─────────────────────────────────────┐
│ 1. LLM 推理                          │
│    • 接收 system_prompt + task      │
│    • 决定是否调用工具（Function Call）│
│    • 生成自然语言或工具调用请求      │
└──────────────┬──────────────────────┘
               │
         ┌─────▼─────┐
         │ 是工具调用？│
         └─────┬─────┘
      否 /    │    \ 是
            ▼       ▼
    直接返回文本   执行工具函数
                     │
                     ▼
              将工具结果
              重新注入 LLM
                     │
                     ▼
              生成最终回复
```

**核心组件**：
- `system_message`: 定义 Agent 角色和能力边界
- `tools`: 函数工具列表，LLM 通过 Function Calling 调用
- `model_client`: LLM 客户端（本项目使用 OpenAI 兼容接口）

#### GroupChat 编排模式对比

| 模式 | 适用场景 | 特点 |
|------|----------|------|
| `RoundRobinGroupChat` | 固定顺序执行 | 按 participants 列表顺序轮流发言，适合单 Agent 或固定流程 |
| `SelectorGroupChat` | 动态调度 | LLM 选择下一个发言者，适合多 Agent 协作，需 ≥2 participants |

### 6.2 Function Calling 实现细节

```python
# research_analyst.py - 工具注册示例

from app.tools.stock_data import get_stock_info
from app.tools.news_search import search_company_news

research_analyst = AssistantAgent(
    name="Research_Analyst",
    system_message="""You are a research analyst...""",
    model_client=get_model_client(),
    tools=[get_stock_info, search_company_news],  # 工具注册
)
```

**Function Calling 执行流程**：

1. **工具描述生成**：AutoGen 通过函数签名自动生成 JSON Schema
2. **LLM 决策**：模型根据上下文决定是否需要调用工具
3. **参数提取**：LLM 从对话中提取参数值
4. **本地执行**：AutoGen 在本地 Python 环境执行函数
5. **结果回传**：将工具返回值注入对话历史
6. **最终生成**：LLM 基于工具结果生成自然语言回复

### 6.3 Agent 状态管理与消息流

```
单次分析的消息状态流转：

run_initial_analysis(ticker)
    │
    ├──► _run_research_analysis()
    │      ├──► [System] System message
    │      ├──► [User] Task prompt
    │      ├──► [Assistant] Thought + Tool Calls
    │      ├──► [Tool] Tool results
    │      └──► [Assistant] Research Analysis Complete
    │
    ├──► _run_financial_analysis() (并行)
    │      └──► ... 类似流程
    │
    └──► _run_investment_synthesis()
           ├──► 接收 Research + Financial 结果
           ├──► [System] System message
           ├──► [User] Synthesis task
           └──► [Assistant] Final Report
```

**关键状态**：
- `TaskResult.messages`: 完整对话历史
- `message.source`: 标识消息来源（Agent 名称）
- `message.content`: 消息内容（文本或工具调用）

### 6.4 终止条件设计

```python
# 多层终止条件组合

from autogen_agentchat.conditions import (
    MaxMessageTermination,
    TextMentionTermination,
)

# 组合终止条件：满足任一即终止
termination = (
    TextMentionTermination("ANALYSIS COMPLETE", sources=["Agent_Name"])
    | MaxMessageTermination(10)  # 兜底保护
)
```

**设计原则**：
1. **明确信号**：Agent 输出特定文本表示完成
2. **来源限制**：`sources` 参数确保只有特定 Agent 的信号有效
3. **最大轮次**：防止无限循环的兜底机制

### 6.5 Prompt 工程策略

#### System Prompt 结构

```python
# investment_advisor.py - 系统提示模板

system_message="""You are an Investment Advisor AI.

## Your Role
Synthesize research and financial analysis into actionable investment recommendations.

## Output Format
Always respond in Professional Chinese with:
1. Executive Summary (执行摘要)
2. Key Risks (主要风险)
3. Final Recommendation (最终投资建议)

## Constraints
- Always end with "INVESTMENT ADVISORY REPORT COMPLETE"
- Provide detailed analysis (at least 300 words)
- Include disclaimer in both English and Chinese

## Disclaimer Template
[中英文免责声明]
"""
```

**Prompt 设计技巧**：
1. **角色锚定**：明确定义 Agent 身份和能力边界
2. **格式约束**：强制输出结构（Markdown、字数、语言）
3. **终止信号**：要求特定文本作为完成标记
4. **容错指导**：指示 Agent 如何处理数据缺失

### 6.6 工具函数设计最佳实践

```python
# tools/stock_data.py - 工具函数示例

async def get_stock_info(ticker: str) -> str:
    """
    Get company fundamental information.

    Args:
        ticker: Stock ticker symbol (e.g., "AAPL")

    Returns:
        Formatted string with company info or error message
    """
    try:
        # 双源策略：优先 Polygon，回退 Yahoo Finance
        if POLYGON_API_KEY:
            data = await _fetch_from_polygon(ticker)
        else:
            data = await _fetch_from_yfinance(ticker)
        return _format_output(data)
    except Exception as e:
        # 关键：返回友好错误而非抛出异常
        return f"Unable to fetch data for {ticker}: {str(e)}"
```

**设计原则**：
1. **降级策略**：多数据源保证可用性
2. **错误处理**：返回字符串错误信息，不抛异常
3. **参数清晰**：类型注解帮助 LLM 正确传参
4. **文档完整**：docstring 会被转为工具描述

---

## 七、Agent 应用开发岗面试专题

### Q: 为什么从 SSE 流式改为同步 API？

> A: 主要考虑三点。第一，**用户体验**：流式输出字数不可控，往往过短；同步 API 可以强制要求详细回答（如至少300字）。第二，**稳定性**：SSE 在长连接场景下容易超时或断开，同步 API 更可靠。第三，**实现简洁**：同步 API 前端实现更简单，不需要处理复杂的流解析和重连逻辑。作为补偿，我们在前端添加了"分析中，请稍候"的加载提示。

### Q: 并行分析具体是怎么实现的？节省了多少时间？

> A: 使用 Python 的 `asyncio.gather()` 让 Research Analyst 和 Financial Analyst 同时执行，而不是串行等待。两者都完成后，Investment Advisor 再综合两份报告。实际测试节省约 40-50% 时间，从原来的 5-7 分钟缩短到 3-4 分钟。代码里还加了异常处理，如果某个 analyst 失败，不会阻塞整体流程，而是记录错误继续执行。

### Q: 追问时的路由系统是如何工作的？

> A: 设计了一个三级管线：第一层是**向量粗筛**，用 sentence-transformers 计算用户问题与各类意图例句的余弦相似度；第二层是**规则引擎**，硬规则直接匹配（如"重新分析"），软规则正则匹配关键词加分；第三层是**LLM 分类器**，当前两层不够自信时，用 Kimi 做最终决策。这样大部分简单问题在前两级就能快速决策，只有模糊场景才调用 LLM，兼顾速度和准确性。

### Q: 遇到过什么技术难题？如何解决的？

> A: 一个典型问题是 AutoGen 的 `SelectorGroupChat` 要求至少 2 个 participants，但追问时经常只需要 Investment Advisor 单独回答。查源码发现这是框架限制，解决方案是改用 `RoundRobinGroupChat`，它支持单 participant 场景。另一个问题是 LLM 输出字数不稳定，通过在 prompt 中明确要求"at least 300 words"解决了字数过短的问题。

### Q: 什么是 RAG？项目中怎么实现的？

> A: RAG（Retrieval-Augmented Generation）是让 LLM 在生成回答前先检索相关外部知识。项目中实现了三层上下文：对话摘要（全局信息）、最近消息（短期记忆）、pgvector 向量检索（语义相关的历史片段）。每次用户追问时，从这三层构建上下文注入 prompt，让 Agent 能"记住"之前的分析。

### Q: 做了哪些安全机制？

> A: 四层防护：API Key 认证中间件；SlowAPI IP 限流（投资接口 10 次/分钟）；Prompt 注入检测（正则匹配恶意指令）；审计日志记录所有请求。其中 Prompt 注入防护在 Pydantic 模型层实现，命中直接返回 422 错误。

---

### 📌 Agent 核心原理

**Q: 解释一下 Function Calling 的工作原理？项目中是怎么用的？**

> A: Function Calling 是 LLM 的一种能力，让模型可以决定调用外部函数来获取信息或执行操作。工作流程是：首先我在定义 Agent 时通过 `tools` 参数注册可用的函数；当 Agent 运行时，LLM 会分析用户输入，如果判断需要外部数据，它会输出一个结构化的函数调用请求（包含函数名和参数）；AutoGen 框架捕获这个请求，在本地执行实际的 Python 函数；函数执行结果被格式化为文本，重新注入到对话中；LLM 基于这个结果继续推理，最终生成自然语言回复。在我的项目中，Research Analyst 注册了两个工具：`get_stock_info` 和 `search_company_news`，Financial Analyst 也有两个工具用于获取财务数据。

**Q: 为什么选择 AutoGen 而不是其他 Agent 框架（如 LangChain、LlamaIndex）？**

> A: 选择 AutoGen 主要基于三个考虑。第一，**多 Agent 编排能力**，AutoGen 的 GroupChat 模式非常适合我的场景——三个专业 Agent 需要协作完成分析任务，而 LangChain 更偏链式调用。第二，**原生异步支持**，AutoGen 0.4+ 版本基于 asyncio 设计，和我的 FastAPI 后端完美契合。第三，**工具调用抽象**，AutoGen 自动处理 Function Calling 的协议转换，我只需要写普通 Python 函数，不需要手动处理 JSON Schema。当然 LlamaIndex 在 RAG 方面更强，但我的 RAG 需求相对简单（pgvector 即可满足），不需要引入额外的框架。

**Q: 说说 `SelectorGroupChat` 和 `RoundRobinGroupChat` 的区别？**

> A: `RoundRobinGroupChat` 是轮询模式，按照 participants 列表的顺序轮流让每个 Agent 发言一次，适合流程固定的场景，比如单 Agent 执行或确定顺序的多 Agent 协作。`SelectorGroupChat` 更智能，它内部维护一个 LLM-based 的选择器，每轮根据对话上下文动态选择"接下来谁发言"，适合需要灵活调度的复杂协作。但 `SelectorGroupChat` 有硬性要求——至少需要 2 个 participants，这是我项目中遇到坑的地方：追问时经常只需要 Investment Advisor 单独回答，导致报错。最终我的方案是并行分析阶段用 `RoundRobinGroupChat` 分别执行 Research 和 Financial，追问阶段根据路由结果选择使用 `RoundRobinGroupChat`（单 Agent）或 `SelectorGroupChat`（多 Agent）。

**Q: Agent 之间的消息是如何传递的？**

> A: 在 AutoGen 中，消息传递通过 GroupChat 维护的共享对话历史实现。每个 Agent 都是独立的 `AssistantAgent` 实例，它们不直接通信，而是通过 GroupChat 的 `run()` 或 `run_stream()` 方法协调。当调用 `team.run(task)` 时，task 会被转换为第一条消息加入对话历史；然后 GroupChat 根据调度策略选择下一个 Agent，将当前对话历史传给它的 LLM；Agent 生成回复后，回复被添加到共享历史中；循环直到满足终止条件。在我的并行分析设计中，Research 和 Financial 是分别独立运行的（两个独立的 GroupChat），所以它们之间没有直接消息传递，各自的结果由我手动收集后，拼接成新的 task 传给 Investment Advisor。

**Q: 如何控制 Agent 的输出格式和字数？**

> A: 主要通过 System Prompt 的约束来实现。在 Investment Advisor 的 system_message 中，我明确指定了：
> 1. **格式要求**："Format the output in Markdown with clear sections for: 'Executive Summary', 'Key Risks', 'Final Recommendation'"
> 2. **字数要求**："Provide a comprehensive and detailed answer (at least 300 words)"
> 3. **语言要求**："Always respond to the user in fluent Professional Chinese"
> 4. **终止信号**："End your response with 'INVESTMENT ADVISORY REPORT COMPLETE'"
>
> 这些约束通过 LLM 的指令遵循能力生效。如果 LLM 不遵守，还可以通过后处理检查（比如检查字数、关键词）并触发重试，但我的场景中 prompt 约束已经足够可靠。

---

### 📌 工具与数据

**Q: 工具函数设计时有哪些注意事项？**

> A: 我总结了四个要点。第一，**错误处理**，工具函数必须内部捕获异常，返回友好的错误字符串而不是抛出异常，因为异常会中断整个 Agent 流程。第二，**参数类型**，使用 Python 类型注解，帮助 LLM 正确理解参数类型。第三，**文档字符串**，docstring 会被 AutoGen 转换为工具描述，LLM 通过描述决定何时调用该工具，所以要写清楚函数的用途、参数含义、返回值格式。第四，**降级策略**，外部数据源不可靠，我的工具都实现了双源策略（如股票数据优先 Polygon，失败回退到 Yahoo Finance），提高可用性。

**Q: 如果工具调用超时或失败怎么办？**

> A: 我在多个层面做了防护。在工具层，函数内部 try-except 捕获所有异常，返回错误信息字符串，Agent 会基于这个错误信息调整输出（如"无法获取数据，基于有限信息分析..."）。在编排层，使用 `asyncio.gather(return_exceptions=True)` 捕获并行任务的异常，单个任务失败不影响其他任务。在终止条件层，设置 `MaxMessageTermination` 作为兜底，防止 Agent 陷入无限重试。目前没有做工具调用的自动重试，因为 LLM 调用成本较高，失败一次后直接返回错误信息更经济。

**Q: 为什么要用双数据源？具体怎么实现的？**

> A: 双数据源是为了**可靠性**。金融数据 API 经常有限流、故障或数据缺失，单点故障会导致整个分析流程失败。我的实现是优先级策略：优先使用付费 API（如 Polygon、Tavily），如果失败（异常或返回空数据）则自动回退到免费方案（yfinance、DuckDuckGo）。代码里通过 try-except 块实现：先尝试主源，捕获异常后切换备用源。如果都失败，返回"数据获取失败"的提示，Agent 会据此调整分析内容。

---

### 📌 编排与调度

**Q: 多 Agent 编排有哪些常见模式？你的项目用了哪种？**

> A: 常见的多 Agent 模式有三种。**流水线模式**（Pipeline）：Agent 按固定顺序执行，前一个的输出作为后一个的输入，适合有明确依赖链的任务。**协商模式**（Discussion）：多个 Agent 反复讨论直到达成共识，适合需要多角度辩论的场景。**主从模式**（Manager-Worker）：一个 Manager Agent 分配任务给 Worker Agents，汇总结果，适合任务可分解的场景。我的项目用的是**改进版流水线**：Research 和 Financial 并行执行（无依赖），然后 Investment Advisor 综合两者结果。追问场景则用**动态路由**：根据问题类型决定是单 Agent 回答还是多 Agent 协作。

**Q: 追问时的路由决策是如何做的？为什么不用直接让 LLM 判断？**

> A: 我设计了一个**三级路由管线**来平衡速度和准确性。第一级是**向量粗筛**（embedding similarity），计算用户问题与预设意图例句的余弦相似度，<10ms；第二级是**规则引擎**，硬规则直接匹配（如"重新分析"→full），软规则关键词加分（如"PE"→financial），<1ms；第三级是**LLM 分类器**，只有前两级的最高分低于阈值时才调用，输出 JSON 决策。这样做的原因是成本和延迟优化——80% 的简单问题在前两级就能确定路由，只有模糊问题才需要 LLM。如果直接让每个问题都走 LLM，会增加 1-2 秒延迟和额外的 Token 消耗。

**Q: 终止条件是如何设计的？为什么要组合多个条件？**

> A: 我使用 `TextMentionTermination | MaxMessageTermination` 的组合。文本终止是主条件，要求 Agent 输出特定短语（如"ANALYSIS COMPLETE"）表示完成；最大消息数是兜底保护，防止异常情况下无限循环。组合使用是为了**可靠性**——如果只依赖文本终止，Agent 可能因 prompt 理解偏差而不输出关键词，导致挂起；如果只依赖最大消息数，可能在分析不完整时就强制终止。两者结合，既保证正常流程快速结束，又有兜底保护。

---

### 📌 记忆与上下文

**Q: RAG 和普通的上下文窗口有什么区别？**

> A: 核心区别在于**选择性检索**。普通上下文窗口是把最近 N 条消息直接塞进 prompt，适合连续的短对话，但存在两个问题：一是当历史很长时，上下文窗口可能溢出（LLM 有 token 限制）；二是很多历史消息与当前问题无关，会干扰回答质量。RAG（检索增强生成）则通过语义相似度，从大量历史中选择与当前问题最相关的片段注入 prompt。在我的项目中，实现了**三层上下文**：对话摘要（全局信息，压缩到几百字）、最近消息（短期记忆，最近 6 条）、语义检索（RAG，top-5 相关片段）。这样既保证了关键信息不丢失，又避免了无关信息干扰。

**Q: 对话摘要是什么时候生成的？如何更新？**

> A: 对话摘要在每轮分析完成后异步更新。流程是：Agent 完成回答 → 保存消息到数据库 → 调用 `update_conversation_summary()` → 读取最近 10 条消息 → 启发式摘要（取最长的 3 条消息内容拼接）→ 更新 conversations.summary 字段。之所以用启发式而非 LLM 生成摘要，是为了节省成本和延迟。当前方案足够表达对话主题，如果未来对话变长，可以考虑用 LLM 生成更智能的摘要。

---

### 📌 调试与优化

**Q: 如何调试 Agent 的行为？**

> A: 我主要从三个层面调试。第一，**日志记录**，在关键节点（路由决策、Agent 调用、工具执行）记录 INFO 级别日志，包括输入参数和输出结果。第二，**消息追踪**，AutoGen 的 `TaskResult.messages` 包含完整的对话历史，可以在调试时打印出来查看 Agent 的思考过程。第三，**结构化输出**，要求 Agent 输出格式化的 Markdown，并包含终止标记，便于检查结果完整性。对于复杂问题，我会单独运行单个 Agent，传入简化后的 task，观察其行为，定位是 prompt 问题、工具问题还是模型能力问题。

**Q: Agent 输出不稳定怎么办？**

> A: 不稳定体现在两方面：格式和字数。解决格式不稳定，我在 system prompt 中明确指定了输出模板（Markdown 结构、必须包含的章节），并用终止标记强制约束流程。解决字数不稳定，我在 prompt 中明确要求"at least 300 words"，如果仍然过短，理论上可以增加后处理检查（字数不达标则触发重试并追加"请详细阐述"提示），但当前版本的 LLM（Kimi K2.5）对字数指令遵循较好，没有启用重试。另外，temperature 设置也会影响稳定性，我将 temperature 设为 1（默认），在创造性和一致性之间平衡。

**Q: 如何评估 Agent 的效果？**

> A: 评估分为**自动评估**和**人工评估**。自动评估包括：终止成功率（是否输出了终止标记）、工具调用成功率（是否成功获取数据）、响应格式合规性（是否包含要求的章节）。人工评估主要看：分析深度（是否有实质见解而非泛泛而谈）、数据准确性（关键财务指标是否正确）、投资建议合理性（是否基于分析得出结论）。目前主要靠人工抽查，未来可以考虑引入 LLM-as-Judge，用另一个 LLM 按评分标准自动评估。

---

### 📌 生产部署

**Q: Agent 系统的性能瓶颈在哪里？如何优化？**

> A: 瓶颈主要在**LLM 调用延迟**。一次完整分析需要多次 LLM 调用：Research Analyst 可能有 2-3 次（思考+工具结果分析），Financial Analyst 类似，Investment Advisor 1 次合成。每次调用 10-30 秒，串行执行会很慢。我的优化策略是：第一，**并行化**，Research 和 Financial 同时执行，节省约 50% 时间；第二，**选择性路由**，追问时根据问题类型选择最小 Agent 集合，避免不必要的分析；第三，**缓存**，股票基本信息可以短时缓存（如 5 分钟），避免重复调用。未来可以考虑模型层面的优化，如使用更快的模型处理简单任务，或用流式输出提前展示部分结果。

**Q: 如何保证 Agent 在生产环境的稳定性？**

> A: 多层防护：超时控制（每层调用设置超时，避免挂起）、降级策略（数据获取失败时使用缓存或返回友好错误）、资源限制（MaxMessageTermination 限制最大轮次）、异常隔离（单个 Agent 失败不影响其他 Agent）、日志监控（记录所有关键路径便于排查）。数据库连接使用连接池，避免连接泄漏。API 层有限流，防止过度调用导致成本失控。



---

## 七、扩展面试专题 ⭐新增

### 📌 RAG与意图识别

**Q: 项目中RAG意图识别是如何实现的？如何处理垂类意图？**

> A: 我实现了一个五级路由管线来解决意图识别问题：
>
> **架构设计**：
> 1. **Embedding粗筛**：快速计算与5类意图例句的相似度（<10ms）
> 2. **规则引擎**：硬规则直接匹配（如"重新分析"→full），软规则关键词打分
> 3. **RAG意图召回**：从42条人工构造的意图案例库中向量检索相似案例
> 4. **Few-shot LLM**：动态few-shot,基于召回的案例构建Few-shot Prompt进行意图分类
> 5. **Fallback**：以上都失败时调用原始LLM分类器
>
> **意图知识库覆盖**：
> - 财务指标类（8条）：PE、ROE、现金流、毛利率等
> - 财务风险类（6条）：现金流风险、应收账款、存货、减持等
> - 研究分析类（8条）：新闻催化剂、竞争分析、宏观影响、护城河等
> - 投资建议类（8条）：择时、仓位管理、止损、目标价等
> - 模糊/歧义类（5条）：意图不明确、多因素权衡、跨会话对比等
> - 非股票相关（7条）：天气、计算、加密货币、券商推荐等
>
> **长尾问题处理**：通过向量相似度匹配，即使用户表述与案例不完全一致，也能召回相似意图。

**Q: 用户表述模糊时如何引导？**

> A: 在Few-shot LLM阶段，模型会判断`needs_clarification`字段。如果意图不明确（如"这个怎么样"），系统会：
> 1. 设置`needs_clarification: true`
> 2. 生成一个具体的澄清问题（如"您想了解财务数据、最新新闻，还是投资建议？"）
> 3. 前端展示澄清问题，用户选择后再次路由

---

### 📌 记忆系统

**Q: 项目中Agent的记忆是如何设计的？短期记忆和长期记忆如何区分？**

> A: 我设计了一个**五层记忆体系**：
>
> **短期记忆（滑动窗口）**：
> - 保留最近8轮对话的原始消息
> - 用于即时上下文理解
>
> **中期记忆（压缩摘要）**：
> - 每8轮触发一次LLM摘要生成
> - 将历史消息压缩为200-400字的关键信息摘要
> - 存储在`conversation_summaries`表，支持向量检索
>
> **长期记忆（元认知）**：
> - 每10轮触发一次自省(reflection)
> - 生成三类元记忆：
>   - `user_preference`：用户偏好（详细vs简洁、关注维度）
>   - `self_correction`：自我修正（之前犯的错误）
>   - `interaction_pattern`：互动模式（追问频率、质疑倾向）
> - 存储在`meta_memories`表，置信度≥0.6才会被使用
>
> **语义记忆（RAG）**：
> - 所有消息分块、embedding后存入`memory_chunks`
> - 根据当前问题向量检索相关历史片段
>
> **工具溯源记忆**：
> - 所有工具调用记录存入`tool_call_logs`
> - 用于幻觉核查和数据溯源

**Q: 如何应对上下文溢出问题？**

> A: 采用**分层压缩策略**：
> 1. **滑动窗口**：只保留最近8轮原始消息，旧消息自动进入压缩队列
> 2. **LLM摘要**：超过8轮的历史由LLM生成结构化摘要，提取关键信息
> 3. **分层注入**：构建上下文时按优先级注入：元记忆 → 摘要 → 近期消息 → 语义检索结果
> 4. **Token控制**：每层都有长度限制，确保总上下文不超过LLM窗口
       
       layer0 元记忆，top-k筛选（置信值>0.6）
       layer1 压缩摘要，并进行向量检索top-2
       layer2 滑动窗口得到近期8轮对话
       layer3 RAG语义检索，top-5相关片段
       layer4 工具调用日志
---

### 📌 RAG实现细节

**Q: 详细介绍一下RAG流程，如何切分、索引、检查相似度？如何应对RAG延迟？**

> A: **RAG流程**：
>
> 1. **切分策略**：
>    - 按消息粒度切分（不跨消息切分，保持语义完整）
>    - 每条消息生成一个chunk，保留元数据（sender, turn, event_type）
>
> 2. **索引构建**：
>    - 使用`sentence-transformers`（all-MiniLM-L6-v2）生成384维向量
>    - 存入`memory_chunks`表的`embedding vector(384)`列
>    - 创建pgvector ivfflat索引加速检索（lists=20）
>
> 3. **相似度检查**：
>    - 余弦相似度：`embedding <=> query_vector`
>    - 阈值过滤：默认threshold=0.5，低于此值丢弃
>    - 去重策略：同一意图子类别只保留最高相似度的一个
>
> 4. **延迟优化**：
>    - **内存模式**：意图知识库预加载到内存，检索<10ms
>    - **批量编码**：多条消息批量生成embedding，减少模型加载开销
>    - **异步处理**：RAG检索与规则引擎并行执行
>    - **缓存机制**：热门查询结果短时缓存

---

### 📌 AI幻觉应对

**Q: 项目中如何应对AI幻觉问题？**

> A: **多层防护机制**：
>
> 1. **工具溯源**：所有工具调用记录存入`tool_call_logs`，包含：
>    - 工具名称、参数、返回结果摘要
>    - 数据来源标记（yfinance/Polygon/Tavily等）
>    - 调用耗时和状态
>
> 2. **上下文溯源**：在五层上下文中标注【数据来源】：
>    - 【历史摘要 | 轮次X-Y】
>    - 【数据来源：近期对话（最近N轮）】
>    - 【数据来源：历史记忆 | 类型：X】
>
> 3. **数据一致性校验**：财务指标类回答要求Agent注明数据来源
>
> 4. **元认知修正**：通过`self_correction`元记忆记录之前的错误，避免重复犯错

---

### 📌 Agent Loop详解

**Q: 详细介绍一下项目的Agent Loop设计？**

> A: **初始分析流程** (`parallel_analysis.py`):
> ```
> Phase 1: Research + Financial 并行执行
>   • asyncio.gather() 同时运行两个Analyst
>   • return_exceptions=True 保证容错（单失败不影响整体）
>
> Phase 2: Investment Advisor 综合报告
>   • 接收两份分析结果
>   • 生成最终投资建议
> ```
>
> **追问流程** (`group_chat.py`):
> ```
> 1. 构建五层上下文（元记忆 → 摘要 → 近期消息 → RAG → 工具日志）
> 2. 路由决策 (embedding → rules → RAG → Few-shot LLM → fallback)
> 3. 根据路由选择执行模式:
>    • advisor_only: RoundRobinGroupChat 单Agent回答
>    • research/financial: 对应Agent获取新数据
>    • full: 重新执行完整三智能体分析
>    • unknown: 拒绝并引导回股票场景
> 4. 触发记忆压缩（满足条件时）
> 5. 触发元认知自省（每10轮）
> ```

---

### 📌 Function Calling原理

**Q: 介绍一下该项目Function Call原理，模型生成的JSON如何通过逻辑触发表层代码执行并返回给模型？**

> A: 基于**AutoGen框架**实现：
>
> 1. **工具注册**：定义Python函数，添加类型注解和docstring，注册到Agent的`tools`参数
> 2. **Schema生成**：AutoGen自动解析函数签名生成JSON Schema
> 3. **LLM决策**：LLM接收system_prompt + task，判断是否需要工具调用
> 4. **输出解析**：LLM输出结构化函数调用请求（函数名+参数）
> 5. **本地执行**：AutoGen解析JSON，匹配注册的工具函数，执行Python代码获取返回值
> 6. **结果回注**：工具结果以`ToolMessage`格式重新注入对话历史
> 7. **最终生成**：LLM基于工具结果生成自然语言回复

---

### 📌 vLLM与推理优化

**Q: vLLM的PagedAttention原理是什么？在该项目有用的必要吗？**

> A: **PagedAttention原理**：
> - 将KV Cache分页管理，解决传统方式显存碎片化问题
> - 动态分配物理块，支持高效的内存共享（如beam search）
> - 允许更大的batch size和更长的序列
>
> **项目适用性**：
> - **当前不需要**：项目使用Moonshot API（Kimi K2.5），非本地部署
> - **适用场景**：如果使用本地vLLM部署（如Llama、Qwen），PagedAttention可显著提升吞吐
> - **替代方案**：项目通过并行分析和选择性路由优化延迟，而非推理层优化

---

### 📌 FastAPI架构设计

**Q: 在使用FastAPI开发大模型接口时，中间件和依赖注入分别适合处理什么样的业务逻辑？**

> A: **中间件（Middleware）**：适用于**横切关注点**（所有请求都需要）
> - **认证**：API Key验证
> - **审计日志**：记录所有请求和响应
> - **限流**：SlowAPI基于IP的速率限制
> - **跨域**：CORS处理
>
> **依赖注入（Dependency Injection）**：适用于**路由特定的资源**
> - **数据库会话**：ConversationStore连接池
> - **用户上下文**：从请求中提取的用户信息
> - **配置注入**：Settings配置对象
> - **服务实例**：EmbeddingService等单例服务
>
> **设计原则**：中间件处理通用逻辑，依赖注入处理业务资源，保持关注点分离。


对于memory_reflection.py
1.confidence采取时间衰减 / 新近优先

用 created_at 或 turn_range 的上界：越靠近当前 turn 越优先；或对 confidence 乘一个 recency 权重。
或 先取最近 N 条，再在里面按 confidence 排序取 5。

2.prompt应该更接近工业化
工业级标准实现
✅ 已实现的 6 大标准
精确角色定义

专业背景、行为风格、约束边界
例如："15+年投行经验、CFA持证人、保守风格"
输入规范与防御

输入类型定义、验证规则、拒绝条件
防止注入和越界查询
输出格式约束

Markdown表格强制结构
JSON Schema定义
字段长度限制
Few-shot示例

标准案例、边界案例、错误处理
每个Prompt包含3-6个完整示例
质量检查清单

6-10项自检项
强制修正机制
完成标准验证
错误处理

工具失败策略
数据缺失处理
降级方案


storage 表
表	             用途
conversations	会话：id, ticker, title, status, summary（rolling digest）, 时间戳；ALTER 增加 last_compressed_turn, last_reflection_turn。
messages	消息：turn, sender, content, event_type, 可选 embedding vector(dim)。
memory_chunks	每条消息对应的检索块：chunk_type, content, embedding, importance, turn；部分唯一索引 (conversation_id, message_id, chunk_type)（message_id 非空时）防重复 ingest。
tool_call_logs	工具名、参数 JSON、完整结果、摘要、数据源、耗时、成功/错误。
conversation_summaries	压缩管线的 LLM 摘要：summary_type, turn_range, message_count, embedding。
meta_memories	反思产出的元记忆：memory_type, content, evidence, confidence, turn_range, embedding 等。

向量索引：memory_chunks、messages、conversation_summaries、meta_memories 上对 embedding 建 ivfflat + vector_cosine_ops（lists 参数各不同）；查询里用 <=> 排序。


什么是元记忆反思：在有限上下文窗口，智能体能够在长期对话中进行深度学习，提取核心特征并保留关键信息，实现个性化服务和长期记忆。（帮助AI理解用户特征，喜欢什么，以及之前是否自己做错了什么）  三个维度：用户维度（个性化用户画像），自我修复（自动化修复错误），互动模式（分析交互动态，如调整话术）。置信度区分：强证据：明确陈述+重复3次以上，中证据：两次提及，弱证据：单次模糊信号。
错误处理：数据不足，矛盾证据->记录为情境依赖，意图不明：无明显偏好

会话摘要： 必须包含元数据（股票代码，论数，时间跨度），关注维度，关键问答，关键数据（PE，营收），决策结论，数据缺口（标明不确定和数据缺失的地方）。压缩策略：股票代码、具体数值、投资建议、用户偏好绝不压缩，分析方法、行业背景、风险类别概括，删除客套话和冗余。

ReAct：在首轮问答，采用类似workflow的智能体，使研究分析师这财务分析师两个智能体并行运行，提高效率，后将结果返回给报告撰写。
在追问部分，如果意图判断为“unknown":返回固定回答，”advisor_only“：只有对话的上下文。其他采取ReAct架构，先有ReAct分析师工作，然后为投资建议撰写，使用AutoGen的AssistantAgent做模型+工具的多轮循环，reflect_on_tool_use=True（开反思），循环：推理（分析用户需求，判断需要什么信息）->行动（自主调用工具）-> 观察（接受工具返回的数据，信息不足则继续调用），最多5轮循环

可以做微调的部分： 意图识别，用线上日志
记忆压缩：历史对话+人工摘要


CHATGPT:基于Transformer 仅解码器架构的自回归生成式大语言模型，通过1.海量无监督预训练学习语言规律，从互联网海量文本（让模型学习语言的语法、语义、事实知识和逻辑关系），2.监督学习（SFT，人工撰写的对话数据），再经3.RLHF（人类反馈强化学习）三阶段对齐训练提升对话质量与安全性，即建立奖励模型训练（RM,对用一问题生成多条回答，人类标注员打分，建立人类偏好的数学表达）和强化学习微调（RL，PPO算法，根据打分主动优化，生成RM打分更高的回复，更符合人类偏好）最终以逐词预测方式生成符合人类意图的自然语言回复。

强化学习