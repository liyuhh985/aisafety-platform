<template>
  <div class="report-detail-view">
    <div class="content-wrapper">
      <!-- 头部操作条 -->
      <header class="detail-header">
        <div class="header-left">
          <button class="back-btn btn-pill-secondary" @click="goBack" title="返回档案库">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <span class="back-text">返回档案库</span>
          </button>
        </div>
        <div class="header-right">
          <button class="print-btn btn-pill btn-pill-primary" @click="handlePrint">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="6 9 6 2 18 2 18 9"/>
              <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/>
              <rect x="6" y="14" width="12" height="8"/>
            </svg>
            <span>打印 / 导出公文 PDF</span>
          </button>
        </div>
      </header>

      <main class="main-content">
        <!-- 加载中 -->
        <div v-if="loading" class="state-card glass-card">
          <div class="spinner"></div>
          <p>正在调阅城市安全隐患智能研判公文原件...</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMessage" class="state-card glass-card error-card">
          <p class="error-msg">{{ errorMessage }}</p>
          <button class="btn-pill btn-pill-primary" @click="goBack">返回历史档案列表</button>
        </div>

        <!-- 权威公文式报告正文 (可打印区域) -->
        <article v-else-if="report" class="official-dossier printable-area">
          <!-- 公文抬头 -->
          <div class="dossier-headline glass-card">
            <div class="headline-badge">
              <span>三明市城市运行管理服务平台 · 隐患处置专件</span>
            </div>
            <h1 class="headline-title">城市安全隐患智能研判与鉴定意见书</h1>
            <div class="headline-meta num-font">
              <span>归档日期：{{ formatDate(report.createdAt) }}</span>
              <span>防伪标识：VERIFIED-OFFICIAL</span>
            </div>
          </div>

          <!-- 双栏展示网格 -->
          <div class="dossier-grid">
            <!-- 左侧：现场影像与靶向研判结论 -->
            <div class="dossier-left-col">
              <!-- 现场影像视口 -->
              <section class="section-card glass-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                    <circle cx="12" cy="13" r="4"/>
                  </svg>
                  <span>现场取证影像原件</span>
                </div>
                <div class="image-stage">
                  <SecureImage v-if="report.imageUrl" :src="report.imageUrl" alt="隐患现场取证" class="dossier-img" />
                  <div v-else class="no-img-text">未留存现场取证图像</div>
                </div>
              </section>

              <!-- 研判评定印章面板 -->
              <section class="section-card glass-card verdict-summary-card">
                <div class="verdict-row">
                  <div>
                    <span class="label-text">隐患定性类别</span>
                    <div class="category-text">{{ report.hazardCategory || '综合安全隐患' }}</div>
                  </div>
                  <div class="stamp-box">
                    <span class="severity-stamp" :class="severityClass(report.severity)">
                      {{ report.severity || '未定级' }}风险
                    </span>
                  </div>
                </div>

                <div class="field-block">
                  <span class="label-text">现场隐患特征简述</span>
                  <p class="field-content">{{ report.description || '暂无详细描述记录。' }}</p>
                </div>
              </section>
            </div>

            <!-- 右侧：公文正文与整改措施要求 -->
            <div class="dossier-right-col">
              <!-- 研判报告全案正文 -->
              <section class="section-card glass-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  <span>综合安全评估鉴定报告正文</span>
                </div>
                <div class="report-text-body">
                  {{ report.reportText || '暂无详细评估报告正文。' }}
                </div>
              </section>

              <!-- 整改处置闭环行动项 -->
              <section class="section-card glass-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <polyline points="9 11 12 14 22 4"/>
                    <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
                  </svg>
                  <span>安全防范与整改技术要求清单</span>
                </div>
                <ul v-if="report.rectification && report.rectification.length" class="rectification-checklist">
                  <li v-for="(item, index) in report.rectification" :key="index">
                    <span class="check-box num-font">0{{ index + 1 }}</span>
                    <span class="check-text">{{ item }}</span>
                  </li>
                </ul>
                <p v-else class="empty-field-text">未指定特定整改措施。</p>
              </section>
            </div>
          </div>
        </article>
      </main>
    </div>
  </div>
</template>

<script setup>
import SecureImage from '../components/SecureImage.vue'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { normalizeReport } from '../utils/report.js'

const route = useRoute()
const router = useRouter()
const report = ref(null)
const loading = ref(true)
const errorMessage = ref('')

function goBack() {
  router.push('/history')
}

function formatDate(value) {
  if (!value) return ''
  return String(value).slice(0, 10)
}

function severityClass(value) {
  return { '高': 'sev-high', '中': 'sev-medium', '低': 'sev-low' }[value] || 'sev-low'
}

function redirectToLogin() {
  router.replace('/login?redirect=' + encodeURIComponent(route.fullPath))
}

function handlePrint() {
  window.print()
}

async function fetchReport() {
  const token = localStorage.getItem('token')
  if (!token) {
    redirectToLogin()
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    const response = await fetch('/api/report/' + encodeURIComponent(route.params.id), {
      headers: { 'Authorization': 'Bearer ' + token },
    })
    const json = await response.json().catch(() => ({}))
    if (response.status === 401) {
      redirectToLogin()
      return
    }
    if (response.status === 404) {
      errorMessage.value = '报告档案不存在或已删除'
      return
    }
    if (!response.ok || json.code !== 200 || !json.data) {
      throw new Error(json.message || ('报告加载失败（' + response.status + '）'))
    }
    report.value = normalizeReport(json.data)
  } catch (error) {
    console.error('获取报告详情失败', error)
    errorMessage.value = error.message || '报告加载失败，请检查网络后重试'
  } finally {
    loading.value = false
  }
}

onMounted(fetchReport)
</script>

<style scoped>
.report-detail-view {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  overflow-x: hidden;
}

.content-wrapper {
  max-width: 1240px;
  margin: 0 auto;
  padding: 20px 24px 56px;
}

/* 头部操作栏 */
.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 16px;
  margin-bottom: 24px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.07);
}

.back-btn {
  padding: 6px 14px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.print-btn {
  padding: 8px 18px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
}

/* 状态卡片 */
.state-card {
  padding: 60px 20px;
  text-align: center;
  max-width: 500px;
  margin: 60px auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
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
@keyframes spin { to { transform: rotate(360deg); } }

.error-card {
  border-color: #fecaca;
}
.error-msg {
  color: #dc2626;
  font-size: 14px;
}

/* 公文抬头部份 */
.official-dossier {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.dossier-headline {
  text-align: center;
  padding: 30px 24px;
  background: #ffffff;
}

.headline-badge {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 9999px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  margin-bottom: 12px;
}

.headline-title {
  font-size: 24px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: 0.02em;
  margin-bottom: 12px;
}

.headline-meta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 24px;
  font-size: 12px;
  color: #64748b;
}

/* 双栏网格 */
.dossier-grid {
  display: grid;
  grid-template-columns: minmax(360px, 440px) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

.dossier-left-col, .dossier-right-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-card {
  padding: 22px;
  background: #ffffff;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 16px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f1f5f9;
}

/* 影像舞台 */
.image-stage {
  border-radius: 12px;
  overflow: hidden;
  background: #090d16;
  min-height: 260px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.dossier-img {
  width: 100%;
  max-height: 420px;
  object-fit: contain;
}
.no-img-text {
  color: #94a3b8;
  font-size: 13px;
}

/* 判定印章与特征 */
.verdict-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 18px;
}
.label-text {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  display: block;
  margin-bottom: 4px;
}
.category-text {
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}

.severity-stamp {
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.05em;
}

.field-block {
  padding-top: 14px;
  border-top: 1px dashed #e2e8f0;
}
.field-content {
  font-size: 14px;
  color: #334155;
  line-height: 1.65;
}

/* 报告正文 */
.report-text-body {
  font-size: 14px;
  color: #334155;
  line-height: 1.85;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 整改建议清单 */
.rectification-checklist {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rectification-checklist li {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  color: #334155;
  line-height: 1.6;
  padding: 10px 12px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
}
.check-box {
  font-size: 11px;
  font-weight: 700;
  color: #1a73e8;
  background: #eff6ff;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.empty-field-text {
  font-size: 13px;
  color: #94a3b8;
}

/* 打印样式适配 */
@media print {
  .detail-header { display: none; }
  .report-detail-view { background: #fff !important; color: #000 !important; }
  .glass-card { background: #fff !important; border: 1px solid #ccc !important; box-shadow: none !important; }
}

/* 响应式断点 */
@media (max-width: 900px) {
  .dossier-grid {
    grid-template-columns: 1fr;
  }
  .content-wrapper {
    padding: 14px 12px 30px;
  }
  .headline-title {
    font-size: 19px;
  }
  .headline-meta {
    flex-direction: column;
    gap: 4px;
  }
}
</style>

