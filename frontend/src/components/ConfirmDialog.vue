<template>
  <transition name="dialog-fade">
    <div v-if="visible" class="dialog-mask" @click.self="onCancel">
      <div class="dialog-box" role="dialog" aria-modal="true" :aria-label="title">
        <div class="dialog-header">
          <div class="dialog-title-row">
            <span class="dialog-icon">{{ icon }}</span>
            <h3 class="dialog-title">{{ title }}</h3>
          </div>
          <button class="dialog-close" type="button" aria-label="关闭" @click="onCancel">✕</button>
        </div>
        <div class="dialog-body">
          <p class="dialog-message">{{ message }}</p>
          <p v-if="detail" class="dialog-detail">{{ detail }}</p>
          <p v-if="error" class="dialog-error">{{ error }}</p>
        </div>
        <div class="dialog-footer">
          <button class="dialog-btn cancel" type="button" :disabled="loading" @click="onCancel">
            {{ cancelText }}
          </button>
          <button
            class="dialog-btn confirm"
            :class="{ danger }"
            type="button"
            :disabled="loading"
            @click="$emit('confirm')"
          >
            {{ loading ? loadingText : confirmText }}
          </button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
const props = defineProps({
  visible: { type: Boolean, default: false },
  title: { type: String, default: '请确认' },
  message: { type: String, default: '' },
  detail: { type: String, default: '' },
  error: { type: String, default: '' },
  icon: { type: String, default: '⚠️' },
  confirmText: { type: String, default: '确定' },
  cancelText: { type: String, default: '取消' },
  loadingText: { type: String, default: '处理中...' },
  loading: { type: Boolean, default: false },
  danger: { type: Boolean, default: false },
})

const emit = defineEmits(['confirm', 'cancel'])

function onCancel() {
  if (props.loading) return
  emit('cancel')
}
</script>

<style scoped>
.dialog-mask {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}
.dialog-box {
  width: 100%;
  max-width: 420px;
  padding: 24px;
  background: #ffffff;
  border-radius: 20px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.16);
}
.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.dialog-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dialog-icon {
  font-size: 18px;
  line-height: 1;
}
.dialog-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
}
.dialog-close {
  background: transparent;
  border: none;
  font-size: 16px;
  color: #94a3b8;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 6px;
  transition: color 0.15s ease;
}
.dialog-close:hover {
  color: #475569;
}
.dialog-message {
  margin: 0;
  font-size: 13.5px;
  line-height: 1.7;
  color: #334155;
}
.dialog-detail {
  margin: 8px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: #64748b;
}
.dialog-error {
  margin: 12px 0 0;
  padding: 8px 12px;
  font-size: 12.5px;
  line-height: 1.6;
  color: #b91c1c;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 10px;
}
.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
.dialog-btn {
  padding: 8px 18px;
  border: none;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: filter 0.15s ease, opacity 0.15s ease;
}
.dialog-btn:hover:not(:disabled) {
  filter: brightness(0.95);
}
.dialog-btn.cancel {
  background: #f1f5f9;
  color: #475569;
}
.dialog-btn.confirm {
  background: #1a73e8;
  color: #ffffff;
}
.dialog-btn.confirm.danger {
  background: #dc2626;
}
.dialog-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.2s ease;
}
.dialog-fade-enter-active .dialog-box,
.dialog-fade-leave-active .dialog-box {
  transition: transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}
.dialog-fade-enter-from .dialog-box,
.dialog-fade-leave-to .dialog-box {
  transform: scale(0.96);
}
</style>
