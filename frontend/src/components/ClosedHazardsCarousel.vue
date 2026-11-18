<template>
  <div v-if="items.length > 0" class="closed-hazards-carousel">
    <!-- 头部标题与控制条 -->
    <div class="carousel-header">
      <div class="header-left">
        <span class="pulse-green-dot"></span>
        <span class="header-title">城市安全治理闭环动态</span>
        <span class="header-badge num-font">已办结 {{ totalCount }} 件</span>
      </div>

      <div class="header-right">
        <button class="nav-arrow-btn" @click="prevSlide" title="上一条" :disabled="items.length <= 1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
        </button>
        <button class="nav-arrow-btn" @click="nextSlide" title="下一条" :disabled="items.length <= 1">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </button>
        <router-link to="/hazard" class="view-all-link">
          <span>全部工单</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="9 18 15 12 9 6"/>
          </svg>
        </router-link>
      </div>
    </div>

    <!-- 轮播卡片视口 -->
    <div
      class="carousel-viewport"
      @mouseenter="pause"
      @mouseleave="resume"
      @touchstart="handleTouchStart"
      @touchend="handleTouchEnd"
    >
      <div class="carousel-track" :style="trackStyle">
        <article
          v-for="(item, index) in loopItems"
          :key="index"
          class="carousel-card glass-card"
          ref="cardRefs"
          @click="goToDetail(item.id)"
        >
          <!-- 背景隐约科技印章水印 (提升治理公信力与质感) -->
          <div class="watermark-seal">
            <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
              <path d="m9 12 2 2 4-4"/>
            </svg>
          </div>

          <div class="card-top-row">
            <div class="badge-group">
              <span class="closed-tag">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span>已验收办结</span>
              </span>
              <span
                v-for="cat in resolveHazardList(item.hazardTypes)"
                :key="`${cat.majorCode}/${cat.subcategoryCode}`"
                class="category-tag"
              >{{ cat.displayText }}</span>
            </div>
            <div class="card-top-right">
              <span class="severity-badge" :class="severityClass(item.severity)">
                {{ formatSeverity(item.severity) }}风险
              </span>
            </div>
          </div>

          <div class="card-body-row">
            <div class="desc-accent-bar"></div>
            <p class="card-description">{{ item.description || '现场安全隐患已由网格责任专员完成核实，并经实地核验闭环归档。' }}</p>
          </div>

          <div class="card-bottom-row">
            <div class="address-box" :title="item.address || '三明市区域'">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                <circle cx="12" cy="10" r="3"/>
              </svg>
              <span>{{ item.district ? item.district + ' · ' : '' }}{{ item.address || '三明市区域' }}</span>
            </div>
            <div class="card-time-action">
              <span class="time-text num-font">{{ formatDate(item.createTime) }}</span>
              <span class="card-hover-arrow">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                  <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
              </span>
            </div>
          </div>
        </article>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { resolveHazardList } from '../constants/hazardTaxonomy.js'

const router = useRouter()
const items = ref([])
const totalCount = ref(0)
const currentIndex = ref(0)
const isPaused = ref(false)
const stepWidth = ref(0)
const cardRefs = ref([])
let timer = null
let touchStartX = 0

const loopItems = computed(() => {
  if (items.value.length > 2) {
    return [...items.value, ...items.value]
  }
  return items.value
})

const trackStyle = computed(() => ({
  transform: `translateX(-${currentIndex.value * stepWidth.value}px)`,
  transition: 'transform 0.45s cubic-bezier(0.16, 1, 0.3, 1)'
}))

function formatSeverity(sev) {
  if (sev === 3 || sev === '高' || sev === 'HIGH') return '高'
  if (sev === 2 || sev === '中' || sev === 'MEDIUM') return '中'
  return '低'
}

function severityClass(sev) {
  const s = formatSeverity(sev)
  if (s === '高') return 'sev-high'
  if (s === '中') return 'sev-medium'
  return 'sev-low'
}

function formatDate(val) {
  if (!val) return ''
  return String(val).slice(0, 10)
}

function goToDetail(id) {
  if (id) {
    router.push(`/hazard/${id}`)
  } else {
    router.push('/hazard')
  }
}

function calcStepWidth() {
  nextTick(() => {
    const card = cardRefs.value?.[0]
    if (card) {
      const cardW = card.offsetWidth
      const track = card.parentElement
      const gap = track ? parseInt(window.getComputedStyle(track).gap) || 0 : 0
      stepWidth.value = cardW + gap
    }
  })
}

function nextSlide() {
  if (items.value.length <= 1) return
  currentIndex.value++
  if (currentIndex.value >= items.value.length) {
    setTimeout(() => {
      currentIndex.value = 0
    }, 460)
  }
}

function prevSlide() {
  if (items.value.length <= 1) return
  if (currentIndex.value > 0) {
    currentIndex.value--
  } else {
    currentIndex.value = items.value.length - 1
  }
}

function pause() {
  isPaused.value = true
}

function resume() {
  isPaused.value = false
}

function handleTouchStart(e) {
  touchStartX = e.touches[0].clientX
  pause()
}

function handleTouchEnd(e) {
  const touchEndX = e.changedTouches[0].clientX
  const diff = touchEndX - touchStartX
  if (Math.abs(diff) > 40) {
    if (diff < 0) {
      nextSlide()
    } else {
      prevSlide()
    }
  }
  resume()
}

async function fetchClosedHazards() {
  try {
    const res = await fetch('/api/hazard?status=3&current=1&size=8')
    const json = await res.json()
    if (json.code === 200 && json.data) {
      totalCount.value = json.data.total || 0
      items.value = json.data.records || []
      calcStepWidth()
    }
  } catch (err) {
    console.warn('获取已办结轮播数据失败', err)
  }
}

onMounted(() => {
  fetchClosedHazards()
  window.addEventListener('resize', calcStepWidth)
  timer = setInterval(() => {
    if (!isPaused.value) {
      nextSlide()
    }
  }, 3600)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('resize', calcStepWidth)
})
</script>

<style scoped>
.closed-hazards-carousel {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto 24px;
  padding: 14px 18px 16px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.92) 0%, rgba(248, 250, 252, 0.85) 100%);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(26, 115, 232, 0.1);
  border-radius: 20px;
  box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.03), 0 1px 3px rgba(26, 115, 232, 0.04);
  box-sizing: border-box;
  position: relative;
}

.carousel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 0 4px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 9px;
}

.pulse-green-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: #10b981;
  box-shadow: 0 0 10px rgba(16, 185, 129, 0.7);
  animation: pulse-dot 2.2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
}

.header-title {
  font-size: 13.5px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.2px;
}

.header-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.25);
  box-shadow: 0 1px 4px rgba(16, 185, 129, 0.1);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 7px;
}

.nav-arrow-btn {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  border: 1px solid rgba(0, 0, 0, 0.08);
  background: #ffffff;
  color: #64748b;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.nav-arrow-btn:hover:not(:disabled) {
  background: #eff6ff;
  color: #1a73e8;
  border-color: rgba(26, 115, 232, 0.3);
  transform: scale(1.08);
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.15);
}

.nav-arrow-btn:active:not(:disabled) {
  transform: scale(0.92);
}

.nav-arrow-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  box-shadow: none;
}

.view-all-link {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 11.5px;
  font-weight: 600;
  color: #1a73e8;
  text-decoration: none;
  padding: 3px 9px;
  border-radius: 9999px;
  background: rgba(26, 115, 232, 0.06);
  border: 1px solid rgba(26, 115, 232, 0.12);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.view-all-link:hover {
  background: #1a73e8;
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.25);
  transform: translateY(-1px);
}

/* 轮播卡片视口两端平滑渐隐遮罩 (Apple风跑马灯遮罩) */
.carousel-viewport {
  width: 100%;
  overflow: hidden;
  border-radius: 14px;
  mask-image: linear-gradient(to right, transparent 0%, black 28px, black calc(100% - 28px), transparent 100%);
  -webkit-mask-image: linear-gradient(to right, transparent 0%, black 28px, black calc(100% - 28px), transparent 100%);
  padding: 4px 0;
}

.carousel-track {
  display: flex;
  gap: 14px;
  width: 100%;
  will-change: transform;
}

/* 高阶微光轮播卡片 */
.carousel-card {
  flex: 0 0 calc((100% - 28px) / 3);
  min-width: calc((100% - 28px) / 3);
  padding: 14px 16px;
  border-radius: 16px;
  background: linear-gradient(145deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.94) 100%);
  border: 1px solid rgba(0, 0, 0, 0.07);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
  display: flex;
  flex-direction: column;
  gap: 10px;
  cursor: pointer;
  transition: all 0.24s cubic-bezier(0.16, 1, 0.3, 1);
  box-sizing: border-box;
  position: relative;
  overflow: hidden;
}

.carousel-card:hover {
  transform: translateY(-3px);
  border-color: rgba(26, 115, 232, 0.35);
  box-shadow: 0 8px 24px -2px rgba(26, 115, 232, 0.12), 0 2px 6px rgba(0, 0, 0, 0.03);
}

.carousel-card:active {
  transform: scale(0.98) translateY(-1px);
}

/* 印章微水印 */
.watermark-seal {
  position: absolute;
  top: -8px;
  right: -8px;
  color: #10b981;
  opacity: 0.06;
  pointer-events: none;
  transform: rotate(-12deg);
  transition: all 0.3s ease;
  z-index: 0;
}

.carousel-card:hover .watermark-seal {
  opacity: 0.12;
  transform: rotate(0deg) scale(1.05);
}

.card-top-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  position: relative;
  z-index: 1;
}

.badge-group {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.closed-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #ecfdf5 0%, #d1fae5 100%);
  color: #059669;
  border: 1px solid rgba(16, 185, 129, 0.25);
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.category-tag {
  font-size: 11px;
  font-weight: 600;
  color: #334155;
  background: #f1f5f9;
  border: 1px solid rgba(0, 0, 0, 0.05);
  padding: 2px 8px;
  border-radius: 9999px;
  white-space: normal;
  overflow-wrap: anywhere;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-top-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.hazard-num-pill {
  font-size: 10px;
  font-weight: 600;
  color: #94a3b8;
  background: rgba(0, 0, 0, 0.03);
  padding: 1px 5px;
  border-radius: 4px;
}

.severity-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  white-space: nowrap;
}

.card-body-row {
  display: flex;
  align-items: stretch;
  gap: 8px;
  position: relative;
  z-index: 1;
}

.desc-accent-bar {
  width: 3px;
  border-radius: 9999px;
  background: linear-gradient(180deg, #10b981 0%, #60a5fa 100%);
  flex-shrink: 0;
  opacity: 0.7;
}

.card-description {
  font-size: 12px;
  color: #334155;
  line-height: 1.55;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.card-bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding-top: 6px;
  border-top: 1px dashed rgba(0, 0, 0, 0.05);
  font-size: 11px;
  color: #64748b;
  position: relative;
  z-index: 1;
}

.address-box {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #64748b;
}

.address-box span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-time-action {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.time-text {
  color: #94a3b8;
  font-size: 10.5px;
}

.card-hover-arrow {
  color: #1a73e8;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translateX(-2px);
  opacity: 0.6;
  transition: all 0.2s ease;
}

.carousel-card:hover .card-hover-arrow {
  opacity: 1;
  transform: translateX(2px);
}

/* 响应式适配 */
@media (min-width: 1280px) {
  .carousel-card {
    flex: 0 0 calc((100% - 42px) / 4);
    min-width: calc((100% - 42px) / 4);
  }
}

@media (max-width: 1024px) and (min-width: 641px) {
  .carousel-card {
    flex: 0 0 calc((100% - 14px) / 2);
    min-width: calc((100% - 14px) / 2);
  }
  .closed-hazards-carousel {
    padding: 12px 14px;
    margin-bottom: 16px;
  }
  .header-title {
    font-size: 13px;
  }
}

@media (max-width: 640px) {
  .closed-hazards-carousel {
    padding: 10px 12px 12px;
    margin-bottom: 12px;
    border-radius: 16px;
  }
  .carousel-viewport {
    mask-image: none;
    -webkit-mask-image: none;
  }
  .carousel-header {
    margin-bottom: 8px;
  }
  .header-title {
    font-size: 12px;
  }
  .header-badge {
    font-size: 10px;
    padding: 1px 6px;
  }
  .carousel-card {
    flex: 0 0 100%;
    min-width: 100%;
    max-width: 100%;
    padding: 10px 12px;
    gap: 7px;
    border-radius: 12px;
  }
  .card-description {
    -webkit-line-clamp: 2;
    font-size: 11.5px;
    line-height: 1.45;
  }
  .card-top-row {
    gap: 6px;
  }
  .hazard-num-pill {
    display: none;
  }
  .closed-tag, .category-tag {
    font-size: 10.5px;
    padding: 1.5px 6px;
  }
}
</style>
