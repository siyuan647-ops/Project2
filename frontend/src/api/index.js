import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 min for long agent analysis
})

// ── SSE stream helper (POST with manual parsing) ───────────────────

function _streamSSE(url, body, { onMessage, onTurnComplete, onReport, onError }) {
  fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
    .then(async (response) => {
      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Unknown error' }))
        onError(err.detail || 'Request failed')
        return
      }
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const lines = buffer.split('\n')
        buffer = lines.pop()
        let eventType = ''
        for (const line of lines) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            const data = line.slice(5).trim()
            if (!data) continue
            try {
              const parsed = JSON.parse(data)
              if (eventType === 'agent_message' && onMessage) {
                onMessage(parsed)
              } else if (eventType === 'turn_complete' && onTurnComplete) {
                onTurnComplete(parsed)
              } else if (eventType === 'report' && onReport) {
                onReport(parsed)
              }
            } catch {
              // non-JSON data, skip
            }
          }
        }
      }
    })
    .catch((err) => onError(err.message))
}

// ── Advisor: legacy one-shot ───────────────────────────────────────

export function analyzeStock(ticker, onMessage, onReport, onError) {
  _streamSSE('/api/advisor/analyze', { ticker }, { onMessage, onReport, onError })
}

// ── Advisor: multi-turn conversations ──────────────────────────────

export function createConversation(ticker) {
  return api.post('/advisor/conversations', { ticker })
}

export function listConversations(limit = 20) {
  return api.get('/advisor/conversations', { params: { limit } })
}

export function getConversation(convId) {
  return api.get(`/advisor/conversations/${convId}`)
}

// 【修改】: 改为同步调用，直接返回完整结果
export function startInitialAnalysis(convId) {
  return api.post(`/advisor/conversations/${convId}/initial`)
}

// 【修改】: 改为同步调用，直接返回完整结果
export function sendFollowUp(convId, question) {
  return api.post(`/advisor/conversations/${convId}/messages`, { question })
}

// ── Agent traces (thinking process) ─────────────────────────────────

export function getAgentTraces(convId, traceType = null, limit = 100) {
  const params = { limit }
  if (traceType) params.trace_type = traceType
  return api.get(`/advisor/conversations/${convId}/traces`, { params })
}

export function getAgentTraceSummary(convId) {
  return api.get(`/advisor/conversations/${convId}/traces/summary`)
}

// ── Credit risk ────────────────────────────────────────────────────

export function uploadCreditFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/credit/predict', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function downloadResult(filename) {
  return `/api/credit/download/${encodeURIComponent(filename)}`
}

export function downloadTemplate() {
  return '/api/credit/template'
}

export default api
