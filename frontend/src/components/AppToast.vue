<template>
  <transition name="toast-rise">
    <div v-if="text" class="app-toast" :class="type" role="status" aria-live="polite">
      <span class="toast-icon">{{ type === 'error' ? '⚠️' : '✅' }}</span>
      <span class="toast-text">{{ text }}</span>
    </div>
  </transition>
</template>

<script setup>
defineProps({
  text: { type: String, default: '' },
  type: { type: String, default: 'success' },
})
</script>

<style scoped>
.app-toast {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 4000;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: min(420px, calc(100vw - 48px));
  padding: 10px 16px;
  background: rgba(255, 255, 255, 0.94);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(37, 99, 235, 0.2);
  border-radius: 9999px;
  box-shadow: 0 10px 30px -4px rgba(15, 23, 42, 0.12), 0 2px 6px rgba(37, 99, 235, 0.08);
  font-size: 12.5px;
  color: #1e293b;
}
.app-toast.error {
  border-color: rgba(220, 38, 38, 0.24);
}
.toast-icon {
  font-size: 14px;
  line-height: 1;
}
.toast-text {
  line-height: 1.5;
}
.toast-rise-enter-active,
.toast-rise-leave-active {
  transition: opacity 0.24s ease, transform 0.24s cubic-bezier(0.22, 1, 0.36, 1);
}
.toast-rise-enter-from,
.toast-rise-leave-to {
  opacity: 0;
  transform: translateY(10px);
}
@media (max-width: 640px) {
  .app-toast {
    left: 16px;
    right: 16px;
    bottom: 84px;
    max-width: none;
    justify-content: center;
  }
}
</style>
