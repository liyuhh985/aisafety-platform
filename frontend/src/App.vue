<template>
  <div id="app-root" class="app-antigravity-bg min-h-screen text-slate-800">
    <div class="app-page-wrapper" :class="{ 'has-bottom-nav': shouldShowBottomNav }">
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <keep-alive include="HomeView">
            <component :is="Component" />
          </keep-alive>
        </transition>
      </router-view>
    </div>

    <!-- 移动端底部常驻导航栏：仅在真机移动触控小屏时挂载，PC 桌面端彻底不渲染 -->
    <BottomNav v-if="shouldShowBottomNav" />

    <!-- 桌面端大缩放友好提示温润微胶囊 (支持一键关闭并记住状态) -->
    <div v-if="showZoomHint" class="desktop-zoom-hint-toast animate-bounce-subtle" role="status">
      <div class="hint-content">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2.2">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          <line x1="11" y1="8" x2="11" y2="14"></line>
          <line x1="8" y1="11" x2="14" y2="11"></line>
        </svg>
        <span>检测到浏览器缩放比例偏大，按 <strong>Ctrl + 0</strong> 可恢复最佳高分屏视界</span>
      </div>
      <button class="hint-close-btn" @click="dismissZoomHint" title="我知道了" aria-label="关闭提示">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import BottomNav from './components/BottomNav.vue'

const shouldShowBottomNav = ref(false)
const showZoomHint = ref(false)

const checkDeviceAndViewport = () => {
  if (typeof window === 'undefined') return

  // 1. 是否具备 PC 精细鼠标指针特征 (W3C 标准规范)
  const isFinePointer = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches
  // 2. 是否属于真机移动触控屏幕 (无鼠标且带粗糙触控，或屏幕小于等于 640px)
  const isTouchDevice = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0)
  const isSmallScreen = window.innerWidth <= 640

  // 桌面端核心铁律：只要是有鼠标/精确指针的 PC 电脑，哪怕缩小窗口，也绝对不渲染移动端底栏！
  if (isFinePointer) {
    shouldShowBottomNav.value = false
  } else {
    // 仅在真实移动端触控且小屏设备上开启底栏
    shouldShowBottomNav.value = isSmallScreen || isTouchDevice
  }

  // 检测高分屏 PC 上是否处于异常巨型放大状态
  try {
    const isDismissed = sessionStorage.getItem('dismiss_zoom_hint') === '1'
    const screenPhysicalWidth = window.screen ? window.screen.width : 0
    // 如果物理屏幕是 1080p 或 2K 屏 (>= 1920)，但网页当前逻辑宽度跌破 960px，说明浏览器开启了 200% 以上超大 Zoom
    if (!isDismissed && isFinePointer && screenPhysicalWidth >= 1920 && window.innerWidth < 960) {
      showZoomHint.value = true
    } else {
      showZoomHint.value = false
    }
  } catch (e) {
    // 忽略异常
  }
}

const dismissZoomHint = () => {
  showZoomHint.value = false
  try {
    sessionStorage.setItem('dismiss_zoom_hint', '1')
  } catch (e) {}
}

let resizeHandler = null

onMounted(() => {
  checkDeviceAndViewport()
  resizeHandler = () => {
    checkDeviceAndViewport()
  }
  window.addEventListener('resize', resizeHandler, { passive: true })
})

onBeforeUnmount(() => {
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler)
  }
})
</script>

<style>
#app-root {
  width: 100%;
  min-height: 100vh;
  position: relative;
}

.app-page-wrapper {
  width: 100%;
  min-height: 100vh;
}

/* 仅在触控且小屏确实挂载了底栏时，预留底部安全边距 */
@media (pointer: coarse) and (max-width: 640px) {
  .app-page-wrapper.has-bottom-nav {
    padding-bottom: calc(72px + env(safe-area-inset-bottom, 0px));
  }
}

/* 桌面端高分屏巨型缩放温润提示浮条 */
.desktop-zoom-hint-toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 10000;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 9999px;
  box-shadow: 0 10px 30px -4px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(37, 99, 235, 0.08);
  font-size: 12.5px;
  color: #1e293b;
  pointer-events: auto;
  transition: all 0.3s cubic-bezier(0.22, 1, 0.36, 1);
}

.desktop-zoom-hint-toast .hint-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.desktop-zoom-hint-toast strong {
  color: #2563eb;
  font-weight: 600;
}

.desktop-zoom-hint-toast .hint-close-btn {
  background: none;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color 0.15s ease;
}

.desktop-zoom-hint-toast .hint-close-btn:hover {
  color: #475569;
}

/* 全局页面平滑呼吸转场动效 (对标 Open Study 弹性阻尼) */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.28s cubic-bezier(0.22, 1, 0.36, 1), transform 0.28s cubic-bezier(0.22, 1, 0.36, 1);
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
