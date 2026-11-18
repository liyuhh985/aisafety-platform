<template>
  <section class="carousel-section" :class="`accent-${accent}`">
    <div class="section-header">
      <div class="section-heading">
        <span class="section-icon" aria-hidden="true">
          <svg v-if="icon === 'document'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/></svg>
          <svg v-else-if="icon === 'alert'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="m10.3 3.3-8 14A2 2 0 0 0 4 20h16a2 2 0 0 0 1.7-2.7l-8-14a2 2 0 0 0-3.4 0Z"/><path d="M12 9v4M12 17h.01"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14.5 4h-5L8 7H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-1.5-3Z"/><circle cx="12" cy="13" r="3.5"/></svg>
        </span>
        <div class="heading-copy">
          <span class="section-eyebrow">{{ eyebrow }}</span>
          <h3 class="section-title">{{ title }}</h3>
        </div>
      </div>
      <span class="section-badge num-font">{{ items.length }}条</span>
    </div>

    <div v-if="!items.length" class="empty-state">暂无相关数据收录</div>
    <div v-else class="carousel-viewport" @mouseenter="pause" @mouseleave="resume">
      <div class="carousel-track" :style="trackStyle">
        <div
          v-for="(item, index) in loopItems"
          :key="index"
          class="carousel-card"
          ref="cardRefs"
        >
          <template v-if="type === 'document' || type === 'citizen'">
            <div class="card-top">
              <span class="card-label">{{ type === 'citizen' ? '市民线索' : '规范文书' }}</span>
              <span class="card-date num-font">{{ item.date }}</span>
            </div>
            <h4 class="card-title">{{ item.title }}</h4>
            <p class="card-source">{{ item.source || '三明市应急管理联动中心' }}</p>
          </template>

          <template v-else>
            <div class="card-top">
              <span class="severity-tag" :class="'sev-' + item.severity">{{ item.severity }}风险</span>
              <span class="card-date num-font">{{ item.date }}</span>
            </div>
            <h4 class="card-title">{{ item.hazardTypes }}</h4>
            <div class="card-foot">
              <span>国家典型案例库</span>
              <svg class="foot-arrow" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          </template>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'

const props = defineProps({
  title: String,
  eyebrow: String,
  type: String,
  icon: String,
  accent: { type: String, default: 'blue' },
  items: Array,
})

const current = ref(0)
const isPaused = ref(false)
const animating = ref(true)
const step = ref(0)
const cardRefs = ref([])
let timer = null

const loopItems = computed(() => props.items.length > 1 ? [...props.items, ...props.items] : props.items)

const trackStyle = computed(() => ({
  transform: `translateX(-${current.value * step.value}px)`,
  transition: animating.value ? 'transform 0.5s cubic-bezier(0.16, 1, 0.3, 1)' : 'none',
}))

function calcStep() {
  nextTick(() => {
    const card = cardRefs.value?.[0]
    if (card) {
      const cardW = card.offsetWidth
      const track = card.parentElement
      const gap = track ? parseInt(getComputedStyle(track).gap) || 0 : 0
      step.value = cardW + gap
    }
  })
}

watch(() => props.items.length, () => {
  current.value = 0
  animating.value = false
  calcStep()
}, { flush: 'post' })

function slide() {
  if (props.items.length <= 1) return
  current.value++
  animating.value = true
  if (current.value >= props.items.length) {
    setTimeout(() => {
      animating.value = false
      current.value = 0
    }, 520)
  }
}

function pause() { isPaused.value = true }
function resume() { isPaused.value = false }

onMounted(() => {
  calcStep()
  window.addEventListener('resize', calcStep)
  timer = setInterval(() => {
    if (!isPaused.value) slide()
  }, 3200)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('resize', calcStep)
})
</script>

<style scoped>
.carousel-section {
  width: 100%;
  max-width: 100%;
  padding: 16px;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.65);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 4px 18px -2px rgba(0, 0, 0, 0.4), inset 0 1px 0 0 rgba(255, 255, 255, 0.08);
  --section-accent: #38bdf8;
  overflow: hidden;
  box-sizing: border-box;
}

.accent-orange { --section-accent: #fb923c; }
.accent-green { --section-accent: #10b981; }

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 8px;
  width: 100%;
  min-width: 0;
}

.section-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}

.section-icon {
  width: 28px;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  color: var(--section-accent);
  background: color-mix(in srgb, var(--section-accent) 14%, transparent);
  border: 1px solid color-mix(in srgb, var(--section-accent) 24%, transparent);
  flex-shrink: 0;
}

.section-icon svg {
  width: 15px;
  height: 15px;
}

.heading-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.section-eyebrow {
  display: block;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  color: #64748b;
  text-transform: uppercase;
  margin-bottom: 1px;
}

.section-title {
  font-size: 14px;
  font-weight: 700;
  color: #f1f5f9;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.section-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #94a3b8;
  flex-shrink: 0;
}

.carousel-viewport {
  overflow: hidden;
  border-radius: 8px;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.carousel-track {
  display: flex;
  gap: 10px;
  width: 100%;
  will-change: transform;
}

.carousel-card {
  flex: 0 0 calc((100% - 20px) / 3);
  width: calc((100% - 20px) / 3);
  min-height: 110px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex-shrink: 0;
  border-radius: 8px;
  background: rgba(2, 6, 23, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.06);
  min-width: 0;
  overflow: hidden;
  box-sizing: border-box;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}

.card-label {
  color: var(--section-accent);
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
}

.card-date {
  font-size: 10px;
  color: #64748b;
  white-space: nowrap;
}

.card-title {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-all;
}

.card-source {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  overflow: hidden;
  font-size: 10px;
  color: #64748b;
  margin-top: auto;
  word-break: break-all;
}

.card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: auto;
  color: #64748b;
  font-size: 10px;
}

.foot-arrow {
  color: var(--section-accent);
  font-size: 12px;
}

.empty-state {
  min-height: 90px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 1px dashed rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  color: #64748b;
  font-size: 11px;
}

.severity-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
}

@media (max-width: 900px) {
  .carousel-card {
    flex: 0 0 calc((100% - 10px) / 2);
    width: calc((100% - 10px) / 2);
  }
}

/* 手机端严格贴合屏幕宽度：一个屏幕只容纳一张卡片，绝无超出溢出 */
@media (max-width: 640px) {
  .carousel-section {
    padding: 10px 8px !important;
    width: 100% !important;
    max-width: 100% !important;
  }
  .carousel-track {
    gap: 8px !important;
  }
  .carousel-card {
    flex: 0 0 100% !important;
    width: 100% !important;
    max-width: 100% !important;
    min-width: 100% !important;
  }
}
</style>