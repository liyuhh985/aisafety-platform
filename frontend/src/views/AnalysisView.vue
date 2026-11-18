<template>
  <div class="analysis-view">
    <div class="content-wrapper">
      <!-- 顶部 Header (Antigravity 优雅白底) -->
      <header class="workbench-header">
        <div class="header-left">
          <router-link to="/" class="back-btn" title="返回主控中心">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <span>返回主控</span>
          </router-link>
          <div class="title-wrap">
            <div class="system-tag">
              <span class="status-indicator-dot"></span>
              <span class="tag-name">三明市城市安全智能研判专网</span>
            </div>
            <h1 class="page-title">隐患影像智能研判工作台</h1>
          </div>
        </div>

        <div class="header-right">
          <div class="status-capsule" :class="{ 'active': analyzing }">
            <span class="capsule-dot" :class="{ 'analyzing': analyzing, 'done': analysisDone }"></span>
            <span class="capsule-text">{{ analyzing ? '研判作业中...' : (analysisDone ? '研判就绪' : '待载入影像') }}</span>
          </div>
        </div>
      </header>

      <!-- 双栏/单栏自适应作业台 -->
      <main class="workbench-layout">
        <!-- 左栏：影像采集与靶向标定视口 -->
        <section class="viewport-col">
          <div class="panel-card glass-card">
            <div class="panel-head">
              <div class="head-title">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
                <span>现场取证影像标定视口</span>
              </div>
              <span v-if="imageUrl" class="head-badge">已导入</span>
            </div>

            <!-- 图像上传与标定视口 -->
            <div
              class="inspect-viewport"
              :class="{ 'has-image': imageUrl, 'dragover': isDragging, 'disabled': analyzing }"
              @click="handleUploadClick"
              @dragover.prevent="isDragging = true"
              @dragleave.prevent="isDragging = false"
              @drop.prevent="handleDrop"
            >
              <input
                ref="fileInput"
                type="file"
                accept="image/*"
                class="file-input"
                @change="handleFileChange"
              />

              <!-- 四角瞄准准星角标 -->
              <div class="reticle-corner corner-tl"></div>
              <div class="reticle-corner corner-tr"></div>
              <div class="reticle-corner corner-bl"></div>
              <div class="reticle-corner corner-br"></div>

              <!-- 未上传占位引导 -->
              <div v-if="!imageUrl" class="upload-guide">
                <div class="guide-icon-box">
                  <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="1.8">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
                    <polyline points="17 8 12 3 7 8"/>
                    <line x1="12" y1="3" x2="12" y2="15"/>
                  </svg>
                </div>
                <p class="guide-title">点击或拖拽现场照片至此</p>
                <p class="guide-meta">支持 JPG / PNG / WEBP · 最大 10MB</p>
                <button type="button" class="select-btn btn-pill-primary" @click.stop="handleUploadClick">选择照片</button>
              </div>

              <!-- 已上传图片展示舞台 -->
              <div v-else class="preview-stage">
                <SecureImage :src="imageUrl" alt="现场隐患影像" class="stage-img" />
                <div class="scan-laser" v-if="analyzing"></div>
                <button v-if="!analyzing" class="delete-stage-btn" @click.stop="removeImage" title="更换照片">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                  </svg>
                  <span>更换照片</span>
                </button>
              </div>
            </div>

            <!-- 控制操作区 -->
            <div class="viewport-controls">
              <!-- 未分析时：开始分析按钮 -->
              <button
                v-if="imageUrl && !analyzing && !analysisDone"
                class="action-btn btn-pill btn-pill-primary w-full"
                @click="startAnalysis"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polygon points="5 3 19 12 5 21 5 3"/>
                </svg>
                <span>启动 AI 视觉多模态研判</span>
              </button>

              <!-- 分析中：取消按钮 -->
              <button
                v-if="analyzing"
                class="action-btn cancel-btn w-full"
                @click="cancelAnalysis"
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
                <span>中断分析作业</span>
              </button>

              <!-- 分析完成后的归档操作 -->
              <div v-if="analysisDone" class="completion-bar">
                <button
                  class="save-btn"
                  :class="{ 'is-saved': saved }"
                  :disabled="saved"
                  @click="saveToHistory"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/>
                    <polyline points="17 21 17 13 7 13 7 21"/>
                    <polyline points="7 3 7 8 15 8"/>
                  </svg>
                  <span>{{ saved ? '已归档至数据库 ✓' : '归档此报告至历史档案' }}</span>
                </button>
              </div>
            </div>
          </div>
        </section>

        <!-- 右栏：研判报告台与阶段步进器 -->
        <section class="report-col">
          <div class="panel-card glass-card">
            <!-- 阶段进度步进器 Stepper -->
            <div class="stepper-bar">
              <div class="step-item" :class="{ 'done': visionResult || analysisDone, 'active': analyzing && !visionResult }">
                <span class="step-badge">1</span>
                <span class="step-name">特征解构</span>
              </div>
              <div class="step-line" :class="{ 'active': visionResult }"></div>

              <div class="step-item" :class="{ 'done': retrievalContent || analysisDone, 'active': analyzing && visionResult && !retrievalContent }">
                <span class="step-badge">2</span>
                <span class="step-name">法规检索</span>
              </div>
              <div class="step-line" :class="{ 'active': retrievalContent }"></div>

              <div class="step-item" :class="{ 'done': reportContent || analysisDone, 'active': analyzing && retrievalContent && !analysisDone }">
                <span class="step-badge">3</span>
                <span class="step-name">报告生成</span>
              </div>
              <div class="step-line" :class="{ 'active': analysisDone }"></div>

              <div class="step-item" :class="{ 'done': analysisDone }">
                <span class="step-badge">4</span>
                <span class="step-name">闭环归档</span>
              </div>
            </div>

            <!-- 分析中的实时提示栏 -->
            <div v-if="analyzing" class="running-status-bar">
              <div class="spinner"></div>
              <span class="running-text">{{ statusMessage || '多模态模型与法规知识库深度比对分析中...' }}</span>
            </div>

            <!-- 未开始分析时的空状态引导 -->
            <div v-if="!analyzing && !analysisDone && !visionResult" class="idle-state-placeholder">
              <div class="blueprint-circle">
                <svg width="34" height="34" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="1.6">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                </svg>
              </div>
              <h3 class="idle-title">等待载入现场隐患照片</h3>
              <p class="idle-desc">请在左侧上传施工、道路或市政设施照片，启动后系统将自动进行视觉要素提取、法规检索与隐患判定。</p>
            </div>

            <!-- 研判内容输出容器 -->
            <div v-else class="dossier-stream">
              <!-- 视觉识别核心定性卡片 -->
              <div v-if="visionResult" class="dossier-card vision-summary">
                <div class="dossier-header">
                  <div class="tag-row">
                    <span class="category-pill">{{ visionResult.hazard_category || '安全隐患' }}</span>
                    <span class="severity-stamp" :class="'sev-' + (visionResult.severity || '低')">
                      {{ visionResult.severity || '未定级' }}风险
                    </span>
                  </div>
                  <span class="dossier-id num-font">VERDICT-AI-VERIFIED</span>
                </div>

                <div class="dossier-body">
                  <div class="desc-box">
                    <div class="desc-label">隐患特征定性：</div>
                    <p class="desc-text">{{ visionResult.description || '图像特征解析中...' }}</p>
                  </div>

                  <div v-if="visionResult.location_hint" class="meta-row">
                    <span class="meta-label">点位推断：</span>
                    <span class="meta-val">{{ visionResult.location_hint }}</span>
                  </div>

                  <!-- 整改建议项清单 -->
                  <div v-if="visionResult.rectification && visionResult.rectification.length" class="rectification-box">
                    <div class="rect-title">安全处置与整改技术要求：</div>
                    <ul class="rect-list">
                      <li v-for="(item, idx) in visionResult.rectification" :key="idx">
                        <span class="rect-bullet num-font">0{{ idx + 1 }}</span>
                        <span class="rect-text">{{ item }}</span>
                      </li>
                    </ul>
                  </div>
                </div>
              </div>

              <!-- 法规案例依据 -->
              <div v-if="retrievalContent" class="dossier-card reference-card">
                <div class="card-title-bar">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
                    <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
                  </svg>
                  <span>知识库依据（现行法规标准 / 历史案例比对）</span>
                </div>
                <div class="retrieval-body" v-html="renderedRetrieval"></div>
              </div>

              <!-- 完整研判报告书 -->
              <div v-if="reportContent" class="dossier-card report-card">
                <div class="card-title-bar">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                  </svg>
                  <span>城市安全隐患综合研判与鉴定报告</span>
                </div>
                <div class="report-body" v-html="renderedReport"></div>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { clearAnalysisState, readAnalysisState } from '../utils/analysis-session.js'
import SecureImage from '../components/SecureImage.vue'

const router = useRouter()

const imageUrl = ref('')
const uploadedImageUrl = ref('')
const uploadedFileId = ref(null)
const selectedFile = ref(null)
const isDragging = ref(false)
const fileInput = ref(null)

const analyzing = ref(false)
const analysisDone = ref(false)
const statusMessage = ref('')

const visionResult = ref(null)
const retrievalContent = ref('')
const reportContent = ref('')

const saved = ref(false)
const saveReportId = ref(null)

let abortController = null

onMounted(() => {
  try {
    const s = readAnalysisState(sessionStorage, localStorage.getItem('userId'))
    if (s && (s.imageUrl || s.visionResult || s.reportContent)) {
      imageUrl.value = s.uploadedImageUrl || s.imageUrl || ''
      uploadedImageUrl.value = s.uploadedImageUrl || ''
      uploadedFileId.value = s.uploadedFileId || null
      visionResult.value = s.visionResult || null
      retrievalContent.value = s.retrievalContent || ''
      reportContent.value = s.reportContent || ''
      analysisDone.value = !!s.analysisDone
    }
  } catch (e) {
    console.warn('恢复状态失败', e)
  }
})

function saveState() {
  try {
    sessionStorage.setItem('safety_analysis', JSON.stringify({
      userId: localStorage.getItem('userId'),
      imageUrl: uploadedImageUrl.value || '',
      uploadedImageUrl: uploadedImageUrl.value,
      uploadedFileId: uploadedFileId.value,
      visionResult: visionResult.value,
      retrievalContent: retrievalContent.value,
      reportContent: reportContent.value,
      analysisDone: analysisDone.value,
    }))
  } catch (e) {
    console.warn('保存状态失败', e)
  }
}

function goBack() {
  router.push('/')
}

function handleUploadClick() {
  if (analyzing.value) return
  fileInput.value && fileInput.value.click()
}

function handleFileChange(e) {
  const file = e.target.files && e.target.files[0]
  if (file) processFile(file)
}

function handleDrop(e) {
  isDragging.value = false
  if (analyzing.value) return
  const file = e.dataTransfer.files && e.dataTransfer.files[0]
  if (file) processFile(file)
}

function processFile(file) {
  if (!file.type.startsWith('image/')) {
    alert('请上传有效的图片文件')
    return
  }
  if (file.size > 10 * 1024 * 1024) {
    alert('图片大小不能超过 10MB')
    return
  }
  selectedFile.value = file
  if (imageUrl.value && imageUrl.value.startsWith('blob:')) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = URL.createObjectURL(file)
  uploadedImageUrl.value = ''
  uploadedFileId.value = null
  visionResult.value = null
  retrievalContent.value = ''
  reportContent.value = ''
  analysisDone.value = false
  saved.value = false
  saveReportId.value = null
  clearAnalysisState(sessionStorage)
}

function removeImage() {
  if (imageUrl.value && imageUrl.value.startsWith('blob:')) URL.revokeObjectURL(imageUrl.value)
  imageUrl.value = ''
  uploadedImageUrl.value = ''
  uploadedFileId.value = null
  selectedFile.value = null
  visionResult.value = null
  retrievalContent.value = ''
  reportContent.value = ''
  analysisDone.value = false
  saved.value = false
  saveReportId.value = null
  clearAnalysisState(sessionStorage)
  if (fileInput.value) fileInput.value.value = ''
}

async function startAnalysis() {
  if (!selectedFile.value || analyzing.value) return

  analyzing.value = true
  analysisDone.value = false
  statusMessage.value = '正在上传影像并连接多模态研判管线...'
  visionResult.value = null
  retrievalContent.value = ''
  reportContent.value = ''
  saved.value = false

  const token = localStorage.getItem('token')
  if (!token) {
    analyzing.value = false
    alert('请先登录后再进行 AI 分析')
    router.push('/login')
    return
  }

  abortController = new AbortController()

  try {
    statusMessage.value = '正在上传图片并校验文件...'
    const uploadForm = new FormData()
    uploadForm.append('file', selectedFile.value)
    const uploadRes = await fetch('/api/upload/image', {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${token}` },
      body: uploadForm,
      signal: abortController.signal,
    })
    const uploadJson = await uploadRes.json().catch(() => ({}))
    if (!uploadRes.ok || uploadJson.code !== 200 || !uploadJson.data?.fileId) {
      throw new Error(uploadJson.message || `图片上传失败 (${uploadRes.status})`)
    }
    uploadedFileId.value = uploadJson.data.fileId
    uploadedImageUrl.value = uploadJson.data.url || ''
    saveState()

    statusMessage.value = '图片已保存，正在连接多模态研判管线...'
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const headers = { 'Authorization': `Bearer ${token}` }

    const response = await fetch('/api/ai/analyze/stream', {
      method: 'POST',
      headers,
      body: formData,
      signal: abortController.signal,
    })

    if (!response.ok) {
      throw new Error(`服务器响应异常 (${response.status})`)
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

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const dataStr = line.slice(6).trim()
        if (!dataStr) continue

        try {
          const event = JSON.parse(dataStr)
          switch (event.type) {
            case 'vision':
              visionResult.value = typeof event.content === 'string'
                ? JSON.parse(event.content)
                : event.content
              saveState()
              break
            case 'retrieval':
              retrievalContent.value += event.content
              break
            case 'report':
              reportContent.value += event.content
              saveState()
              break
            case 'done':
              analyzing.value = false
              analysisDone.value = true
              statusMessage.value = ''
              saveState()
              break
          }
        } catch (e) {
          console.warn('SSE parse error:', e)
        }
      }
    }
  } catch (e) {
    if (e.name === 'AbortError') {
      console.log('分析任务已取消')
    } else {
      console.error('分析请求失败', e)
      alert(e.message || '分析服务暂时不可用，请稍后重试')
    }
  } finally {
    analyzing.value = false
    abortController = null
  }
}

function cancelAnalysis() {
  if (abortController) {
    abortController.abort()
  }
  analyzing.value = false
  statusMessage.value = ''
}

async function saveToHistory() {
  if (saved.value) return

  const token = localStorage.getItem('token')
  if (!token) {
    alert('请先登录后再保存报告')
    router.push('/login')
    return
  }

  if (!uploadedFileId.value) {
    alert('图片尚未完成上传，请重新分析后再保存')
    return
  }

  const v = visionResult.value || {}
  const payload = {
    fileId: uploadedFileId.value,
    hazardCategory: v.hazard_category || '综合隐患',
    severity: v.severity || '中',
    description: v.description || '现场隐患记录',
    rectification: Array.isArray(v.rectification) ? v.rectification : [],
    reportText: reportContent.value || '',
  }

  try {
    const res = await fetch('/api/report', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      if (res.status === 401) {
        alert('登录态已失效，请重新登录')
        router.push('/login')
        return
      }
      throw new Error(`保存失败 (${res.status})`)
    }

    const json = await res.json()
    if (json.code === 200) {
      saved.value = true
      saveReportId.value = json.data?.id
      alert('研判报告已成功归档至数据库')
    } else {
      alert(json.message || '保存失败')
    }
  } catch (e) {
    console.error('保存报告失败', e)
    alert('保存失败，请检查网络后重试')
  }
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/### (.+)/g, '<h4 class="report-h4">$1</h4>')
    .replace(/## (.+)/g, '<h3 class="report-h3">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="report-strong">$1</strong>')
    .replace(/\n{2,}/g, '</p><p class="report-para">')
    .replace(/\n/g, '<br/>')
}

const renderedRetrieval = computed(() => renderMarkdown(retrievalContent.value))
const renderedReport = computed(() => renderMarkdown(reportContent.value))
</script>

<style scoped>
.analysis-view {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  overflow-x: hidden;
}

.content-wrapper {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px 24px 48px;
  min-width: 0;
}

/* 顶部 Header */
.workbench-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 16px;
  margin-bottom: 20px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.07);
  gap: 10px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

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

.title-wrap {
  min-width: 0;
}

.system-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #64748b;
  margin-bottom: 2px;
}

.page-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-right {
  flex-shrink: 0;
}

.status-capsule {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 9999px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  font-size: 11px;
  color: #475569;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.02);
}
.capsule-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
}
.capsule-dot.analyzing {
  background: #1a73e8;
  box-shadow: 0 0 6px rgba(26, 115, 232, 0.4);
  animation: pulse-dot 1.5s infinite;
}
.capsule-dot.done {
  background: #16a34a;
  box-shadow: 0 0 6px rgba(22, 163, 74, 0.4);
}

/* 工作台布局网格 */
.workbench-layout {
  display: grid;
  grid-template-columns: minmax(360px, 420px) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
  width: 100%;
}

.viewport-col, .report-col {
  width: 100%;
  min-width: 0;
}

.panel-card {
  padding: 22px;
  width: 100%;
  min-width: 0;
  background: #ffffff;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.head-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}
.head-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  border: 1px solid #dbeafe;
  font-weight: 600;
}

/* 准星视口 */
.inspect-viewport {
  position: relative;
  width: 100%;
  min-height: 270px;
  border: 1.5px dashed #cbd5e1;
  border-radius: 14px;
  background: #f8fafc;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.2s;
}
.inspect-viewport.has-image {
  border-style: solid;
  border-color: #e2e8f0;
  background: #090d16;
  cursor: default;
}
.inspect-viewport.dragover {
  border-color: #1a73e8;
  background: #eff6ff;
}

.reticle-corner {
  position: absolute;
  width: 10px;
  height: 10px;
  border-color: #1a73e8;
  pointer-events: none;
}
.corner-tl { top: 8px; left: 8px; border-top: 2px solid; border-left: 2px solid; }
.corner-tr { top: 8px; right: 8px; border-top: 2px solid; border-right: 2px solid; }
.corner-bl { bottom: 8px; left: 8px; border-bottom: 2px solid; border-left: 2px solid; }
.corner-br { bottom: 8px; right: 8px; border-bottom: 2px solid; border-right: 2px solid; }

.file-input { display: none; }

.upload-guide {
  text-align: center;
  padding: 24px 16px;
}
.guide-icon-box {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: #eff6ff;
  border: 1px solid #dbeafe;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}
.guide-title {
  font-size: 14px;
  font-weight: 600;
  color: #334155;
  margin-bottom: 4px;
}
.guide-meta {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 14px;
}
.select-btn {
  padding: 6px 20px;
  font-size: 13px;
}

.preview-stage {
  position: relative;
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stage-img {
  max-width: 100%;
  max-height: 380px;
  object-fit: contain;
}

.scan-laser {
  position: absolute;
  top: 0; left: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, transparent, #38bdf8, transparent);
  box-shadow: 0 0 10px #38bdf8;
  animation: laser-scan 2.4s ease-in-out infinite;
}
@keyframes laser-scan {
  0% { top: 5%; opacity: 0.3; }
  50% { top: 92%; opacity: 1; }
  100% { top: 5%; opacity: 0.3; }
}

.delete-stage-btn {
  position: absolute;
  top: 10px; right: 10px;
  display: flex; align-items: center; gap: 4px;
  padding: 5px 12px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(8px);
  border: 1px solid #fecaca;
  color: #dc2626;
  border-radius: 9999px;
  font-size: 11px;
  cursor: pointer;
}

.viewport-controls {
  margin-top: 18px;
}
.action-btn {
  padding: 12px;
  font-size: 14px;
  width: 100%;
}
.cancel-btn {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
  border-radius: 9999px;
  font-weight: 600;
  cursor: pointer;
}

.completion-bar { width: 100%; }
.save-btn {
  width: 100%;
  padding: 12px;
  border-radius: 9999px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  transition: all 0.2s;
}
.save-btn.is-saved {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #15803d;
}

/* 步进器 */
.stepper-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: #f8fafc;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
  margin-bottom: 18px;
  width: 100%;
}
.step-item {
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0.45;
}
.step-item.active { opacity: 1; }
.step-item.done { opacity: 1; }
.step-badge {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #cbd5e1;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
}
.step-item.active .step-badge {
  background: #1a73e8;
}
.step-item.done .step-badge {
  background: #16a34a;
}
.step-name {
  font-size: 12px;
  color: #334155;
  font-weight: 600;
  white-space: nowrap;
}
.step-line {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 8px;
}
.step-line.active {
  background: #1a73e8;
}

/* 运行状态 */
.running-status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  margin-bottom: 16px;
}
.spinner {
  width: 16px; height: 16px;
  border: 2px solid #bfdbfe;
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}
.running-text { font-size: 13px; color: #1d4ed8; font-weight: 500; }
@keyframes spin { to { transform: rotate(360deg); } }

/* 空状态占位 */
.idle-state-placeholder {
  padding: 48px 16px;
  text-align: center;
}
.blueprint-circle {
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: #eff6ff;
  border: 1px dashed #93c5fd;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}
.idle-title { font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 6px; }
.idle-desc { font-size: 13px; color: #64748b; line-height: 1.6; }

/* 研判内容流 */
.dossier-stream {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dossier-card {
  padding: 18px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  word-break: break-all;
}

.dossier-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding-bottom: 10px;
  border-bottom: 1px solid #e2e8f0;
}
.tag-row { display: flex; align-items: center; gap: 8px; }
.category-pill {
  padding: 3px 10px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  border: 1px solid #bfdbfe;
  font-size: 12px;
  font-weight: 700;
}
.severity-stamp {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 800;
}
.dossier-id { font-size: 11px; color: #64748b; font-weight: 600; }

.desc-box { margin-bottom: 10px; }
.desc-label { font-size: 12px; color: #475569; font-weight: 600; margin-bottom: 3px; }
.desc-text { font-size: 14px; color: #0f172a; line-height: 1.6; }

.meta-row { font-size: 12px; color: #64748b; margin-bottom: 10px; }
.meta-val { color: #0f172a; font-weight: 500; }

.rectification-box {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #cbd5e1;
}
.rect-title { font-size: 12px; font-weight: 700; color: #0f172a; margin-bottom: 8px; }
.rect-list { list-style: none; display: flex; flex-direction: column; gap: 6px; }
.rect-list li { display: flex; align-items: flex-start; gap: 8px; font-size: 13px; color: #334155; line-height: 1.5; }
.rect-bullet { font-size: 11px; font-weight: 700; color: #1a73e8; background: #eff6ff; padding: 1px 6px; border-radius: 4px; flex-shrink: 0; }

.card-title-bar {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 700; color: #0f172a;
  margin-bottom: 10px; padding-bottom: 8px;
  border-bottom: 1px solid #e2e8f0;
}

.retrieval-body, .report-body { font-size: 13px; color: #334155; line-height: 1.8; word-break: break-all; }
:deep(.report-h3) { font-size: 15px; font-weight: 700; color: #1a73e8; margin: 14px 0 6px; border-left: 3px solid #1a73e8; padding-left: 6px; }
:deep(.report-h4) { font-size: 13px; font-weight: 600; color: #0f172a; margin: 10px 0 4px; }
:deep(.report-strong) { color: #1a73e8; font-weight: 600; }
:deep(.report-para) { margin-bottom: 8px; }

/* 响应式适配 */
@media (max-width: 900px) {
  .workbench-layout {
    grid-template-columns: 1fr;
    gap: 16px;
  }
}

@media (max-width: 640px) {
  .content-wrapper {
    padding: 12px 10px 30px;
  }

  .workbench-header {
    padding-bottom: 10px;
    margin-bottom: 12px;
  }

  /* back-label removed */
  .system-tag { display: none; }
  .page-title { font-size: 15px; }

  .panel-card {
    padding: 14px 12px;
  }

  .inspect-viewport {
    min-height: 200px;
  }
  .stage-img {
    max-height: 240px;
  }

  .step-name {
    display: none;
  }
  .stepper-bar {
    justify-content: space-around;
    padding: 8px 10px;
  }
  .step-line {
    margin: 0 4px;
  }
}
</style>

