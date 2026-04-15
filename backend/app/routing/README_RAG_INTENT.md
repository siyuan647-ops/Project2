# RAG意图识别增强系统

基于RAG（检索增强生成）的意图识别增强模块，通过预构建的意图知识库提升金融投资场景下的意图识别准确性。

## 核心组件

```
routing/
├── intent_knowledge_base.py      # 意图知识库（30-50条人工构造案例）
├── rag_intent_retriever.py       # RAG意图召回层
├── intent_prompt_builder.py      # Few-shot Prompt构建器
├── enhanced_router.py            # 增强版路由管线
├── router.py                     # 原路由（保留作为fallback）
├── embeddings.py                 # Embedding服务（复用现有）
├── rules.py                      # 规则引擎（复用现有）
└── types.py                      # 类型定义（扩展）
```

## 管线流程

```
用户Query
    │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 1: Embedding 粗筛（复用现有）                     │
│  └─ 计算与5类基础意图的相似度                            │
└──────────────────────┬──────────────────────────────────┘
                       │
    ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 2: 规则引擎（复用现有）                           │
│  ├─ 硬规则：直接匹配特定模式（如"重新分析"）              │
│  └─ 软规则：关键词匹配加分                               │
└──────────────────────┬──────────────────────────────────┘
                       │ 规则未命中或置信度低
    ▼
┌─────────────────────────────────────────────────────────┐
│  Stage 3: RAG意图召回（新增）                            │
│  ├─ 向量化用户Query                                     │
│  ├─ 从知识库召回top-k相似案例                            │
│  └─ 检查是否达到高置信度阈值（>0.75）                     │
└──────────────────────┬──────────────────────────────────┘
                       │
    ┌──────────────────┴──────────────────┐
    ▼                                       ▼
高置信度(>0.75)                      需要LLM判断
    │                                       │
    ▼                                       ▼
直接返回RAG路由                     Few-shot LLM分类
（快速路径）                        （精准路径）
```

## 意图知识库

### 覆盖的意图类别

| 类别 | 子类别数 | 说明 |
|------|----------|------|
| financial_metrics | 8 | PE、ROE、EPS、现金流、毛利率等 |
| financial_risk | 6 | 现金流风险、应收账款、存货、减持等 |
| research | 8 | 新闻、竞争分析、宏观影响、护城河等 |
| advisor | 8 | 择时、仓位、止损、目标价、风险评估等 |
| ambiguous | 5 | 模糊查询、多因素权衡、跨会话对比等 |
| off_topic | 7 | 天气、计算、加密货币、券商推荐等 |

**总计: 42条精心构造的案例**

### 案例结构

```python
{
    "query": "AAPL的市盈率是多少，和同行业比怎么样？",
    "intent_category": "financial_metrics",
    "intent_subcategory": "pe_analysis",
    "route": "financial",
    "extracted_entities": {"metric": "PE", "ticker": "AAPL", "comparison": "industry"},
    "handling_strategy": "调用财务数据工具获取PE并进行同业对比",
    "difficulty": "standard",
    "common_variations": ["PE多少", "市盈率", "估值贵不贵"]
}
```

## 使用方法

### 1. 基本使用（已集成）

```python
from app.routing import route_followup

# 使用增强版路由（自动使用RAG+Few-shot）
decision = await route_followup(
    ticker="AAPL",
    question="PE是多少？",
    history_summary=""
)

print(decision.route)        # "financial"
print(decision.source)       # "rag_few_shot_llm" 或 "rag_direct"
print(decision.confidence)   # 0.85
print(decision.metadata)     # 包含召回案例、实体等
```

### 2. 使用原始路由（对比测试）

```python
from app.routing import original_route_followup

# 使用原版三级管线（embedding → rules → LLM）
decision = await original_route_followup(
    ticker="AAPL",
    question="PE是多少？",
    history_summary=""
)
```

### 3. 直接使用RAG召回

```python
from app.routing.rag_intent_retriever import get_rag_retriever

retriever = get_rag_retriever()
cases = await retriever.retrieve_similar_intents(
    query="PE是多少？",
    top_k=5,
    similarity_threshold=0.5,
    diversify=True  # 同一意图类别只保留最高相似度
)

for case in cases:
    print(f"{case.query} -> {case.route} (相似度: {case.similarity:.3f})")
```

### 4. 使用增强路由的可配置选项

```python
from app.routing.enhanced_router import enhanced_route_followup

decision = await enhanced_route_followup(
    ticker="AAPL",
    question="PE是多少？",
    history_summary="",
    enable_rag=True,        # 是否启用RAG召回
    enable_few_shot=True,   # 是否启用Few-shot LLM（需要LLM调用）
)
```

## 决策Source类型

| Source | 说明 | 延迟 |
|--------|------|------|
| hard_rule | 硬规则直接匹配 | ~1ms |
| soft_rule | 软规则高置信度 | ~1ms |
| rag_direct | RAG高置信度直接返回 | ~10ms |
| rag_few_shot_llm | RAG+Few-shot LLM分类 | ~1-2s |
| llm_fallback | 原LLM分类（RAG失败时） | ~1-2s |
| fallback | Embedding fallback | ~10ms |

## 测试

```bash
cd backend
python test_rag_intent.py
```

测试内容包括：
1. RAG意图召回效果
2. 意图知识库覆盖情况
3. 增强版 vs 原版的分类准确性对比

## 扩展知识库

当遇到新的意图类型或误分类case时，编辑 `intent_knowledge_base.py`：

```python
INTENT_KNOWLEDGE_CASES.append({
    "query": "新的查询示例",
    "intent_category": "新类别",
    "intent_subcategory": "新子类别",
    "route": "对应的",
    "handling_strategy": "处理策略",
    "difficulty": "standard",
    "common_variations": ["变体1", "变体2"]
})
```

重启服务后，新的案例会自动加载到内存索引中。

## 性能优化

1. **内存模式**: 默认使用内存模式，无需数据库查询，延迟~10ms
2. **懒加载**: Embedding模型首次使用时加载
3. **去重**: `diversify=True` 避免召回同一意图的多个案例
4. **快速路径**: 高置信度匹配(>0.75)直接返回，跳过LLM调用

## 预期收益

| 场景 | 原方案 | RAG增强方案 |
|------|--------|-------------|
| "PE是多少" | ✅ 规则命中 | ✅ 规则命中（不变） |
| "这个怎么样" | ⚠️ LLM判断 | ✅ RAG匹配ambiguous，主动澄清 |
| "亏了20%怎么办" | ⚠️ 可能错误 | ✅ RAG匹配position_management |
| "和之前那只比" | ❌ 难以理解 | ✅ RAG匹配cross_session，触发记忆 |
| "股息率怎么样" | ⚠️ 可能错误 | ✅ RAG匹配dividend_analysis |
