"""金融决策平台意图知识库 - 用于RAG召回的垂类意图案例

包含30-50条人工构造的query和意图映射关系，覆盖金融投资场景的核心意图类型。
每条案例包含：
- query: 用户查询示例
- intent_category/subcategory: 意图分类（细粒度）
- route: 对应的路由决策
- extracted_entities: 需要提取的关键实体
- handling_strategy: 处理策略（给LLM的提示）
- difficulty: 难度级别（standard/complex/ambiguous）
- common_variations: 常见变体表述
"""

from typing import List, Dict, Any


INTENT_KNOWLEDGE_CASES: List[Dict[str, Any]] = [
    # ========== 财务指标类（financial_metrics）- 8条 ==========
    {
        "query": "AAPL的市盈率是多少，和同行业比怎么样？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "pe_analysis",
        "route": "financial",
        "extracted_entities": {"metric": "PE", "ticker": "AAPL", "comparison": "industry"},
        "handling_strategy": "调用财务数据工具获取PE并进行同业对比",
        "difficulty": "standard",
        "common_variations": ["PE多少", "市盈率", "估值贵不贵", "PE ratio", "price to earnings"]
    },
    {
        "query": "这家公司的ROE为什么比去年下降了？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "roe_analysis",
        "route": "financial",
        "extracted_entities": {"metric": "ROE", "trend": "declining", "period": "YoY"},
        "handling_strategy": "获取ROE历史数据，拆解杜邦分析三因素",
        "difficulty": "complex",
        "common_variations": ["净资产收益率", "ROE下降", "股东回报率"]
    },
    {
        "query": "自由现金流和经营现金流有什么区别？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "cashflow_education",
        "route": "advisor_only",
        "extracted_entities": {"topic": "cashflow_types", "intent": "explanation"},
        "handling_strategy": "解释财务概念，可结合具体公司数据说明",
        "difficulty": "standard",
        "common_variations": ["FCF和OCF区别", "现金流类型", "自由现金怎么算"]
    },
    {
        "query": "毛利率连续下滑意味着什么？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "margin_trend",
        "route": "financial",
        "extracted_entities": {"metric": "gross_margin", "trend": "declining", "period": "continuous"},
        "handling_strategy": "分析毛利率趋势，结合行业竞争格局判断",
        "difficulty": "complex",
        "common_variations": ["毛利下降", " profitability下滑", "利润率趋势"]
    },
    {
        "query": "每股收益EPS和 diluted EPS 有什么区别？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "eps_analysis",
        "route": "advisor_only",
        "extracted_entities": {"metric": "EPS", "intent": "explanation"},
        "handling_strategy": "解释基本EPS和稀释EPS的区别",
        "difficulty": "standard",
        "common_variations": ["EPS是什么", "earnings per share", "稀释每股收益"]
    },
    {
        "query": "负债率多少算健康？这家公司的资产负债率如何？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "leverage_analysis",
        "route": "financial",
        "extracted_entities": {"metric": "debt_ratio", "intent": "evaluation"},
        "handling_strategy": "解释负债率健康标准，分析具体公司数据",
        "difficulty": "standard",
        "common_variations": ["资产负债率", "debt to equity", "负债水平", "杠杆率"]
    },
    {
        "query": "股息率怎么计算？这家公司分红怎么样？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "dividend_analysis",
        "route": "financial",
        "extracted_entities": {"metric": "dividend_yield", "intent": "evaluation"},
        "handling_strategy": "获取股息历史，分析分红政策和收益率",
        "difficulty": "standard",
        "common_variations": ["分红率", "dividend yield", "派息", "股息回报"]
    },
    {
        "query": "EBITDA和净利润的区别是什么？",
        "intent_category": "financial_metrics",
        "intent_subcategory": "profitability_education",
        "route": "advisor_only",
        "extracted_entities": {"topic": "profitability_metrics", "intent": "explanation"},
        "handling_strategy": "解释EBITDA与净利润的区别及应用场景",
        "difficulty": "standard",
        "common_variations": ["息税折旧前利润", "operating profit", "营业利润"]
    },

    # ========== 财务风险类（financial_risk）- 6条 ==========
    {
        "query": "这家公司现金流一直为负，是不是要破产了？",
        "intent_category": "financial_risk",
        "intent_subcategory": "cashflow_risk",
        "route": "financial",
        "extracted_entities": {"concern": "negative_cashflow", "risk_type": "solvency"},
        "handling_strategy": "分析现金流结构，评估短期偿债能力和持续性",
        "difficulty": "complex",
        "common_variations": ["现金流不好", "一直亏钱", "资金链断裂", "burn rate太高"]
    },
    {
        "query": "应收账款增长比营收还快，有风险吗？",
        "intent_category": "financial_risk",
        "intent_subcategory": "receivable_risk",
        "route": "financial",
        "extracted_entities": {"red_flag": "receivables_growth", "comparison": "revenue"},
        "handling_strategy": "分析应收账款周转率，评估收入质量和回款风险",
        "difficulty": "complex",
        "common_variations": ["AR增长快", "应收账款高企", "收入质量差"]
    },
    {
        "query": "存货周转天数增加说明什么？",
        "intent_category": "financial_risk",
        "intent_subcategory": "inventory_risk",
        "route": "financial",
        "extracted_entities": {"metric": "inventory_days", "trend": "increasing"},
        "handling_strategy": "分析存货周转变化，评估滞销风险和减值可能",
        "difficulty": "complex",
        "common_variations": ["库存积压", "inventory turnover", "存货高企"]
    },
    {
        "query": "大股东在减持，是不是内部人都不看好了？",
        "intent_category": "financial_risk",
        "intent_subcategory": "insider_selling",
        "route": "research",
        "extracted_entities": {"signal": "insider_selling", "concern": "confidence"},
        "handling_strategy": "搜索大股东减持新闻，分析减持原因和市场影响",
        "difficulty": "complex",
        "common_variations": ["高管减持", "内部人交易", "大股东套现", "insider trading"]
    },
    {
        "query": "审计报告里有保留意见，严重吗？",
        "intent_category": "financial_risk",
        "intent_subcategory": "audit_risk",
        "route": "financial",
        "extracted_entities": {"red_flag": "qualified_opinion", "source": "audit_report"},
        "handling_strategy": "解释审计意见类型，评估保留意见的实质影响",
        "difficulty": "complex",
        "common_variations": ["审计非标", "无法表示意见", "audit qualification"]
    },
    {
        "query": "有息负债太多了怎么办？",
        "intent_category": "financial_risk",
        "intent_subcategory": "debt_risk",
        "route": "financial",
        "extracted_entities": {"concern": "high_interest_debt", "risk_type": "liquidity"},
        "handling_strategy": "分析债务结构、期限分布和偿债能力",
        "difficulty": "standard",
        "common_variations": ["负债过高", "债务压力大", "interest burden"]
    },

    # ========== 研究分析类（research）- 8条 ==========
    {
        "query": "最近有什么影响股价的重大新闻？",
        "intent_category": "research",
        "intent_subcategory": "news_catalyst",
        "route": "research",
        "extracted_entities": {"news_type": "catalyst", "impact": "price"},
        "handling_strategy": "搜索近期重大新闻并评估对股价影响",
        "difficulty": "standard",
        "common_variations": ["有什么利好利空", "最近消息", "新闻面", "有什么事件"]
    },
    {
        "query": "苹果和特斯拉在AI领域的布局有什么不同？",
        "intent_category": "research",
        "intent_subcategory": "competitive_analysis",
        "route": "research",
        "extracted_entities": {"competitors": ["AAPL", "TSLA"], "topic": "AI_strategy"},
        "handling_strategy": "分别获取两家公司AI战略信息并对比分析",
        "difficulty": "complex",
        "common_variations": ["和竞争对手比", "行业对比", "差异化", "vs", "compared to"]
    },
    {
        "query": "美联储降息对这只股票有什么影响？",
        "intent_category": "research",
        "intent_subcategory": "macro_impact",
        "route": "research",
        "extracted_entities": {"macro_factor": "fed_rate", "impact_type": "indirect"},
        "handling_strategy": "分析宏观政策对行业及个股的影响路径",
        "difficulty": "complex",
        "common_variations": ["加息影响", "货币政策", "宏观环境", "利率变化"]
    },
    {
        "query": "这个行业的竞争格局怎么样？",
        "intent_category": "research",
        "intent_subcategory": "industry_landscape",
        "route": "research",
        "extracted_entities": {"topic": "competition", "scope": "industry"},
        "handling_strategy": "分析行业竞争格局、市场份额和进入壁垒",
        "difficulty": "standard",
        "common_variations": ["行业竞争", "market share", "护城河", "竞争态势"]
    },
    {
        "query": "公司管理层最近有什么变动？",
        "intent_category": "research",
        "intent_subcategory": "management_change",
        "route": "research",
        "extracted_entities": {"topic": "management", "event": "personnel_change"},
        "handling_strategy": "搜索管理层变动新闻，评估对公司的影响",
        "difficulty": "standard",
        "common_variations": ["CEO变动", "高管离职", "管理层更替", "leadership change"]
    },
    {
        "query": " upcoming earnings 什么时候发布？市场预期如何？",
        "intent_category": "research",
        "intent_subcategory": "earnings_calendar",
        "route": "research",
        "extracted_entities": {"event": "earnings_release", "info_needed": "date_and_expectations"},
        "handling_strategy": "获取财报发布日期和市场一致预期",
        "difficulty": "standard",
        "common_variations": ["财报什么时候出", "业绩发布", "earnings date", "业绩预期"]
    },
    {
        "query": "这家公司的护城河是什么？",
        "intent_category": "research",
        "intent_subcategory": "moat_analysis",
        "route": "research",
        "extracted_entities": {"topic": "competitive_advantage", "intent": "evaluation"},
        "handling_strategy": "分析公司的竞争优势和护城河宽度",
        "difficulty": "complex",
        "common_variations": ["竞争优势", "护城河分析", "moat", "sustainable advantage"]
    },
    {
        "query": "机构最近是在增持还是减持？",
        "intent_category": "research",
        "intent_subcategory": "institutional_activity",
        "route": "research",
        "extracted_entities": {"signal": "institutional_ownership", "trend": "changes"},
        "handling_strategy": "获取机构持仓变化数据，分析资金流向",
        "difficulty": "standard",
        "common_variations": ["机构持仓", "基金增持", "institutional ownership", "smart money"]
    },

    # ========== 投资建议类（advisor）- 8条 ==========
    {
        "query": "现在适合买入吗，还是再等等？",
        "intent_category": "advisor",
        "intent_subcategory": "investment_timing",
        "route": "advisor_only",
        "extracted_entities": {"decision_type": "entry", "uncertainty": "timing"},
        "handling_strategy": "基于已有分析给出择时建议",
        "difficulty": "standard",
        "common_variations": ["能不能买", "现在入场", "什么价位买", "buy now or wait"]
    },
    {
        "query": "如果已经亏损20%，应该止损还是补仓？",
        "intent_category": "advisor",
        "intent_subcategory": "loss_handling",
        "route": "advisor_only",
        "extracted_entities": {"current_loss": "20%", "options": ["stop_loss", "average_down"]},
        "handling_strategy": "评估仓位管理策略，给出具体操作建议",
        "difficulty": "complex",
        "common_variations": ["亏了怎么办", "被套了", "要不要割肉", "stop loss or add"]
    },
    {
        "query": "这只股票占我仓位的50%，风险大吗？",
        "intent_category": "advisor",
        "intent_subcategory": "concentration_risk",
        "route": "advisor_only",
        "extracted_entities": {"position_size": "50%", "risk_type": "concentration"},
        "handling_strategy": "评估集中度风险，建议仓位调整",
        "difficulty": "standard",
        "common_variations": ["仓位太重", "集中持股", "要不要减仓", "position sizing"]
    },
    {
        "query": "目标价应该是多少？止损位设在哪里？",
        "intent_category": "advisor",
        "intent_subcategory": "price_targets",
        "route": "advisor_only",
        "extracted_entities": {"request": ["target_price", "stop_loss"]},
        "handling_strategy": "基于估值模型给出目标价区间和止损建议",
        "difficulty": "complex",
        "common_variations": ["target price", "止盈止损", "目标价位", "exit strategy"]
    },
    {
        "query": "我的投资期限是3年，适合投资这只股票吗？",
        "intent_category": "advisor",
        "intent_subcategory": "time_horizon_fit",
        "route": "advisor_only",
        "extracted_entities": {"time_horizon": "3y", "intent": "fit_assessment"},
        "handling_strategy": "评估股票特性与用户投资期限的匹配度",
        "difficulty": "standard",
        "common_variations": ["长期持有", "investment horizon", "持有期", "timeframe"]
    },
    {
        "query": "能总结一下这只股票的投资亮点和风险吗？",
        "intent_category": "advisor",
        "intent_subcategory": "summary_request",
        "route": "advisor_only",
        "extracted_entities": {"request_type": "summary", "aspects": ["bull_case", "risks"]},
        "handling_strategy": "综合已有分析生成投资摘要",
        "difficulty": "standard",
        "common_variations": ["总结一下", "investment thesis", "bull vs bear", "优缺点"]
    },
    {
        "query": "估值已经这么高了，还能涨吗？",
        "intent_category": "advisor",
        "intent_subcategory": "valuation_concern",
        "route": "advisor_only",
        "extracted_entities": {"concern": "high_valuation", "question": "upside_potential"},
        "handling_strategy": "分析高估值的合理性，评估增长能否支撑估值",
        "difficulty": "complex",
        "common_variations": ["太贵了", "估值泡沫", "overvalued", "还能买吗"]
    },
    {
        "query": "考虑到我的保守风险偏好，这只股票合适吗？",
        "intent_category": "advisor",
        "intent_subcategory": "risk_profile_fit",
        "route": "advisor_only",
        "extracted_entities": {"risk_profile": "conservative", "intent": "fit_assessment"},
        "handling_strategy": "评估股票风险特征与用户偏好的匹配度",
        "difficulty": "standard",
        "common_variations": ["风险偏好", "risk tolerance", "适合我吗", "保守投资者"]
    },

    # ========== 模糊/歧义类（ambiguous）- 5条 ==========
    {
        "query": "这个怎么样？",
        "intent_category": "ambiguous",
        "intent_subcategory": "unclear_intent",
        "route": "advisor_only",
        "extracted_entities": {},
        "handling_strategy": "先澄清用户具体想了解哪方面（财务/新闻/建议）",
        "difficulty": "ambiguous",
        "common_variations": ["怎么看", "评价一下", "说说这个", "如何", "怎么样"]
    },
    {
        "query": "分析一下",
        "intent_category": "ambiguous",
        "intent_subcategory": "vague_request",
        "route": "full",
        "extracted_entities": {"intent": "complete_analysis"},
        "handling_strategy": "执行完整分析（财务+研究+建议）",
        "difficulty": "ambiguous",
        "common_variations": ["分析一下", "看看这个", "分析一下这只股票", "analyse this"]
    },
    {
        "query": "PE高但是增长快，怎么权衡？",
        "intent_category": "ambiguous",
        "intent_subcategory": "multi_factor_tradeoff",
        "route": "full",
        "extracted_entities": {"factors": ["high_pe", "high_growth"], "need_synthesis": True},
        "handling_strategy": "需要财务数据+行业研究+投资建议综合分析",
        "difficulty": "complex",
        "common_variations": ["贵但增长好", "估值和增长矛盾", "growth vs value", "tradeoff"]
    },
    {
        "query": "和之前分析的那只股票比哪个更好？",
        "intent_category": "ambiguous",
        "intent_subcategory": "cross_session_comparison",
        "route": "advisor_only",
        "extracted_entities": {"reference_type": "previous_analysis", "comparison": True},
        "handling_strategy": "从记忆检索历史分析记录进行对比",
        "difficulty": "complex",
        "requires_memory": True,
        "common_variations": ["和之前那只比", "哪个更好", "对比下", "compare with previous"]
    },
    {
        "query": "为什么涨跌？",
        "intent_category": "ambiguous",
        "intent_subcategory": "price_movement_cause",
        "route": "research",
        "extracted_entities": {"topic": "price_movement", "question": "causation"},
        "handling_strategy": "搜索近期新闻和市场因素解释价格波动",
        "difficulty": "ambiguous",
        "common_variations": ["为什么涨了", "为什么跌了", "price movement", "股价波动原因"]
    },

    # ========== 非股票相关（off_topic）- 7条 ==========
    {
        "query": "今天的天气怎么样？",
        "intent_category": "off_topic",
        "intent_subcategory": "chitchat",
        "route": "unknown",
        "extracted_entities": {},
        "handling_strategy": "礼貌拒绝并引导回股票分析场景",
        "difficulty": "standard",
        "common_variations": ["你好", "在吗", "讲个笑话", "天气如何", "hello"]
    },
    {
        "query": "帮我算一下复利收益",
        "intent_category": "off_topic",
        "intent_subcategory": "calculation_request",
        "route": "unknown",
        "extracted_entities": {"task_type": "calculation"},
        "handling_strategy": "超出能力范围，建议用户使用专业计算工具",
        "difficulty": "standard",
        "common_variations": ["算收益率", "复利计算", "投资回报计算", "compound interest"]
    },
    {
        "query": "推荐几只好股票",
        "intent_category": "off_topic",
        "intent_subcategory": "stock_recommendation",
        "route": "unknown",
        "extracted_entities": {"request": "general_recommendation"},
        "handling_strategy": "无法提供具体个股推荐，建议用户先提供股票代码",
        "difficulty": "standard",
        "common_variations": ["有什么好股票", "推荐股票", "买什么好", "stock picks"]
    },
    {
        "query": "你怎么看比特币？",
        "intent_category": "off_topic",
        "intent_subcategory": "crypto_question",
        "route": "unknown",
        "extracted_entities": {"asset_class": "crypto", "ticker": "BTC"},
        "handling_strategy": "说明本平台专注于股票分析，不提供加密货币建议",
        "difficulty": "standard",
        "common_variations": ["比特币", "加密货币", "crypto", "以太坊", "ETH"]
    },
    {
        "query": "教我怎么看K线图",
        "intent_category": "off_topic",
        "intent_subcategory": "education_request",
        "route": "unknown",
        "extracted_entities": {"topic": "technical_analysis", "intent": "education"},
        "handling_strategy": "建议用户参考专业技术分析教程",
        "difficulty": "standard",
        "common_variations": ["怎么看图", "技术分析教学", "K线教学", "chart analysis"]
    },
    {
        "query": "哪个券商开户好？",
        "intent_category": "off_topic",
        "intent_subcategory": "broker_question",
        "route": "unknown",
        "extracted_entities": {"topic": "broker_selection"},
        "handling_strategy": "不评论具体券商，建议用户自行比较",
        "difficulty": "standard",
        "common_variations": ["开户推荐", "券商对比", "哪个平台好", "broker recommendation"]
    },
    {
        "query": "下周大盘会怎么走？",
        "intent_category": "off_topic",
        "intent_subcategory": "market_prediction",
        "route": "unknown",
        "extracted_entities": {"scope": "broad_market", "time": "future"},
        "handling_strategy": "无法预测大盘走势，建议关注个股基本面",
        "difficulty": "standard",
        "common_variations": ["市场走势", "大盘预测", "市场方向", "market outlook"]
    },
]


def get_cases_by_category(category: str) -> List[Dict[str, Any]]:
    """按意图类别获取案例"""
    return [case for case in INTENT_KNOWLEDGE_CASES if case["intent_category"] == category]


def get_cases_by_route(route: str) -> List[Dict[str, Any]]:
    """按路由获取案例"""
    return [case for case in INTENT_KNOWLEDGE_CASES if case["route"] == route]


def get_all_queries() -> List[str]:
    """获取所有query用于构建向量索引"""
    queries = []
    for case in INTENT_KNOWLEDGE_CASES:
        queries.append(case["query"])
        # 也可以加入变体
        queries.extend(case.get("common_variations", []))
    return queries
