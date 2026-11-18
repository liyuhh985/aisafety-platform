<template>
  <img v-if="resolvedSrc" :src="resolvedSrc" :alt="alt" v-bind="$attrs" />
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

defineOptions({ inheritAttrs: false })
const props = defineProps({
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
})

const resolvedSrc = ref('')
let objectUrl = ''
let abortController = null

function releaseObjectUrl() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl)
    objectUrl = ''
  }
}

async function resolveSource(value) {
  abortController?.abort()
  abortController = null
  releaseObjectUrl()

  if (!value) {
    resolvedSrc.value = ''
    return
  }
  if (value.startsWith('blob:') || value.startsWith('data:') || !value.startsWith('/api/files/')) {
    resolvedSrc.value = value
    return
  }

  const token = localStorage.getItem('token')
  if (!token) {
    resolvedSrc.value = ''
    return
  }

  abortController = new AbortController()
  try {
    const response = await fetch(value, {
      headers: { Authorization: `Bearer ${token}` },
      signal: abortController.signal,
    })
    if (!response.ok) throw new Error(`图片读取失败 (${response.status})`)
    const blob = await response.blob()
    objectUrl = URL.createObjectURL(blob)
    resolvedSrc.value = objectUrl
  } catch (error) {
    if (error.name !== 'AbortError') console.warn('受保护图片加载失败', error)
    resolvedSrc.value = ''
  }
}

watch(() => props.src, resolveSource, { immediate: true })
onBeforeUnmount(() => {
  abortController?.abort()
  releaseObjectUrl()
})
</script>
