-- 查看 agent_traces 表结构
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'agent_traces';

-- 查看某个对话的Agent思考过程（替换 '你的conv_id' 为实际的ID）
SELECT
    agent_name,
    trace_type,
    LEFT(content, 200) as content_preview,
    created_at
FROM agent_traces
WHERE conversation_id = '93cf37f93359'
ORDER BY created_at ASC;

-- 查看有多少条trace记录
SELECT COUNT(*) as total_traces FROM agent_traces;

-- 查看所有对话的trace统计
SELECT
    conversation_id,
    COUNT(*) as trace_count
FROM agent_traces
GROUP BY conversation_id
ORDER BY trace_count DESC;
