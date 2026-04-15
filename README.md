# 🤖 多智能体金融决策平台（Multi-Agent Financial Decision Platform）

基于 **AutoGen + Kimi K2.5 + Vue 3** 构建的全栈 AI 金融分析系统，集成多智能体协同投资分析与机器学习信用风险评估两大核心功能。

---

## ✨ 核心功能

### 1. 多智能体投资顾问

输入任意上市公司股票代码，三大 AI 智能体自动协同完成深度投资分析：

| 智能体 | 职责 | 工具 |
|--------|------|------|
| 🔍 研究分析师 | 搜集新闻、行业趋势、竞争格局 | yfinance、DuckDuckGo |
| 📊 财务分析师 | 财务报表分析、估值评估、价格趋势 | yfinance 财务数据 |
| 💼 投资顾问 | 综合研判，输出投资评级与策略 | 无（纯推理） |

- **实时 SSE 流式输出**：用户即时看到每位智能体的工作过程
- **多轮对话**：支持追问，系统自动路由到合适的智能体组合
- **混合意图路由**：Embedding 粗筛 → 规则引擎 → LLM 分类器，三级路由管线
- **RAG 记忆系统**：对话摘要 + 最近消息窗口 + pgvector 语义检索，三层上下文构建

### 2. AI 信用风险预测

上传贷款申请人 Excel/CSV 文件，基于 XGBoost 模型批量预测信用等级（P1-P4）：

- P1（信用最好）→ P4（信用最差）
- 自动特征工程（DTI 债务收入比、LTI 贷款收入比）
- 数据质量自动修正与告警
- 结果直接下载为 Excel 文件

---

## 🏗️ 技术架构

```
┌─────────────┐     Nginx 反向代理      ┌────────────────────┐
│  Vue 3 SPA  │ ◄──────────────────────► │  FastAPI Backend   │
│  + Element  │      /api/ Proxy + SSE   │                    │
│    Plus     │                          │  ┌──────────────┐  │
└─────────────┘                          │  │ AutoGen 0.4  │  │
                                         │  │ Multi-Agent  │  │
                                         │  └──────┬───────┘  │
                                         │         │          │
                                         │  ┌──────▼───────┐  │
                                         │  │ Hybrid Router│  │
                                         │  │ Emb→Rule→LLM │  │
                                         │  └──────┬───────┘  │
                                         │         │          │
                                         │  ┌──────▼───────┐  │
                                         │  │  PostgreSQL   │  │
                                         │  │  + pgvector   │  │
                                         │  └──────────────┘  │
                                         └────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | Vue 3、Vite 6、Element Plus、Vue Router 4、Axios、Marked.js |
| **后端** | Python 3.11、FastAPI、Uvicorn、Pydantic Settings |
| **智能体** | AutoGen 0.4+ (SelectorGroupChat)、Kimi K2.5 (OpenAI 兼容 API) |
| **路由** | sentence-transformers (all-MiniLM-L6-v2)、正则规则引擎、LLM 分类器 |
| **数据库** | PostgreSQL 16 + pgvector (向量相似度检索) |
| **ML** | XGBoost、scikit-learn、Pandas、NumPy |
| **数据源** | yfinance（财务数据）、DuckDuckGo Search（新闻搜索） |
| **部署** | Docker Compose（PostgreSQL + Backend + Frontend/Nginx） |
| **安全** | API Key 认证、SlowAPI 限流、Prompt 注入防护、审计日志 |

---

## 🚀 快速启动

### Docker Compose（推荐）

```bash
# 1. 克隆项目
git clone <repo-url> && cd project2

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 .env，填入 KIMI_API_KEY

# 3. 一键启动
docker compose up --build -d

# 4. 访问
# 前端：http://localhost
# 后端 API：http://localhost:8000/docs
```

### 本地开发

```bash
# 后端
cd backend
python -m venv .venv && .venv/Scripts/activate  # Windows
pip install -r requirements.txt
python -m app.ml.generate_data && python -m app.ml.train_model
uvicorn app.main:app --reload

# 前端
cd frontend
npm install && npm run dev
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `KIMI_API_KEY` | Kimi K2.5 API 密钥 | 必填 |
| `KIMI_BASE_URL` | OpenAI 兼容端点 | `https://api.moonshot.cn/v1` |
| `DATABASE_URL` | PostgreSQL 连接字符串 | `postgresql://finapp:finapp_secret@localhost:5432/financial_platform` |
| `API_KEY` | API 访问密钥（空=跳过认证） | 空 |

---

## 📁 项目结构

```
project2/
├── docker-compose.yml          # 三服务编排
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             # FastAPI 入口 + 中间件
│       ├── config.py           # 全局配置
│       ├── storage.py          # PostgreSQL + pgvector 存储层
│       ├── memory_ingest.py    # RAG 写入管线
│       ├── agents/             # AutoGen 多智能体
│       │   ├── group_chat.py   # 编排中心
│       │   ├── investment_advisor.py
│       │   ├── research_analyst.py
│       │   └── financial_analyst.py
│       ├── routing/            # 混合意图路由
│       │   ├── router.py       # 三级管线
│       │   ├── embeddings.py   # 向量粗筛
│       │   ├── rules.py        # 规则引擎
│       │   └── types.py        # 路由类型定义
│       ├── routers/            # API 端点
│       │   ├── advisor.py
│       │   └── credit.py
│       ├── middleware/          # 安全中间件
│       │   └── audit.py
│       ├── schemas/models.py   # Pydantic 模型
│       ├── tools/              # 外部数据工具
│       │   ├── stock_data.py
│       │   └── news_search.py
│       └── ml/                 # 信用风险 ML
│           ├── generate_data.py
│           ├── train_model.py
│           └── predict.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    └── src/
        ├── App.vue
        ├── main.js
        ├── api/index.js
        ├── router/index.js
        └── views/
            ├── HomePage.vue
            ├── AdvisorView.vue
            └── CreditView.vue
```

---

## 📄 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/advisor/conversations` | 创建会话 |
| GET | `/api/advisor/conversations` | 列出会话 |
| GET | `/api/advisor/conversations/{id}` | 获取会话详情 |
| POST | `/api/advisor/conversations/{id}/initial` | 启动初始分析 (SSE) |
| POST | `/api/advisor/conversations/{id}/messages` | 追问 (SSE) |
| POST | `/api/advisor/analyze` | 一次性分析（兼容旧接口） |
| POST | `/api/credit/predict` | 批量信用预测 |
| GET | `/api/credit/download/{filename}` | 下载预测结果 |
| GET | `/api/credit/template` | 下载上传模板 |
| GET | `/api/health` | 健康检查 |
| GET | `/api/admin/audit-stats` | 审计统计 |
| POST | `/api/admin/backfill-memory` | 历史记忆回填 |

---

## ⚠️ 免责声明

本平台分析结果由 AI 生成，仅供学习和参考，不构成任何投资建议。投资有风险，决策需谨慎。信用评估结果不应作为唯一放贷依据。
