<template>
  <div class="map-page" ref="mapRootRef">
    <!-- 加载遮罩 -->
    <div v-if="loading" class="loading-overlay">
      <div class="loading-spinner"></div>
      <p class="loading-text">空间地理信息与隐患工单点位同步中...</p>
    </div>

    <!-- 错误遮罩 -->
    <div v-if="error" class="error-overlay">
      <div class="error-content">
        <p class="error-icon">⚠️</p>
        <p class="error-text">{{ error }}</p>
        <button class="btn-pill btn-pill-primary mt-3" @click="loadDataAndInit">重新加载</button>
      </div>
    </div>

    <!-- 高德地图挂载容器 -->
    <div id="amap-container" class="map-container"></div>

    <!-- 顶部导航条 (Antigravity 白底磨砂) -->
    <header class="top-bar">
      <div class="top-bar-left" @click="goHome" title="返回主控中心">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/>
        </svg>
        <span>返回主控</span>
      </div>

      <div class="top-bar-center">
        <span class="pulse-status-dot"></span>
        <span class="title-text title-full">三明市城市安全隐患空间态势地图</span>
        <span class="title-text title-short">空间态势地图</span>
        <span class="role-identity-pill">{{ roleTitle }}</span>
      </div>

      <div class="top-bar-right">
        <!-- 底图风格切换选择器 -->
        <div class="map-theme-switcher">
          <button
            v-for="th in mapThemes"
            :key="th.val"
            class="theme-btn"
            :class="{ active: currentTheme === th.val }"
            @click="switchTheme(th.val)"
            :title="th.label"
          >
            <span class="theme-label-full">{{ th.label }}</span>
            <span class="theme-label-short">{{ th.shortLabel }}</span>
          </button>
        </div>

        <router-link to="/hazard" class="task-link-pill">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
            <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
          </svg>
          <span>工单处置</span>
        </router-link>
      </div>
    </header>

    <!-- 筛选栏收起后的浮动开启微胶囊 -->
    <transition name="fade-pop">
      <button
        v-if="filterCollapsed"
        type="button"
        class="filter-open-pill glass-card"
        @click="filterCollapsed = false"
        title="展开隐患状态与分类筛选栏"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
        </svg>
        <span class="open-label">隐患筛选</span>
        <span class="open-summary-chip">{{ currentFilterSummary }}</span>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>
    </transition>

    <!-- 复合筛选器浮层 (类别 + 状态) -->
    <transition name="fade-slide">
      <div v-if="!filterCollapsed" class="filter-floating-card glass-card">
        <!-- 筛选栏顶部控制栏 -->
        <div class="filter-card-header">
          <div class="filter-card-title">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
            </svg>
            <span>工单空间筛选</span>
            <span v-if="hasActiveFilter" class="active-filter-badge">已筛选</span>
          </div>
          <div class="filter-card-actions">
            <button
              v-if="hasActiveFilter"
              type="button"
              class="filter-reset-btn"
              @click="resetFilters"
              title="重置为全部"
            >
              重置
            </button>
            <button
              type="button"
              class="filter-collapse-btn"
              @click="filterCollapsed = true"
              title="收起筛选栏，释放地图空间"
              aria-label="收起筛选栏"
            >
              <span class="collapse-text">收起</span>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <polyline points="18 15 12 9 6 15"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- 状态维度筛选 (五态支持) -->
        <div class="filter-row">
          <span class="row-label">处置状态：</span>
          <div class="chips-group touch-scroll-x no-scrollbar">
            <button
              v-for="st in statusOptions"
              :key="st.val"
              class="filter-chip"
              :class="{ active: filterStatus === st.val }"
              @click="setFilterStatus(st.val)"
            >
              <span class="status-indicator" :style="{ background: st.color }"></span>
              <span>{{ st.label }}</span>
              <span class="badge-num num-font">{{ countByStatus(st.val) }}</span>
            </button>
          </div>
        </div>

        <div class="filter-sep"></div>

        <!-- 类别维度筛选 (标准一级大类) -->
        <div class="filter-row">
          <span class="row-label">隐患分类：</span>
          <div class="chips-group touch-scroll-x no-scrollbar">
            <button
              v-for="cat in categoryOptions"
              :key="cat.code"
              class="filter-chip"
              :class="{ active: filterCategoryCode === cat.code }"
              @click="setFilterCategory(cat.code)"
            >
              <span>{{ cat.label }}</span>
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 底部工单抽屉呼出按钮 -->
    <button class="panel-toggle-capsule btn-pill" @click="showPanel = !showPanel">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/>
        <line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/>
      </svg>
      <span>{{ showPanel ? '收起隐患点位列表' : `查看工单点位 (${displayHazards.length})` }}</span>
    </button>

    <!-- 底部抽屉面板 -->
    <transition name="slide-up">
      <div v-if="showPanel" class="hazard-drawer glass-card">
        <div class="drawer-header">
          <div class="header-info">
            <span class="drawer-title">空间筛选点位清单</span>
            <span class="drawer-meta">共筛选出 {{ displayHazards.length }} 个需要处置的隐患任务</span>
          </div>
          <button class="drawer-close-btn" @click="showPanel = false">✕</button>
        </div>

        <div class="drawer-body">
          <div v-if="!displayHazards.length" class="drawer-empty">
            <span>当前筛选条件下暂无点位</span>
          </div>

          <div
            v-for="item in displayHazards"
            :key="item.id"
            class="drawer-item"
            :class="{ active: activeId === item.id }"
            @click="flyTo(item)"
          >
            <div class="item-status-tag" :class="'status-' + item.status">
              {{ formatStatus(item.status) }}
            </div>
            <div class="item-content">
              <div class="item-title-row">
                <span
                  v-for="cat in resolveHazardList(item.hazardTypes)"
                  :key="`${cat.majorCode}/${cat.subcategoryCode}`"
                  class="item-type-badge"
                >{{ cat.displayText }}</span>
              </div>
              <span class="item-addr">📍 {{ item.district || '三明市辖区' }}</span>
            </div>
            <div class="item-tail">
              <button class="locate-btn" @click.stop="flyTo(item)">定位</button>
              <button class="locate-btn" @click.stop="openDetail(item.id)">详情</button>
            </div>
          </div>
        </div>
      </div>
    </transition>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { HAZARD_TAXONOMY, resolveHazardList, matchHazardFilter } from '../constants/hazardTaxonomy.js'

const router = useRouter()
const mapRootRef = ref(null)

const SANMING = [117.635, 26.265]
const userRole = ref(localStorage.getItem('role') || '0')

const loading = ref(true)
const error = ref('')
const hazards = ref([])
const showPanel = ref(false)
const activeId = ref(null)

const filterStatus = ref(-1) // -1: 全部
const filterCategoryCode = ref('all') // 'all' 或一级大类代码
const filterCollapsed = ref(false) // 筛选卡片收起/展开控制

const hasActiveFilter = computed(() => {
  return filterStatus.value !== -1 || filterCategoryCode.value !== 'all'
})

const currentFilterSummary = computed(() => {
  const currentSt = statusOptions.find(s => s.val === filterStatus.value)
  const currentCat = categoryOptions.value.find(c => c.code === filterCategoryCode.value)

  const stText = (currentSt && currentSt.val !== -1) ? currentSt.label : ''
  const catText = (currentCat && currentCat.code !== 'all') ? currentCat.label : ''

  if (stText && catText) {
    return `${stText}·${catText} (${displayHazards.value.length})`
  } else if (stText) {
    return `${stText} (${displayHazards.value.length})`
  } else if (catText) {
    return `${catText} (${displayHazards.value.length})`
  } else {
    return `全部 (${hazards.value.length})`
  }
})

function resetFilters() {
  filterStatus.value = -1
  filterCategoryCode.value = 'all'
  renderMarkers()
}

const categoryOptions = computed(() => [
  { code: 'all', label: '全部' },
  ...HAZARD_TAXONOMY.map(m => ({ code: m.code, label: m.label }))
])


let mapInstance = null
let markers = []
let infoWindow = null

// 五态完整定义
const statusOptions = [
  { val: -1, label: '全部', color: '#64748b' },
  { val: 0, label: '待处理', color: '#64748b' },
  { val: 1, label: '已接单', color: '#1a73e8' },
  { val: 2, label: '整改中', color: '#ea580c' },
  { val: 3, label: '待验收/已办结', color: '#d97706' },
  { val: 4, label: '已驳回', color: '#dc2626' },
]

const currentTheme = ref('amap://styles/macaron')
const mapThemes = [
  { val: 'amap://styles/macaron', label: '清新全彩', shortLabel: '全彩' },
  { val: 'amap://styles/whitesmoke', label: '极简浅白', shortLabel: '浅白' },
  { val: 'amap://styles/dark', label: '深黑科技', shortLabel: '深黑' },
]

function switchTheme(styleVal) {
  currentTheme.value = styleVal
  if (mapInstance) {
    mapInstance.setMapStyle(styleVal)
  }
}

const roleTitle = computed(() => {
  if (userRole.value === '1') return '管理员指挥视图'
  if (userRole.value === '2') return '处置责任人视图'
  return '市民巡查视图'
})

function goHome() {
  router.push('/')
}

function formatStatus(status) {
  const map = { 0: '待处理', 1: '已接单', 2: '整改中', 3: '已完成', 4: '已驳回' }
  return map[status] || '待处理'
}

function countByStatus(val) {
  if (val === -1) return hazards.value.length
  return hazards.value.filter(h => h.status === val).length
}

const displayHazards = computed(() => {
  return hazards.value.filter(h => {
    if (filterStatus.value !== -1 && h.status !== filterStatus.value) {
      return false
    }
    if (filterCategoryCode.value !== 'all') {
      if (!matchHazardFilter(h.hazardTypes, filterCategoryCode.value)) return false
    }
    return true
  })
})

function setFilterStatus(val) {
  filterStatus.value = val
  renderMarkers()
}

function setFilterCategory(catCode) {
  filterCategoryCode.value = catCode
  renderMarkers()
}

// 动态载入高德地图 SDK
function loadAMap() {
  return new Promise((resolve, reject) => {
    if (window.AMap) return resolve(window.AMap)
    const amapKey = (import.meta.env.VITE_AMAP_KEY || '').trim()
    const amapSecurityCode = (import.meta.env.VITE_AMAP_SECURITY_CODE || '').trim()
    if (!amapKey) {
      reject(new Error('未配置 VITE_AMAP_KEY'))
      return
    }
    if (amapSecurityCode) {
      window._AMapSecurityConfig = { securityJsCode: amapSecurityCode }
    }
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(amapKey)}&plugin=AMap.ToolBar,AMap.Scale,AMap.InfoWindow`
    script.async = true
    script.onload = () => {
      setTimeout(() => {
        if (window.AMap) resolve(window.AMap)
        else reject(new Error('AMap 实例未就绪'))
      }, 150)
    }
    script.onerror = () => reject(new Error('高德地图脚本加载失败'))
    document.head.appendChild(script)
  })
}

// 匿名公开地图：接口只返回 id/经纬度/类别/状态/区县白名单字段。
async function loadHazards() {
  const res = await fetch('/api/hazard/map?limit=100')
  const json = await res.json().catch(() => ({}))
  if (!res.ok || json.code !== 200) {
    throw new Error(json.message || '加载地图点位失败')
  }

  const list = Array.isArray(json.data) ? json.data : []
  hazards.value = list.map(item => ({
    id: Number(item.id),
    hazardTypes: item.hazardTypes,
    status: item.status != null ? item.status : 0,
    district: item.district,
    lng: Number(item.longitude) || 117.635,
    lat: Number(item.latitude) || 26.265,
  }))
}

// 清理图面标注
function clearMarkers() {
  markers.forEach(m => m.setMap(null))
  markers = []
  if (infoWindow) {
    infoWindow.close()
    infoWindow = null
  }
}

// 渲染 Marker 点位 (五态色彩)
function renderMarkers() {
  if (!mapInstance || !window.AMap) return
  clearMarkers()

  const colorMap = {
    0: '#64748b', // 待处理 灰
    1: '#1a73e8', // 已接单 蓝
    2: '#ea580c', // 整改中 橙
    3: '#16a34a', // 已完成 绿
    4: '#dc2626', // 已驳回 红
  }

  const list = displayHazards.value
  list.forEach(h => {
    const color = colorMap[h.status] || '#64748b'

    const markerContent = document.createElement('div')
    markerContent.className = 'custom-amap-marker'
    markerContent.innerHTML = `
      <div style="
        width: 32px; height: 32px; border-radius: 50%;
        background: #ffffff; border: 2.5px solid ${color};
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 4px 14px rgba(0,0,0,0.18); cursor: pointer;
        transition: transform 0.2s;
      ">
        <div style="width: 10px; height: 10px; border-radius: 50%; background: ${color};"></div>
      </div>
    `
    markerContent.addEventListener('mouseenter', () => {
      markerContent.style.transform = 'scale(1.2)'
    })
    markerContent.addEventListener('mouseleave', () => {
      markerContent.style.transform = 'scale(1)'
    })

    const marker = new window.AMap.Marker({
      position: [h.lng, h.lat],
      content: markerContent,
      offset: new window.AMap.Pixel(-16, -16),
      title: h.district || '隐患点位',
    })

    marker.on('click', () => {
      activeId.value = h.id
      showInfo(h)
    })

    marker.setMap(mapInstance)
    markers.push(marker)
  })
  if (markers.length > 0) {
    mapInstance.setFitView(markers, false, [80, 40, 80, 40])
  }
}

function escapeHtml(str) {
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// 公开信息窗只展示白名单字段，不拼接图片、描述、精确地址或处理人。
function showInfo(h) {
  if (!mapInstance || !window.AMap) return
  activeId.value = h.id

  const categoryBadges = resolveHazardList(h.hazardTypes)
    .map(cat => `<span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;background:#f1f5f9;color:#334155;white-space:nowrap;">${escapeHtml(cat.displayText)}</span>`)
    .join('') || '<span style="font-size:11px;font-weight:700;padding:2px 8px;border-radius:4px;background:#f1f5f9;color:#334155;">未定类别</span>'
  const statusName = escapeHtml(formatStatus(h.status))
  const district = escapeHtml(h.district || '三明市辖区')
  const safeId = Number(h.id)

  const html = `
    <div class="amap-info-card" style="
      width: 280px; background: #ffffff; border-radius: 16px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.15); border: 1px solid rgba(0,0,0,0.08);
      overflow: hidden; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    ">
      <div style="padding: 14px;">
        <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:10px;">
          <span style="font-size:11px; font-weight:700; padding:2px 8px; border-radius:9999px; background:#eff6ff; color:#1a73e8;">
            ${statusName}
          </span>
          <div style="display:flex; gap:4px; flex-wrap:wrap; justify-content:flex-end; min-width:0;">
            ${categoryBadges}
          </div>
        </div>
        <div style="font-size:12px; color:#64748b; margin-bottom:12px;">📍 ${district}</div>
        <div style="display:flex; justify-content:flex-end; padding-top:10px; border-top:1px solid #f1f5f9;">
          <button class="info-flow-btn" onclick="window.__handleMapDetail(${safeId})" style="background:#1a73e8; color:#fff;">
            查看工单详情
          </button>
        </div>
      </div>
    </div>
  `

  infoWindow = new window.AMap.InfoWindow({
    content: html,
    offset: new window.AMap.Pixel(0, -20),
    closeWhenClickMap: true,
    isCustom: true,
  })
  infoWindow.open(mapInstance, [h.lng, h.lat])
}
function flyTo(h) {
  if (mapInstance) {
    mapInstance.setCenter([h.lng, h.lat])
    mapInstance.setZoom(15)
    showInfo(h)
  }
}

// 公开地图不执行状态流转；详情页统一处理登录和权限。
window.__handleMapDetail = (id) => {
  openDetail(id)
}

function openDetail(id) {
  const target = `/hazard/${Number(id)}`
  if (!localStorage.getItem('token')) {
    router.push('/login?redirect=' + encodeURIComponent(target))
    return
  }
  router.push(target)
}
async function loadDataAndInit() {
  loading.value = true
  error.value = ''
  try {
    await loadHazards()
    const AMap = await loadAMap()
    const map = new AMap.Map('amap-container', {
      center: SANMING,
      zoom: 13,
      mapStyle: currentTheme.value,
      showIndoorMap: false,
      expandZoomRange: true,
      zooms: [10, 18],
    })
    map.addControl(new AMap.ToolBar({ position: 'RB' }))
    map.addControl(new AMap.Scale())
    mapInstance = map
    loading.value = false
    map.on('complete', () => renderMarkers())
  } catch (e) {
    console.error('初始化地图失败', e)
    error.value = '地图服务连接受阻：' + e.message
    loading.value = false
  }
}

onMounted(loadDataAndInit)

onBeforeUnmount(() => {
  clearMarkers()
  if (mapInstance) {
    mapInstance.destroy()
    mapInstance = null
  }
  delete window.__handleMapDetail
})
</script>

<style scoped>
.map-page {
  position: relative;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background: #f8fafd;
}
.map-container {
  width: 100%;
  height: 100%;
}

/* 顶部导航条 */
.top-bar {
  position: absolute;
  top: 16px;
  left: 20px;
  right: 20px;
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 9999px;
  box-shadow: 0 4px 20px -2px rgba(0, 0, 0, 0.08);
  z-index: 1000;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 9999px;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.top-bar-left:hover {
  background: #f1f5f9;
  color: #1a73e8;
  transform: translateY(-1px);
}

.top-bar-center {
  display: flex;
  align-items: center;
  gap: 8px;
}
.pulse-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #16a34a;
  box-shadow: 0 0 0 3px rgba(22, 163, 74, 0.2);
  animation: pulse-ring 2s infinite;
}
@keyframes pulse-ring {
  0% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.4); }
  70% { box-shadow: 0 0 0 6px rgba(22, 163, 74, 0); }
  100% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); }
}
.title-text {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
}
.role-identity-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  border: 1px solid #bfdbfe;
}

.top-bar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}
.map-theme-switcher {
  display: flex;
  background: #f1f5f9;
  padding: 2px;
  border-radius: 9999px;
}
.theme-btn {
  border: none;
  background: transparent;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.15s;
}
.theme-btn.active {
  background: #ffffff;
  color: #0f172a;
  box-shadow: 0 1px 3px rgba(0,0,0,0.1);
}
.task-link-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  background: #1a73e8;
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  border-radius: 9999px;
  text-decoration: none;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.3);
}
.task-link-pill:hover {
  background: #1557b0;
  transform: translateY(-1px);
}

.title-short {
  display: none;
}
.theme-label-short {
  display: none;
}

/* 筛选栏收起后的浮动开启微胶囊 */
.filter-open-pill {
  position: absolute;
  top: 80px;
  left: 20px;
  z-index: 1000;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 14px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 9999px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  color: #1e293b;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.filter-open-pill:hover {
  background: #ffffff;
  color: #1a73e8;
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.12);
}
.open-label {
  color: #475569;
}
.open-summary-chip {
  padding: 2px 8px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  font-size: 11px;
  font-weight: 600;
  border: 1px solid #bfdbfe;
}

/* 浮动筛选器卡片 */
.filter-floating-card {
  position: absolute;
  top: 80px;
  left: 20px;
  z-index: 1000;
  padding: 12px 16px;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 18px;
  box-shadow: 0 8px 30px -4px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 460px;
}

/* 筛选卡片顶部控制栏 */
.filter-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 8px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
  margin-bottom: 2px;
}
.filter-card-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 700;
  color: #1e293b;
}
.active-filter-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  border: 1px solid #bfdbfe;
}
.filter-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.filter-reset-btn {
  background: transparent;
  border: none;
  font-size: 11px;
  color: #64748b;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}
.filter-reset-btn:hover {
  background: #f1f5f9;
  color: #1a73e8;
}
.filter-collapse-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.15s;
}
.filter-collapse-btn:hover {
  background: #e2e8f0;
  color: #0f172a;
}

/* 折叠展开动效过渡 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}
.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.98);
}

.fade-pop-enter-active,
.fade-pop-leave-active {
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.fade-pop-enter-from,
.fade-pop-leave-to {
  opacity: 0;
  transform: scale(0.9);
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.row-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
}
.chips-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 9999px;
  background: #f1f5f9;
  border: 1px solid transparent;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.filter-chip:hover {
  background: #e2e8f0;
}
.filter-chip.active {
  background: #ffffff;
  border-color: #1a73e8;
  color: #1a73e8;
  box-shadow: 0 2px 6px rgba(26, 115, 232, 0.15);
}
.status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.badge-num {
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 9999px;
  background: rgba(0, 0, 0, 0.06);
}
.filter-chip.active .badge-num {
  background: #eff6ff;
  color: #1a73e8;
}
.filter-sep {
  height: 1px;
  background: rgba(0, 0, 0, 0.06);
  margin: 0 -4px;
}

/* 底部列表呼出胶囊 */
.panel-toggle-capsule {
  position: absolute;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 22px;
  border-radius: 9999px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.12);
  color: #0f172a;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.panel-toggle-capsule:hover {
  transform: translateX(-50%) translateY(-2px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.16);
  color: #1a73e8;
}

/* 底部抽屉面板 */
.hazard-drawer {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  max-height: 420px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 24px 24px 0 0;
  box-shadow: 0 -10px 40px rgba(0, 0, 0, 0.12);
  z-index: 1100;
  display: flex;
  flex-direction: column;
}
.drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}
.drawer-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}
.drawer-meta {
  font-size: 12px;
  color: #64748b;
  margin-left: 10px;
}
.drawer-close-btn {
  background: transparent;
  border: none;
  font-size: 16px;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 50%;
  transition: all 0.15s;
}
.drawer-close-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.drawer-empty {
  text-align: center;
  padding: 32px;
  color: #94a3b8;
  font-size: 13px;
}
.drawer-item {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
  cursor: pointer;
  transition: all 0.15s;
}
.drawer-item:hover {
  background: #f8fafc;
  border-color: #1a73e8;
}
.drawer-item.active {
  background: #eff6ff;
  border-color: #93c5fd;
}

.item-status-tag {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 6px;
  flex-shrink: 0;
}
.status-0 { background: #f1f5f9; color: #475569; }
.status-1 { background: #eff6ff; color: #1d4ed8; }
.status-2 { background: #fff7ed; color: #c2410c; }
.status-3 { background: #f0fdf4; color: #15803d; }
.status-4 { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }

.item-content {
  flex: 1;
  min-width: 0;
}
.item-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.item-type-badge {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}
.item-code {
  font-size: 10px;
  color: #94a3b8;
}
.item-handler-chip {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  background: #eff6ff;
  color: #1a73e8;
  font-weight: 600;
}
.item-desc {
  font-size: 12px;
  color: #475569;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 2px;
}
.item-addr {
  font-size: 11px;
  color: #64748b;
}

.locate-btn {
  padding: 4px 12px;
  border-radius: 9999px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #1a73e8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

/* 模态框设计 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  z-index: 2500;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}
.modal-box {
  width: 100%;
  max-width: 460px;
  background: #ffffff;
  border-radius: 20px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(0, 0, 0, 0.08);
  overflow: hidden;
  animation: modal-pop 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
@keyframes modal-pop {
  from { opacity: 0; transform: scale(0.95); }
  to { opacity: 1; transform: scale(1); }
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #f1f5f9;
}
.modal-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.modal-icon {
  font-size: 18px;
}
.modal-title {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  margin: 0;
}
.modal-close-btn {
  background: transparent;
  border: none;
  font-size: 16px;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
}
.modal-body {
  padding: 20px;
}
.modal-hint {
  font-size: 13px;
  color: #475569;
  margin-bottom: 14px;
}
.highlight-id {
  color: #1a73e8;
  font-weight: 700;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
}
.form-input, .form-textarea {
  width: 100%;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid #cbd5e1;
  background: #f8fafc;
  font-size: 13px;
  color: #0f172a;
  transition: all 0.2s;
  box-sizing: border-box;
}
.form-input:focus, .form-textarea:focus {
  outline: none;
  border-color: #1a73e8;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.15);
}
.quick-pick-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
}
.quick-label {
  font-size: 11px;
  color: #64748b;
}
.quick-pick-btn {
  padding: 4px 10px;
  border-radius: 9999px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #334155;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.quick-pick-btn.selected {
  background: #eff6ff;
  border-color: #1a73e8;
  color: #1a73e8;
}
.review-type-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.radio-label {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}
.radio-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  border-radius: 8px;
  flex: 1;
}
.badge-reject {
  background: #fef2f2;
  color: #dc2626;
  border: 1px solid #fecaca;
}
.badge-pass {
  background: #f0fdf4;
  color: #16a34a;
  border: 1px solid #bbf7d0;
}
.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  background: #f8fafc;
  border-top: 1px solid #f1f5f9;
}
.modal-btn {
  padding: 8px 18px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.15s;
}
.modal-btn.cancel {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  color: #475569;
}
.modal-btn.confirm {
  background: #1a73e8;
  color: #ffffff;
}
.modal-btn.confirm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.modal-btn.confirm-reject {
  background: #dc2626;
  color: #ffffff;
}
.modal-btn.confirm-pass {
  background: #16a34a;
  color: #ffffff;
}

/* 抽屉动画 */
.slide-up-enter-active, .slide-up-leave-active {
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-up-enter-from, .slide-up-leave-to {
  transform: translateY(100%);
}

/* 加载与错误 */
.loading-overlay, .error-overlay {
  position: absolute; inset: 0; z-index: 2000;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: rgba(248, 250, 253, 0.9);
}
.loading-spinner {
  width: 32px; height: 32px;
  border: 3px solid #dbeafe;
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { margin-top: 12px; font-size: 13px; color: #475569; font-weight: 500; }

.error-content {
  text-align: center; padding: 24px; background: #ffffff;
  border-radius: 16px; border: 1px solid #fecaca; box-shadow: 0 10px 30px rgba(0,0,0,0.06);
}
.error-icon { font-size: 32px; margin-bottom: 8px; }
.error-text { font-size: 14px; color: #dc2626; }

/* 弹窗全局修饰 */
:global(.amap-info-close) { display: none !important; }
:global(.amap-info-contentContainer) { border-radius: 16px !important; overflow: hidden !important; }
:global(.amap-info-outer) { background: transparent !important; border: none !important; box-shadow: none !important; }
:global(.info-flow-btn) {
  padding: 4px 12px; border-radius: 9999px; border: none; font-size: 11px; font-weight: 700; cursor: pointer; transition: all 0.2s;
}
:global(.info-flow-btn:hover) { opacity: 0.9; transform: translateY(-1px); }

/* 移动端响应式 */
@media (max-width: 767px) {
  .top-bar {
    top: 8px;
    left: 8px;
    right: 8px;
    height: 44px;
    padding: 0 10px;
    box-sizing: border-box;
  }
  .top-bar-left,
  .task-link-pill {
    display: none !important; /* 由移动端底部导航承载 */
  }
  .top-bar-center {
    font-size: 13px;
    gap: 6px;
  }
  .role-identity-pill {
    display: none;
  }
  .title-full {
    display: none;
  }
  .title-short {
    display: inline;
  }

  /* 地图风格切换器在移动端紧凑排布，彻底消除与筛选框重叠 */
  .map-theme-switcher {
    padding: 2px;
  }
  .theme-label-full {
    display: none;
  }
  .theme-label-short {
    display: inline;
  }
  .theme-btn {
    padding: 3px 7px;
    font-size: 11px;
  }

  /* 浮动筛选器卡片与开启胶囊定位：严格计算在 top-bar 下方，留足间距，彻底消除重叠 */
  .filter-floating-card {
    top: 60px;
    left: 8px;
    right: 8px;
    max-width: none;
    padding: 10px 12px;
    border-radius: 14px;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
  }
  .filter-open-pill {
    top: 60px;
    left: 8px;
    padding: 5px 12px;
    font-size: 11px;
  }

  .chips-group {
    overflow-x: auto;
    white-space: nowrap;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    flex-wrap: nowrap;
    padding-bottom: 2px;
  }
  .chips-group::-webkit-scrollbar {
    display: none;
  }
  .filter-chip {
    flex-shrink: 0;
    padding: 3px 8px;
    font-size: 11px;
  }

  /* 底部抽屉呼出胶囊与抽屉，避让底部导航栏 */
  .panel-toggle-capsule {
    bottom: calc(66px + env(safe-area-inset-bottom, 0px)) !important;
    padding: 6px 14px;
    font-size: 12px;
  }
  .hazard-drawer {
    bottom: calc(56px + env(safe-area-inset-bottom, 0px)) !important;
    max-height: 55vh;
  }
}
</style>
