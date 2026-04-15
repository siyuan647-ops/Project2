<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <div class="header-content">
        <h1 class="logo" @click="$router.push('/')">
          <span class="logo-icon">📊</span> FinAI Platform
        </h1>
        <el-menu
          :router="true"
          mode="horizontal"
          :default-active="$route.path"
          class="nav-menu"
        >
          <el-menu-item index="/">首页</el-menu-item>
          <el-menu-item index="/advisor">智能投资顾问</el-menu-item>
          <el-menu-item index="/credit">信用风险预测</el-menu-item>
        </el-menu>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: #f5f7fa;
}
.app-container {
  min-height: 100vh;
}
.app-header {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
  padding: 0 24px;
  height: 64px !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}
.header-content {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  height: 100%;
}
.logo {
  color: #e0e0e0;
  font-size: 20px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  margin-right: 40px;
}
.logo-icon {
  font-size: 24px;
}
.nav-menu {
  background: transparent !important;
  border: none !important;
  flex: 1;
}
.nav-menu .el-menu-item {
  color: #b0b0b0 !important;
  border-bottom: none !important;
  font-size: 15px;
}
.nav-menu .el-menu-item:hover,
.nav-menu .el-menu-item.is-active {
  color: #ffffff !important;
  background: rgba(255, 255, 255, 0.08) !important;
  border-bottom: 2px solid #409eff !important;
}
.app-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
  width: 100%;
}
</style>
