<template>
  <nav class="bottom-nav-bar" :class="{ 'is-hidden': isHidden }" aria-label="移动端底部导航栏">
    <router-link
      v-for="item in navItems"
      :key="item.path"
      :to="item.path"
      class="bottom-nav-item"
      :class="{ active: isActive(item.path) }"
    >
      <div class="nav-icon-wrapper">
        <component :is="item.icon" class="nav-icon" />
        <span v-if="isActive(item.path)" class="active-indicator-dot"></span>
      </div>
      <span class="nav-label">{{ item.label }}</span>
    </router-link>
  </nav>
</template>

<script setup>
import { h, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const isHidden = ref(false)

// 判断是否为文本输入类 DOM 元素
function isTextInput(el) {
  if (!el) return false
  const tag = el.tagName?.toLowerCase()
  if (tag === 'textarea') return true
  if (tag === 'input') {
    const type = (el.type || '').toLowerCase()
    return !['checkbox', 'radio', 'button', 'submit', 'file', 'image', 'reset'].includes(type)
  }
  return false
}

let onFocusInHandler = null
let onFocusOutHandler = null
let onViewportResizeHandler = null
let onCustomHideHandler = null
let onCustomShowHandler = null

// SVG 图标定义（保持与系统风格高度一致的 Antigravity 线性图标）
const HomeIcon = () => h('svg', {
  width: '20',
  height: '20',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '2.2',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
}, [
  h('path', { d: 'm3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z' }),
  h('polyline', { points: '9 22 9 12 15 12 15 22' })
])

const AnalysisIcon = () => h('svg', {
  width: '20',
  height: '20',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '2.2',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
}, [
  h('path', { d: 'M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z' }),
  h('circle', { cx: '12', cy: '13', r: '4' })
])

const HazardIcon = () => h('svg', {
  width: '20',
  height: '20',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '2.2',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
}, [
  h('path', { d: 'M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2' }),
  h('rect', { x: '8', y: '2', width: '8', height: '4', rx: '1', ry: '1' }),
  h('path', { d: 'm9 14 2 2 4-4' })
])

const MapIcon = () => h('svg', {
  width: '20',
  height: '20',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '2.2',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
}, [
  h('polygon', { points: '1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6' }),
  h('line', { x1: '8', y1: '2', x2: '8', y2: '18' }),
  h('line', { x1: '16', y1: '6', x2: '16', y2: '22' })
])

const HistoryIcon = () => h('svg', {
  width: '20',
  height: '20',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  'stroke-width': '2.2',
  'stroke-linecap': 'round',
  'stroke-linejoin': 'round'
}, [
  h('path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' }),
  h('polyline', { points: '14 2 14 8 20 8' }),
  h('line', { x1: '16', y1: '13', x2: '8', y2: '13' }),
  h('line', { x1: '16', y1: '17', x2: '8', y2: '17' }),
  h('polyline', { points: '10 9 9 9 8 9' })
])

const userRole = ref(localStorage.getItem('role') || '0')

onMounted(() => {
  userRole.value = localStorage.getItem('role') || '0'

  // 恢复导航栏显示
  const restoreNav = () => {
    isHidden.value = false
  }

  // 隐藏导航栏
  const hideNav = () => {
    isHidden.value = true
  }

  // 1. 全局焦点监听
  onFocusInHandler = (e) => {
    if (isTextInput(e.target)) {
      hideNav()
    }
  }

  onFocusOutHandler = () => {
    setTimeout(restoreNav, 120)
  }

  window.addEventListener('focusin', onFocusInHandler)
  window.addEventListener('focusout', onFocusOutHandler)

  // 2. 结合 visualViewport 监听软键盘真实弹起与收起
  // 核心：只要可视视口高度恢复正常（软键盘收起），无论当前焦点在何处，必须 100% 立即恢复导航栏！
  let maxSeenHeight = window.visualViewport ? window.visualViewport.height : window.innerHeight
  onViewportResizeHandler = () => {
    if (window.visualViewport) {
      const vvHeight = window.visualViewport.height
      if (vvHeight > maxSeenHeight) {
        maxSeenHeight = vvHeight
      }
      // 如果当前视口高度明显偏小（比历史最大高度少 130px 以上），说明软键盘正在显示
      if (vvHeight < maxSeenHeight - 130) {
        hideNav()
      } else {
        // 软键盘已退出，无条件恢复导航栏！彻底消除退出输入法后导航栏消失的问题
        restoreNav()
      }
    }
  }

  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', onViewportResizeHandler)
  }

  // 3. 点击或触摸页面非输入框区域，无条件恢复导航栏
  const onGlobalTouch = (e) => {
    if (!isTextInput(e.target)) {
      setTimeout(restoreNav, 100)
    }
  }
  window.addEventListener('pointerdown', onGlobalTouch, { passive: true })

  // 4. 用户滑动屏幕时，说明已退出打字状态，恢复导航栏
  const onGlobalScroll = () => {
    setTimeout(restoreNav, 100)
  }
  window.addEventListener('scroll', onGlobalScroll, { passive: true })

  // 5. 自定义事件监听
  onCustomHideHandler = () => { hideNav() }
  onCustomShowHandler = () => { restoreNav() }
  window.addEventListener('app-hide-bottom-nav', onCustomHideHandler)
  window.addEventListener('app-show-bottom-nav', onCustomShowHandler)
})

onBeforeUnmount(() => {
  if (onFocusInHandler) window.removeEventListener('focusin', onFocusInHandler)
  if (onFocusOutHandler) window.removeEventListener('focusout', onFocusOutHandler)
  if (window.visualViewport && onViewportResizeHandler) {
    window.visualViewport.removeEventListener('resize', onViewportResizeHandler)
  }
  if (onCustomHideHandler) window.removeEventListener('app-hide-bottom-nav', onCustomHideHandler)
  if (onCustomShowHandler) window.removeEventListener('app-show-bottom-nav', onCustomShowHandler)
})

const hazardNavLabel = computed(() => {
  if (userRole.value === '1') return '指挥'
  if (userRole.value === '2') return '处置'
  return '上报'
})

const navItems = computed(() => [
  { path: '/', label: '主控', icon: HomeIcon },
  { path: '/analysis', label: '研判', icon: AnalysisIcon },
  { path: '/hazard', label: hazardNavLabel.value, icon: HazardIcon },
  { path: '/map', label: '地图', icon: MapIcon },
  { path: '/history', label: '报告', icon: HistoryIcon }
])

const isActive = (itemPath) => {
  if (itemPath === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(itemPath)
}
</script>

<style scoped>
.bottom-nav-bar {
  display: none;
  position: fixed;
  bottom: calc(10px + env(safe-area-inset-bottom, 0px));
  left: 50% !important;
  transform: translateX(-50%) !important;
  width: calc(100% - 24px) !important;
  max-width: 440px !important;
  height: 54px;
  z-index: 999;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 9999px;
  box-shadow: 0 12px 32px -4px rgba(15, 23, 42, 0.12), 0 3px 8px rgba(0, 0, 0, 0.04);
  justify-content: space-around;
  align-items: center;
  padding: 0 8px;
  transition: transform 0.26s cubic-bezier(0.22, 1, 0.36, 1), opacity 0.22s ease, visibility 0.22s;
  will-change: transform, opacity;
}

/* 输入法打字/输入框聚焦时隐藏，平滑沉入底部 */
.bottom-nav-bar.is-hidden {
  transform: translate(-50%, calc(100% + 20px)) !important;
  opacity: 0 !important;
  pointer-events: none !important;
  visibility: hidden !important;
}

/* 仅在真实移动触控小屏设备 (<= 640px) 下启用底部悬浮胶囊 */
@media (pointer: coarse) and (max-width: 640px) {
  .bottom-nav-bar {
    display: flex;
  }
}

/* 具有鼠标/精细指针的高分屏桌面电脑，或平板与大屏幕，无条件绝对隐藏！ */
@media (hover: hover) and (pointer: fine) {
  .bottom-nav-bar {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
  }
}

@media (min-width: 641px) {
  .bottom-nav-bar {
    display: none !important;
    visibility: hidden !important;
    pointer-events: none !important;
  }
}

.bottom-nav-item {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 3px;
  height: 100%;
  text-decoration: none;
  color: #64748b;
  transition: all 0.18s cubic-bezier(0.16, 1, 0.3, 1);
  -webkit-tap-highlight-color: transparent;
  user-select: none;
  position: relative;
}

.bottom-nav-item:active {
  transform: scale(0.92);
}

.nav-icon-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 24px;
}

.nav-icon {
  transition: transform 0.2s ease, stroke 0.2s ease;
}

.nav-label {
  font-size: 11px;
  font-weight: 500;
  letter-spacing: -0.2px;
  transition: color 0.2s ease, font-weight 0.2s ease;
}

.bottom-nav-item.active {
  color: #1a73e8;
}

.bottom-nav-item.active .nav-icon {
  stroke: #1a73e8;
  transform: translateY(-1px);
}

.bottom-nav-item.active .nav-label {
  font-weight: 600;
  color: #1a73e8;
}

.active-indicator-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 5px;
  height: 5px;
  background-color: #1a73e8;
  border-radius: 50%;
}
</style>
