<template>
  <div class="advisor-page">
    <div class="advisor-layout">
      <!-- Sidebar: conversation list -->
      <aside class="sidebar">
        <div class="sidebar-header">
          <h3>会话记录</h3>
          <el-button size="small" @click="resetToNew">+ 新建</el-button>
        </div>
        <div class="conv-list">
          <div
            v-for="c in conversations"
            :key="c.id"
            :class="['conv-item', { active: c.id === conversationId }]"
            @click="openConversation(c.id)"
          >
            <div class="conv-title">{{ c.title }}</div>
            <div class="conv-meta">{{ formatTime(c.updated_at) }}</div>
          </div>
          <div v-if="!conversations.length" class="conv-empty">暂无会话</div>
        </div>
      </aside>

      <!-- Main area -->
      <main class="main-area">
        <h2>🤖 多智能体投资顾问</h2>
        <el-alert
          title="⚠️ 本平台分析结果由 AI 生成，仅供参考，不构成任何投资建议。投资有风险，入市需谨慎。"
          type="warning"
          :closable="false"
          show-icon
          style="margin-bottom: 16px"
        />

        <!-- New conversation: ticker input -->
        <div v-if="!conversationId" class="start-section">
          <p class="desc">输入股票代码，AI 顾问团队将自动分析并生成战略投资计划</p>
          <div class="input-row">
            <el-input
              v-model="ticker"
              placeholder="输入股票代码，如 AAPL、GOOGL、TSLA"
              size="large"
              :disabled="loading"
              @keyup.enter="startNewConversation"
              style="max-width: 400px"
            >
              <template #prepend>Ticker</template>
            </el-input>
            <el-button type="primary" size="large" :loading="loading" @click="startNewConversation">
              开始分析
            </el-button>
          </div>
        </div>

        <!-- Active conversation -->
        <div v-if="conversationId" class="chat-section">
          <!-- Loading indicator -->
          <div v-if="loading" class="loading-indicator">
            <el-icon class="loading-icon"><Loading /></el-icon>
            <span class="loading-title">{{ loadingText }}</span>
            <div class="loading-progress">
              <div class="progress-step" :class="{ active: loadingStep >= 1, done: loadingStep > 1 }">
                <span class="step-num">1</span>
                <span class="step-text">并行分析</span>
              </div>
              <div class="progress-line" :class="{ active: loadingStep >= 2 }"></div>
              <div class="progress-step" :class="{ active: loadingStep >= 2, done: loadingStep > 2 }">
                <span class="step-num">2</span>
                <span class="step-text">汇总报告</span>
              </div>
              <div class="progress-line" :class="{ active: loadingStep >= 3 }"></div>
              <div class="progress-step" :class="{ active: loadingStep >= 3 }">
                <span class="step-num">3</span>
                <span class="step-text">完成</span>
              </div>
            </div>
            <div class="loading-hint">研究分析师和财务分析师正在并行工作中，请稍候...</div>
          </div>

          <!-- Agent status cards -->
          <div v-if="loading || messages.length" class="agent-cards">
            <el-card v-for="agent in agents" :key="agent.key" :class="['agent-card', agent.status]">
              <div class="agent-icon">{{ agent.icon }}</div>
              <div class="agent-name">{{ agent.label }}</div>
              <el-tag :type="statusTagType(agent.status)" size="small">
                {{ statusLabel(agent.status) }}
              </el-tag>
            </el-card>
          </div>

          <!-- Thinking process viewer -->
          <div v-if="conversationId && !initialLoading" class="thinking-section">
            <el-button
              type="info"
              size="small"
              @click="toggleThinkingPanel"
              :icon="showThinkingPanel ? 'ArrowUp' : 'ArrowDown'"
            >
              {{ showThinkingPanel ? '隐藏思考过程' : '查看思考过程' }}
            </el-button>

            <el-collapse-transition>
              <div v-if="showThinkingPanel" class="thinking-panel">
                <div class="thinking-header">
                  <h4>🧠 AI 思考过程</h4>
                  <el-button
                    type="primary"
                    size="small"
                    :loading="loadingTraces"
                    @click="loadTraces"
                  >
                    刷新
                  </el-button>
                </div>

                <div v-if="loadingTraces" class="thinking-loading">
                  <el-icon class="loading-icon"><Loading /></el-icon>
                  加载中...
                </div>

                <div v-else-if="traces.length === 0" class="thinking-empty">
                  暂无思考过程记录
                </div>

                <div v-else class="thinking-timeline">
                  <div
                    v-for="(trace, i) in traces"
                    :key="i"
                    :class="['thinking-item', trace.trace_type]"
                  >
                    <div class="thinking-meta">
                      <el-tag size="small" :type="traceTypeColor(trace.trace_type)">
                        {{ formatTraceType(trace.trace_type) }}
                      </el-tag>
                      <span class="thinking-agent">{{ trace.agent_name }}</span>
                      <span class="thinking-time">{{ formatTime(trace.created_at) }}</span>
                    </div>
                    <div class="thinking-content" v-html="renderMarkdown(trace.content)"></div>
                    <div v-if="trace.metadata" class="thinking-metadata">
                      <pre>{{ JSON.stringify(trace.metadata, null, 2) }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </el-collapse-transition>
          </div>

          <!-- Messages stream -->
          <div v-if="messages.length" class="messages-container" ref="messagesRef">
            <div v-for="(msg, i) in messages" :key="i" :class="['message-item', msg.sender === 'user' ? 'user-msg' : 'agent-msg']">
              <div class="msg-header">
                <el-tag
                  :type="msg.sender === 'user' ? 'info' : agentTagType(msg.sender)"
                  size="small"
                >
                  {{ msg.sender === 'user' ? '你' : msg.sender }}
                </el-tag>
                <span v-if="msg.isHistory" class="history-badge">历史</span>
              </div>
              <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>
            </div>
          </div>

          <!-- Follow-up input -->
          <div v-if="conversationId && !initialLoading" class="followup-row">
            <el-input
              v-model="followUpText"
              placeholder="继续提问，如：估值风险有多大？ 或 结合最新新闻再分析"
              size="large"
              :disabled="loading"
              @keyup.enter="sendFollowUp"
            />
            <el-button
              type="primary"
              size="large"
              :loading="followUpLoading"
              :disabled="!followUpText.trim()"
              @click="sendFollowUp"
            >
              发送
            </el-button>
          </div>
        </div>

        <!-- Error -->
        <el-alert v-if="error" :title="error" type="error" show-icon closable @close="error = ''" style="margin-top: 16px" />
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import {
  createConversation,
  listConversations,
  getConversation,
  startInitialAnalysis,
  sendFollowUp as apiSendFollowUp,
  getAgentTraces,
} from '../api'
import { marked } from 'marked'

// ── State ──────────────────────────────────────────────────────────

const ticker = ref('')
const conversationId = ref('')
const loading = ref(false)
const loadingStep = ref(1)
const loadingText = ref('AI 正在分析中，请稍候...')
const initialLoading = ref(false)
const followUpLoading = ref(false)
const messages = ref([])
const followUpText = ref('')
const error = ref('')
const messagesRef = ref(null)
const conversations = ref([])

// Thinking process viewer state
const showThinkingPanel = ref(false)
const traces = ref([])
const loadingTraces = ref(false)

const agents = reactive([
  { key: 'research', label: '研究分析师', icon: '🔍', status: 'idle' },
  { key: 'financial', label: '财务分析师', icon: '📊', status: 'idle' },
  { key: 'advisor', label: '投资顾问', icon: '💼', status: 'idle' },
])

// ── Helpers ─────────────────────────────────────────────────────────

function statusTagType(s) {
  return { idle: 'info', working: 'warning', done: 'success' }[s] || 'info'
}
function statusLabel(s) {
  return { idle: '等待中', working: '工作中...', done: '已完成' }[s] || '等待中'
}
function agentTagType(sender) {
  if (sender.includes('Research')) return ''
  if (sender.includes('Financial')) return 'warning'
  if (sender.includes('Investment')) return 'success'
  return 'info'
}
function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}
function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

// ── Thinking process viewer ────────────────────────────────────────

function toggleThinkingPanel() {
  showThinkingPanel.value = !showThinkingPanel.value
  if (showThinkingPanel.value && traces.value.length === 0) {
    loadTraces()
  }
}

async function loadTraces() {
  if (!conversationId.value) return
  loadingTraces.value = true
  try {
    const { data } = await getAgentTraces(conversationId.value)
    traces.value = data.traces || []
  } catch (e) {
    console.error('Failed to load traces:', e)
    ElMessage.warning('加载思考过程失败')
  } finally {
    loadingTraces.value = false
  }
}

function formatTraceType(type) {
  const typeMap = {
    'task_start': '🚀 开始任务',
    'task_complete': '✅ 完成任务',
    'phase_start': '📍 阶段开始',
    'phase_complete': '🏁 阶段完成',
    'message': '💬 消息',
    'thinking': '🤔 思考',
    'tool_decision': '🔧 工具决策',
    'tool_call': '📞 工具调用',
    'tool_result': '📊 工具结果',
    'error': '❌ 错误',
    'output': '📝 输出',
  }
  return typeMap[type] || type
}

function traceTypeColor(type) {
  const colorMap = {
    'task_start': 'success',
    'task_complete': 'success',
    'phase_start': 'warning',
    'phase_complete': 'warning',
    'message': 'info',
    'thinking': 'primary',
    'tool_decision': 'warning',
    'tool_call': 'danger',
    'tool_result': 'success',
    'error': 'danger',
    'output': 'info',
  }
  return colorMap[type] || 'info'
}

function resetAgentStatus() {
  agents.forEach((a) => (a.status = 'idle'))
}

function updateAgentStatus(sender) {
  if (sender.includes('Research')) {
    agents[0].status = 'working'
  } else if (sender.includes('Financial')) {
    agents[0].status = 'done'
    agents[1].status = 'working'
  } else if (sender.includes('Investment')) {
    agents[1].status = 'done'
    agents[2].status = 'working'
  }
}

// ── Conversation list ───────────────────────────────────────────────

async function loadConversations() {
  try {
    const resp = await listConversations()
    conversations.value = resp.data
  } catch {
    // Silently ignore — sidebar is supplementary
  }
}

async function openConversation(convId) {
  try {
    const resp = await getConversation(convId)
    const conv = resp.data
    conversationId.value = conv.id
    ticker.value = conv.ticker
    messages.value = (conv.messages || []).map((m) => ({
      sender: m.sender,
      content: m.content,
      isHistory: true,
    }))
    resetAgentStatus()
    // Mark agents as done if there are existing messages
    if (messages.value.length) {
      agents[0].status = 'done'
      agents[1].status = 'done'
      agents[2].status = 'done'
    }
    scrollToBottom()
  } catch {
    ElMessage.error('无法加载会话')
  }
}

function resetToNew() {
  conversationId.value = ''
  ticker.value = ''
  messages.value = []
  followUpText.value = ''
  error.value = ''
  resetAgentStatus()
}

// ── Start new conversation ──────────────────────────────────────────

async function startNewConversation() {
  const t = ticker.value.trim().toUpperCase()
  if (!t) {
    ElMessage.warning('请输入股票代码')
    return
  }

  loading.value = true
  initialLoading.value = true
  loadingStep.value = 1
  loadingText.value = 'AI 顾问团队正在并行分析中...'
  error.value = ''
  messages.value = []
  resetAgentStatus()
  agents[0].status = 'working'
  agents[1].status = 'working'

  try {
    // 1. Create conversation
    const resp = await createConversation(t)
    conversationId.value = resp.data.id

    // 2. Start initial analysis (synchronous with parallel execution)
    // Simulate progress updates since backend is sync
    const progressInterval = setInterval(() => {
      if (loadingStep.value < 2) {
        loadingStep.value = 2
        loadingText.value = '投资顾问正在汇总分析结果...'
      } else if (loadingStep.value < 3) {
        loadingStep.value = 3
        loadingText.value = '报告生成中...'
      }
    }, 15000) // Update every 15 seconds

    try {
      const { data } = await startInitialAnalysis(conversationId.value)
      clearInterval(progressInterval)
      messages.value.push({ sender: 'Investment_Advisor', content: data.report, isHistory: false })
      agents[0].status = 'done'
      agents[1].status = 'done'
      agents[2].status = 'done'
      loading.value = false
      initialLoading.value = false
      loadConversations()
      scrollToBottom()
    } catch (e) {
      clearInterval(progressInterval)
      error.value = e.response?.data?.detail || e.message || '分析失败'
      loading.value = false
      initialLoading.value = false
    }
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '创建会话失败'
    loading.value = false
    initialLoading.value = false
  }
}

// ── Follow-up ───────────────────────────────────────────────────────

async function sendFollowUp() {
  const q = followUpText.value.trim()
  if (!q || !conversationId.value) return

  followUpLoading.value = true
  loading.value = true
  error.value = ''
  resetAgentStatus()

  // Show user's own message
  messages.value.push({ sender: 'user', content: q, isHistory: false })
  followUpText.value = ''
  scrollToBottom()

  // 【修改】: 改为同步调用
  try {
    const { data } = await apiSendFollowUp(conversationId.value, q)
    messages.value.push({ sender: 'Investment_Advisor', content: data.answer, isHistory: false })
    // Mark active agents as done
    agents.forEach((a) => { if (a.status === 'working') a.status = 'done' })
    followUpLoading.value = false
    loading.value = false
    loadConversations()
    scrollToBottom()
  } catch (e) {
    error.value = e.response?.data?.detail || e.message || '请求失败'
    followUpLoading.value = false
    loading.value = false
  }
}

// ── Init ────────────────────────────────────────────────────────────

onMounted(() => {
  loadConversations()
})
</script>

<style scoped>
.advisor-page {
  height: 100%;
}
.advisor-layout {
  display: flex;
  gap: 0;
  height: calc(100vh - 80px);
}

/* ── Sidebar ───────────────────────────────────────────────────── */
.sidebar {
  width: 240px;
  min-width: 240px;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
  background: #fafbfc;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #e4e7ed;
}
.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
}
.conv-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}
.conv-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}
.conv-item:hover {
  background: #ecf5ff;
}
.conv-item.active {
  background: #d9ecff;
}
.conv-title {
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conv-meta {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
}
.conv-empty {
  text-align: center;
  color: #ccc;
  padding: 24px;
  font-size: 13px;
}

/* ── Main ──────────────────────────────────────────────────────── */
.main-area {
  flex: 1;
  padding: 24px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
}
.main-area h2 {
  margin-bottom: 8px;
}
.desc {
  color: #666;
  margin-bottom: 24px;
}
.start-section {
  flex: 1;
}
.input-row {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 24px;
}

/* ── Chat ──────────────────────────────────────────────────────── */
.chat-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.agent-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 16px;
}
.agent-card {
  text-align: center;
  transition: all 0.3s;
}
.agent-card.working {
  border-color: #e6a23c;
  box-shadow: 0 0 12px rgba(230, 162, 60, 0.25);
}
.agent-card.done {
  border-color: #67c23a;
}
.agent-icon {
  font-size: 32px;
  margin-bottom: 8px;
}
.agent-name {
  font-weight: 600;
  margin-bottom: 8px;
}
.messages-container {
  flex: 1;
  min-height: 200px;
  max-height: calc(100vh - 380px);
  overflow-y: auto;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
  background: #fafafa;
  margin-bottom: 16px;
}
.message-item {
  margin-bottom: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #eee;
}
.message-item:last-child {
  border-bottom: none;
  margin-bottom: 0;
}
.message-item.user-msg {
  background: #ecf5ff;
  border-radius: 8px;
  padding: 12px;
  border-bottom: none;
}
.msg-header {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.history-badge {
  font-size: 11px;
  color: #999;
  background: #f0f0f0;
  padding: 1px 6px;
  border-radius: 4px;
}
.msg-content {
  line-height: 1.7;
  color: #333;
  word-break: break-word;
}
.msg-content :deep(h1),
.msg-content :deep(h2),
.msg-content :deep(h3) {
  margin: 12px 0 8px;
}
.msg-content :deep(ul),
.msg-content :deep(ol) {
  padding-left: 20px;
}
.msg-content :deep(strong) {
  color: #409eff;
}

/* ── Follow-up input ───────────────────────────────────────────── */
.followup-row {
  display: flex;
  gap: 12px;
  align-items: center;
}

/* ── Thinking process viewer ─────────────────────────────────────── */
.thinking-section {
  margin: 16px 0;
}

.thinking-panel {
  margin-top: 12px;
  background: #f8f9fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  padding: 16px;
}

.thinking-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #e4e7ed;
}

.thinking-header h4 {
  margin: 0;
  color: #409eff;
}

.thinking-loading,
.thinking-empty {
  text-align: center;
  padding: 24px;
  color: #909399;
}

.thinking-timeline {
  max-height: 500px;
  overflow-y: auto;
}

.thinking-item {
  padding: 12px;
  margin-bottom: 8px;
  background: white;
  border-radius: 6px;
  border-left: 3px solid #409eff;
}

.thinking-item.task_start,
.thinking-item.task_complete {
  border-left-color: #67c23a;
  background: #f0f9ff;
}

.thinking-item.phase_start,
.thinking-item.phase_complete {
  border-left-color: #e6a23c;
  background: #fdf6ec;
}

.thinking-item.error {
  border-left-color: #f56c6c;
  background: #fef0f0;
}

.thinking-item.tool_call,
.thinking-item.tool_result {
  border-left-color: #909399;
  font-family: monospace;
  font-size: 13px;
}

.thinking-meta {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.thinking-agent {
  font-weight: 600;
  color: #606266;
}

.thinking-time {
  color: #909399;
  font-size: 12px;
  margin-left: auto;
}

.thinking-content {
  color: #303133;
  line-height: 1.6;
  word-break: break-word;
}

.thinking-content :deep(pre) {
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  overflow-x: auto;
}

.thinking-content :deep(code) {
  font-family: 'Courier New', monospace;
  background: #f5f7fa;
  padding: 2px 4px;
  border-radius: 3px;
}

.thinking-metadata {
  margin-top: 8px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
}

.thinking-metadata pre {
  margin: 0;
  font-size: 12px;
  color: #606266;
  overflow-x: auto;
}

/* ── Loading indicator ──────────────────────────────────────────── */
.loading-indicator {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
  background: #f5f7fa;
  border-radius: 8px;
  margin-bottom: 16px;
  color: #409eff;
  font-size: 16px;
  gap: 12px;
}
.loading-icon {
  font-size: 32px;
  animation: rotate 1s linear infinite;
}
@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
.loading-hint {
  font-size: 13px;
  color: #909399;
}
.loading-title {
  font-weight: 600;
  font-size: 16px;
  margin-bottom: 8px;
}
.loading-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px 0;
}
.progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}
.progress-step .step-num {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e4e7ed;
  color: #909399;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 600;
  transition: all 0.3s;
}
.progress-step .step-text {
  font-size: 12px;
  color: #909399;
  transition: all 0.3s;
}
.progress-step.active .step-num {
  background: #409eff;
  color: #fff;
}
.progress-step.active .step-text {
  color: #409eff;
  font-weight: 500;
}
.progress-step.done .step-num {
  background: #67c23a;
  color: #fff;
}
.progress-line {
  width: 40px;
  height: 2px;
  background: #e4e7ed;
  transition: all 0.3s;
}
.progress-line.active {
  background: #409eff;
}
</style>
