<template>
  <div class="credit-page">
    <h2>📋 AI 信用风险预测引擎</h2>
    <p class="desc">
      上传贷款申请人名单，AI 将为每位申请人预测信用等级（P1-P4）
    </p>
    <el-alert
      title="⚠️ 信用评估结果由 AI 模型生成，仅供参考，不应作为唯一放贷依据。请结合人工审核进行决策。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 16px"
    />

    <!-- Legend -->
    <div class="legend">
      <el-tag type="success">P1 — 信用最好</el-tag>
      <el-tag type="primary">P2 — 信用次之</el-tag>
      <el-tag type="warning">P3 — 信用较差</el-tag>
      <el-tag type="danger">P4 — 信用最差</el-tag>
    </div>

    <!-- Actions row -->
    <div class="actions">
      <el-button @click="getTemplate">
        📥 下载上传模板
      </el-button>
    </div>

    <!-- Upload area -->
    <el-upload
      ref="uploadRef"
      drag
      :auto-upload="false"
      :limit="1"
      :on-change="handleFileChange"
      :on-exceed="handleExceed"
      accept=".xlsx,.csv"
      class="upload-area"
    >
      <div style="padding: 20px 0">
        <div style="font-size: 48px; color: #c0c4cc; margin-bottom: 8px">📁</div>
        <div class="el-upload__text">
          将文件拖到此处，或 <em>点击上传</em>
        </div>
      </div>
      <template #tip>
        <div class="el-upload__tip">支持 .xlsx 和 .csv 文件，最大 10MB</div>
      </template>
    </el-upload>

    <el-button
      v-if="selectedFile"
      type="primary"
      size="large"
      :loading="loading"
      @click="submitFile"
      style="margin-top: 16px"
    >
      {{ loading ? '预测中...' : '开始预测' }}
    </el-button>

    <!-- Error -->
    <el-alert
      v-if="error"
      :title="error"
      type="error"
      show-icon
      closable
      @close="error = ''"
      style="margin-top: 16px"
    />

    <!-- Warnings -->
    <div v-if="result?.warnings?.length" class="warnings-section">
      <el-alert
        v-for="(w, idx) in result.warnings"
        :key="idx"
        :title="w"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom: 8px"
      />
    </div>

    <!-- Results -->
    <div v-if="result" class="result-section">
      <div class="result-header">
        <h3>预测结果</h3>
        <div>
          <span class="meta">共 {{ result.total_records }} 条记录</span>
          <el-button type="success" @click="downloadFile">📥 下载结果 Excel</el-button>
        </div>
      </div>

      <!-- Distribution -->
      <div class="distribution">
        <el-tag
          v-for="(count, label) in result.distribution"
          :key="label"
          :type="labelTagType(label)"
          size="large"
          effect="dark"
          round
        >
          {{ label }}: {{ count }} 人
        </el-tag>
      </div>

      <!-- Preview table -->
      <el-table v-if="previewData.length" :data="previewData" stripe border style="width: 100%">
        <el-table-column
          v-for="col in previewColumns"
          :key="col"
          :prop="col"
          :label="col"
          :min-width="col === 'Approved_Flag' ? 130 : 100"
        >
          <template #default="{ row }">
            <el-tag
              v-if="col === 'Approved_Flag'"
              :type="labelTagType(row[col])"
              effect="dark"
            >
              {{ row[col] }}
            </el-tag>
            <span v-else>{{ row[col] }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p v-if="previewData.length >= 20" class="preview-hint">仅显示前 20 条，完整数据请下载 Excel</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { uploadCreditFile, downloadResult, downloadTemplate } from '../api'

const uploadRef = ref(null)
const selectedFile = ref(null)
const loading = ref(false)
const error = ref('')
const result = ref(null)
const previewData = ref([])
const previewColumns = ref([])

function labelTagType(label) {
  return { P1: 'success', P2: '', P3: 'warning', P4: 'danger' }[label] || 'info'
}

function handleFileChange(file) {
  selectedFile.value = file.raw
}

function handleExceed() {
  ElMessage.warning('只能上传一个文件，请先移除已选文件')
}

function getTemplate() {
  window.open(downloadTemplate(), '_blank')
}

async function submitFile() {
  if (!selectedFile.value) return
  loading.value = true
  error.value = ''
  result.value = null
  previewData.value = []

  try {
    const resp = await uploadCreditFile(selectedFile.value)
    result.value = resp.data

    // Download result file and parse preview
    const url = downloadResult(resp.data.filename)
    const fileResp = await fetch(url)
    const blob = await fileResp.blob()
    await parseExcelPreview(blob)
  } catch (e) {
    const detail = e.response?.data?.detail
    error.value = detail || e.message || '预测失败'
  } finally {
    loading.value = false
  }
}

async function parseExcelPreview(blob) {
  try {
    const XLSX = await import('https://cdn.sheetjs.com/xlsx-0.20.3/package/xlsx.mjs')
    const ab = await blob.arrayBuffer()
    const wb = XLSX.read(ab)
    const ws = wb.Sheets[wb.SheetNames[0]]
    const data = XLSX.utils.sheet_to_json(ws)
    previewColumns.value = Object.keys(data[0] || {})
    previewData.value = data.slice(0, 20)
  } catch {
    // Fallback: no preview, user can still download the file
    previewColumns.value = []
    previewData.value = []
  }
}

function downloadFile() {
  if (result.value?.filename) {
    window.open(downloadResult(result.value.filename), '_blank')
  }
}
</script>

<style scoped>
.credit-page h2 {
  margin-bottom: 8px;
}
.desc {
  color: #666;
  margin-bottom: 16px;
}
.legend {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.actions {
  margin-bottom: 20px;
}
.upload-area {
  width: 100%;
}
.upload-area :deep(.el-upload-dragger) {
  width: 100%;
}
.result-section {
  margin-top: 24px;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.result-header .meta {
  color: #999;
  margin-right: 12px;
}
.distribution {
  display: flex;
  gap: 16px;
  margin-bottom: 20px;
}
.preview-hint {
  color: #999;
  text-align: center;
  margin-top: 8px;
  font-size: 13px;
}
.warnings-section {
  margin-top: 16px;
}
</style>
