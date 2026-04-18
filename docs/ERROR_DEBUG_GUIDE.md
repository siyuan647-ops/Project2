# 错误排查指南 - 股票投资分析平台

## 🔍 如何查看错误

### 1. 通过 API 端点查看（无需数据库客户端）

#### 查看工具调用统计
```bash
curl http://127.0.0.1:8000/api/admin/tool-logs/stats
```

#### 查看最近的工具调用（包含错误）
```bash
curl http://127.0.0.1:8000/api/admin/tool-logs/recent?limit=50
```

#### 查看特定会话的工具调用
```bash
# 替换 {conv_id} 为实际的会话ID
curl http://127.0.0.1:8000/api/admin/tool-logs/{conv_id}
```

#### 查看请求统计
```bash
curl http://127.0.0.1:8000/api/admin/audit-stats
```

#### 查看健康状态
```bash
curl http://127.0.0.1:8000/api/health
```

---

### 2. 通过浏览器/前端查看

访问以下 URL：
- `http://127.0.0.1:8000/api/admin/tool-logs/stats` - 工具调用统计
- `http://127.0.0.1:8000/api/admin/tool-logs/recent` - 最近工具调用
- `http://127.0.0.1:8000/api/health` - 系统健康状态

---

### 3. 直接查询 PostgreSQL 数据库

#### 连接数据库
```bash
# 如果使用的是 docker-compose 中的 PostgreSQL
docker exec -it project2-postgres-1 psql -U finapp -d financial_platform

# 或者直接使用 psql
psql postgresql://finapp:finapp_secret@localhost:5432/financial_platform
```

#### 常用查询

**查看最近的错误日志：**
```sql
SELECT 
    created_at,
    error_type,
    component,
    severity,
    error_message,
    metadata->>'ticker' as ticker
FROM error_logs 
ORDER BY created_at DESC 
LIMIT 20;
```

**查看特定股票的分析错误：**
```sql
SELECT 
    created_at,
    component,
    error_message,
    error_detail
FROM error_logs 
WHERE metadata->>'ticker' = 'AAPL'
ORDER BY created_at DESC;
```

**查看失败的工具调用：**
```sql
SELECT 
    created_at,
    tool_name,
    error_message,
    data_source
FROM tool_call_logs 
WHERE status = 'error' 
ORDER BY created_at DESC 
LIMIT 20;
```

**查看性能问题：**
```sql
-- 平均执行时间最长的组件
SELECT 
    component,
    metric_type,
    AVG(duration_ms) as avg_ms,
    MAX(duration_ms) as max_ms,
    COUNT(*) as call_count
FROM performance_metrics 
WHERE created_at > now() - interval '1 hour'
GROUP BY component, metric_type
ORDER BY avg_ms DESC;
```

---

## ⚠️ 常见错误及解决方案

### 1. "Stock ticker 'XXX' not found"（股票代码不存在）

**原因：**
- 股票代码拼写错误
- 使用的是美股代码但输入了 A 股代码
- Polygon API 或 Yahoo Finance 无法找到该股票

**解决：**
- 检查股票代码拼写（如 AAPL、GOOGL、TSLA）
- 确保使用正确的美股代码
- 查看工具调用日志确认是哪个数据源失败

---

### 2. "Polygon API error" 或 "Yahoo Finance验证失败"

**原因：**
- API 密钥配置错误或未设置
- 网络连接问题
- API 限流

**解决：**
- 检查 `.env` 文件中的 `POLYGON_API_KEY`
- 如果不使用 Polygon，可以移除该环境变量，系统会自动降级到 Yahoo Finance
- 检查网络连接

---

### 3. "Conversation not found"（会话不存在）

**原因：**
- 会话 ID 错误
- 数据库数据被清理

**解决：**
- 刷新页面重新开始分析
- 检查会话列表 API: `GET /api/advisor/conversations`

---

### 4. 首次输入股票代码无响应/超时

**原因：**
- 并行分析需要较长时间（30秒-2分钟）
- LLM API 调用失败或超时
- 数据库连接问题

**排查步骤：**

1. 查看后端控制台日志是否有错误
2. 检查数据库连接状态：
   ```bash
   curl http://127.0.0.1:8000/api/health
   ```
3. 查看性能指标：
   ```sql
   SELECT * FROM performance_metrics 
   WHERE metric_type = 'total' 
   ORDER BY created_at DESC 
   LIMIT 5;
   ```

---

### 5. "Internal server error"（500错误）

**原因：**
- 未处理的异常
- 数据库连接丢失
- 外部 API 故障

**排查：**
1. 查看后端控制台完整错误堆栈
2. 检查错误日志表：
   ```sql
   SELECT * FROM error_logs 
   WHERE severity = 'critical' 
   ORDER BY created_at DESC 
   LIMIT 10;
   ```

---

## 🛠️ 已修复的问题

### SQL 语法错误（已修复）

**问题：** `storage.py` 中的 `interval '$1 hours'` 语法在 asyncpg 中不正确

**修复：** 改为 `interval '1 hour' * $1`

**影响文件：** `backend/app/storage.py` 第 679、694、795 行

---

## 📝 调试技巧

### 1. 增加日志级别

在 `backend/app/main.py` 中修改日志级别：
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 2. 查看完整的请求/响应

在前端浏览器开发者工具中：
1. 打开 Network 标签
2. 找到 `initial` 或 `conversations` 请求
3. 查看 Response 中的错误详情

### 3. 手动测试 API

```bash
# 1. 创建会话
curl -X POST http://127.0.0.1:8000/api/advisor/conversations \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL"}'

# 2. 使用返回的 id 开始分析
curl -X POST http://127.0.0.1:8000/api/advisor/conversations/{conv_id}/initial
```

---

## 🔄 重启后检查清单

如果问题持续，尝试：

1. **重启后端服务**
2. **检查数据库连接**：`curl http://127.0.0.1:8000/api/health`
3. **验证股票代码验证**：`curl http://127.0.0.1:8000/api/advisor/conversations -d '{"ticker":"AAPL"}'`
4. **查看最近错误**：`curl http://127.0.0.1:8000/api/admin/tool-logs/recent`

---

## 📊 数据库表结构速查

| 表名 | 用途 |
|------|------|
| `conversations` | 会话信息 |
| `messages` | 消息记录 |
| `tool_call_logs` | 工具调用日志（包含错误）|
| `error_logs` | 集中错误日志 |
| `performance_metrics` | 性能指标 |
| `conversation_summaries` | 对话摘要 |
| `meta_memories` | 元记忆（自省）|
| `memory_chunks` | 记忆片段 |
