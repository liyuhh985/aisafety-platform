<template>
  <div class="history-view">
    <div class="content-wrapper">
      <!-- 头部操作与检索栏 -->
      <header class="history-header">
        <div class="header-left">
          <router-link to="/" class="back-btn" title="返回主控中心">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <span>返回主控</span>
          </router-link>
          <div class="header-titles">
            <span class="system-tag">三明市城市安全智能研判档案专库</span>
            <h1 class="page-title">隐患研判历史与处置档案</h1>
          </div>
        </div>

        <div class="header-right">
          <button class="refresh-btn btn-pill-secondary" :disabled="loading" @click="fetchReports">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': loading }">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            <span>刷新档案</span>
          </button>
        </div>
      </header>

      <main class="main-content">
        <!-- 加载状态 -->
        <div v-if="loading" class="state-card glass-card">
          <div class="spinner"></div>
          <p>正在调阅档案库全量安全研判记录...</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMessage" class="state-card glass-card error-card">
          <p class="error-msg">{{ errorMessage }}</p>
          <button class="btn-pill btn-pill-primary" @click="fetchReports">重试调阅</button>
        </div>

        <!-- 空数据引导 -->
        <div v-else-if="!reports.length" class="state-card glass-card">
          <div class="empty-icon-circle">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="1.6">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
            </svg>
          </div>
          <h3 class="empty-title">当前尚无归档记录</h3>
          <p class="empty-desc">在影像智能研判工作台中完成现场研判后，点击“归档此报告至历史”即可在此永久调阅公文鉴定书。</p>
          <button class="btn-pill btn-pill-primary mt-4" @click="router.push('/analysis')">前往影像研判</button>
        </div>

        <!-- 档案卡片多列自适应网格 -->
        <div v-else class="report-grid">
          <article
            v-for="item in reports"
            :key="item.id"
            class="report-card glass-card glass-card-hover"
            @click="viewDetail(item.id)"
          >
            <!-- 封面图 -->
            <div class="card-cover">
              <SecureImage v-if="item.imageUrl" :src="item.imageUrl" alt="隐患现场照片" class="cover-image" />
              <div v-else class="no-cover">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.8">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
                <span>无现场留存图像</span>
              </div>
              <div class="cover-badge-box">
              </div>
            </div>

            <!-- 卡片信息区 -->
            <div class="card-body">
              <div class="card-meta-row">
                <span class="category-name">{{ item.hazardCategory || '综合安全隐患' }}</span>
                <span class="severity-stamp" :class="severityClass(item.severity)">
                  {{ item.severity || '未定级' }}风险
                </span>
              </div>

              <p class="card-desc">{{ item.description || '现场隐患记录与智能研判公文' }}</p>

              <div class="card-footer">
                <span class="date-text num-font">{{ formatDate(item.createdAt) }}</span>
                <div class="action-hint">
                  <span>查阅鉴定书</span>
                  <span class="arrow">→</span>
                </div>
              </div>
            </div>
          </article>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import SecureImage from '../components/SecureImage.vue'
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { normalizeReport } from '../utils/report.js'

const router = useRouter()
const reports = ref([])
const loading = ref(true)
const errorMessage = ref('')

function formatDate(value) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

function severityClass(value) {
  return { '高': 'sev-high', '中': 'sev-medium', '低': 'sev-low' }[value] || 'sev-low'
}

function viewDetail(id) {
  router.push(`/report/${id}`)
}

async function fetchReports() {
  const token = localStorage.getItem('token')
  if (!token) {
    router.replace('/login?redirect=' + encodeURIComponent('/history'))
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/report', {
      headers: { 'Authorization': 'Bearer ' + token },
    })
    const json = await response.json().catch(() => ({}))
    if (response.status === 401) {
      router.replace('/login?redirect=' + encodeURIComponent('/history'))
      return
    }
    if (!response.ok || json.code !== 200) {
      throw new Error(json.message || ('请求失败（' + response.status + '）'))
    }
    const rawList = Array.isArray(json.data) ? json.data : []
    reports.value = rawList.map(normalizeReport)
  } catch (error) {
    console.error('获取报告列表失败', error)
    errorMessage.value = error.message || '加载历史记录失败，请检查网络后重试'
  } finally {
    loading.value = false
  }
}

onMounted(fetchReports)
</script>

<style scoped>
.history-view {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  overflow-x: hidden;
}

.content-wrapper {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px 24px 56px;
}

/* 头部操作栏 */
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 9999px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.1);
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.back-btn:hover {
  background: #f1f5f9;
  border-color: rgba(26, 115, 232, 0.4);
  color: #1a73e8;
  transform: translateX(-2px);
  box-shadow: 0 4px 12px rgba(26, 115, 232, 0.08);
}
.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.07);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.header-titles {
  display: flex;
  flex-direction: column;
}
.system-tag {
  font-size: 11px;
  color: #64748b;
  letter-spacing: 0.04em;
  margin-bottom: 2px;
}
.page-title {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.refresh-btn {
  padding: 8px 16px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.spin-anim {
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* 状态卡片 */
.state-card {
  padding: 60px 20px;
  text-align: center;
  max-width: 500px;
  margin: 60px auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  background: #ffffff;
}
.spinner {
  width: 24px;
  height: 24px;
  border: 2px solid #dbeafe;
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
.error-msg {
  color: #ef4444;
  font-size: 14px;
}
.empty-icon-circle {
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: #eff6ff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 6px;
}
.empty-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.empty-desc {
  font-size: 13px;
  color: #64748b;
  line-height: 1.6;
}

/* 档案多列网格 */
.report-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
  width: 100%;
}

.report-card {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border-radius: 18px;
  background: #ffffff;
}

.card-cover {
  position: relative;
  width: 100%;
  height: 170px;
  background: #f1f5f9;
  overflow: hidden;
}
.cover-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s ease;
}
.report-card:hover .cover-image {
  transform: scale(1.04);
}
.no-cover {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.cover-badge-box {
  position: absolute;
  top: 10px;
  left: 10px;
}
.dossier-code {
  font-size: 10px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(15, 23, 42, 0.75);
  color: #ffffff;
  backdrop-filter: blur(6px);
}

.card-body {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex: 1;
}

.card-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.category-name {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}
.severity-stamp {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 6px;
}

.card-desc {
  font-size: 13px;
  color: #475569;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  margin-bottom: auto;
}

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid #f1f5f9;
}
.date-text {
  font-size: 11px;
  color: #94a3b8;
}
.action-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: #1a73e8;
}
.arrow {
  transition: transform 0.2s;
}
.report-card:hover .arrow {
  transform: translateX(3px);
}

@media (max-width: 640px) {
  .content-wrapper {
    padding: 14px 12px 30px;
  }
  .page-title {
    font-size: 16px;
  }
  .report-grid {
    grid-template-columns: 1fr;
    gap: 14px;
  }
}
</style>

