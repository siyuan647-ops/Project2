<template>
  <div class="home-page">
    <section class="hero">
      <h1>多智能体金融决策平台</h1>
      <p class="subtitle">
        AI 驱动的投资分析与信用风险评估，让智能决策触手可及
      </p>
    </section>

    <el-alert
      title="⚠️ 本平台分析结果由 AI 生成，仅供参考，不构成任何投资建议或信贷审批依据。投资有风险，决策需谨慎。"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom: 24px"
    />

    <div class="features">
      <el-card class="feature-card" shadow="hover" @click="$router.push('/advisor')">
        <div class="feature-icon">🤖</div>
        <h2>多智能体投资顾问</h2>
        <p>
          输入任意上市公司股票代码，由<strong>研究分析师、财务分析师、投资顾问</strong>三大 AI
          智能体协同工作，自动搜集新闻、分析财务数据，生成深度定制的<strong>战略投资计划</strong>。
        </p>
        <el-tag type="primary" size="large">开始分析 →</el-tag>
      </el-card>

      <el-card class="feature-card" shadow="hover" @click="$router.push('/credit')">
        <div class="feature-icon">📋</div>
        <h2>AI 信用风险预测</h2>
        <p>
          上传贷款申请人名单 (Excel/CSV)，基于预训练的 XGBoost
          模型进行批量信用评估，自动生成
          <strong>P1-P4 信用等级</strong>，辅助放贷决策。
        </p>
        <el-tag type="success" size="large">开始预测 →</el-tag>
      </el-card>
    </div>

    <section class="tech-stack">
      <h3>技术架构</h3>
      <div class="tech-tags">
        <el-tag v-for="t in techs" :key="t" effect="plain" round>{{ t }}</el-tag>
      </div>
    </section>
  </div>
</template>

<script setup>
const techs = [
  'FastAPI', 'AutoGen', 'Kimi K2.5', 'Vue 3', 'Element Plus',
  'XGBoost', 'yfinance', 'SSE Streaming', 'Docker',
]
</script>

<style scoped>
.home-page {
  max-width: 960px;
  margin: 0 auto;
}
.hero {
  text-align: center;
  padding: 48px 0 32px;
}
.hero h1 {
  font-size: 36px;
  color: #1a1a2e;
  margin-bottom: 12px;
}
.subtitle {
  font-size: 18px;
  color: #666;
}
.features {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-bottom: 40px;
}
.feature-card {
  cursor: pointer;
  transition: transform 0.2s;
  text-align: center;
  padding: 12px;
}
.feature-card:hover {
  transform: translateY(-4px);
}
.feature-icon {
  font-size: 48px;
  margin-bottom: 12px;
}
.feature-card h2 {
  font-size: 22px;
  margin-bottom: 12px;
  color: #1a1a2e;
}
.feature-card p {
  color: #555;
  line-height: 1.7;
  margin-bottom: 16px;
  text-align: left;
}
.tech-stack {
  text-align: center;
  padding: 24px 0 48px;
}
.tech-stack h3 {
  margin-bottom: 16px;
  color: #999;
  font-weight: 400;
}
.tech-tags {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}
</style>
