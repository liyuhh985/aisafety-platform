<template>
  <canvas ref="canvasRef" class="particle-canvas"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)
let animationId = null
let particles = []

const CONFIG = {
  particleCount: 80,
  maxSpeed: 0.4,
  minSize: 1.5,
  maxSize: 3,
  connectionDistance: 150,
  connectionOpacity: 0.25,
  colors: [
    { r: 0, g: 210, b: 255 },   // cyan
    { r: 58, g: 123, b: 213 },   // blue
    { r: 0, g: 230, b: 118 },    // green
    { r: 0, g: 191, b: 165 },    // teal
  ],
}

class Particle {
  constructor(w, h) {
    this.x = Math.random() * w
    this.y = Math.random() * h
    this.vx = (Math.random() - 0.5) * CONFIG.maxSpeed * 2
    this.vy = (Math.random() - 0.5) * CONFIG.maxSpeed * 2
    this.size = CONFIG.minSize + Math.random() * (CONFIG.maxSize - CONFIG.minSize)
    this.color = CONFIG.colors[Math.floor(Math.random() * CONFIG.colors.length)]
    this.alpha = 0.4 + Math.random() * 0.6
    this.w = w
    this.h = h
  }

  update() {
    this.x += this.vx
    this.y += this.vy

    if (this.x < 0 || this.x > this.w) this.vx *= -1
    if (this.y < 0 || this.y > this.h) this.vy *= -1

    this.x = Math.max(0, Math.min(this.w, this.x))
    this.y = Math.max(0, Math.min(this.h, this.y))
  }

  draw(ctx) {
    const { r, g, b } = this.color
    ctx.beginPath()
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2)
    ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${this.alpha})`
    ctx.fill()

    // glow
    const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.size * 4)
    gradient.addColorStop(0, `rgba(${r}, ${g}, ${b}, ${this.alpha * 0.3})`)
    gradient.addColorStop(1, `rgba(${r}, ${g}, ${b}, 0)`)
    ctx.beginPath()
    ctx.arc(this.x, this.y, this.size * 4, 0, Math.PI * 2)
    ctx.fillStyle = gradient
    ctx.fill()
  }
}

function drawConnections(ctx, particles) {
  for (let i = 0; i < particles.length; i++) {
    for (let j = i + 1; j < particles.length; j++) {
      const dx = particles[i].x - particles[j].x
      const dy = particles[i].y - particles[j].y
      const dist = Math.sqrt(dx * dx + dy * dy)

      if (dist < CONFIG.connectionDistance) {
        const opacity = (1 - dist / CONFIG.connectionDistance) * CONFIG.connectionOpacity
        const ci = particles[i].color
        const cj = particles[j].color
        const r = Math.round((ci.r + cj.r) / 2)
        const g = Math.round((ci.g + cj.g) / 2)
        const b = Math.round((ci.b + cj.b) / 2)

        ctx.beginPath()
        ctx.moveTo(particles[i].x, particles[i].y)
        ctx.lineTo(particles[j].x, particles[j].y)
        ctx.strokeStyle = `rgba(${r}, ${g}, ${b}, ${opacity})`
        ctx.lineWidth = 0.6
        ctx.stroke()
      }
    }
  }
}

function init() {
  const canvas = canvasRef.value
  if (!canvas) return

  const ctx = canvas.getContext('2d')
  let w = window.innerWidth
  let h = window.innerHeight

  function resize() {
    w = window.innerWidth
    h = window.innerHeight
    canvas.width = w
    canvas.height = h
  }

  resize()
  window.addEventListener('resize', resize)

  // create particles
  particles = []
  const count = Math.min(CONFIG.particleCount, Math.floor((w * h) / 12000))
  for (let i = 0; i < count; i++) {
    particles.push(new Particle(w, h))
  }

  function animate() {
    ctx.clearRect(0, 0, w, h)

    drawConnections(ctx, particles)

    for (const p of particles) {
      p.update()
      p.draw(ctx)
    }

    animationId = requestAnimationFrame(animate)
  }

  animate()
}

onMounted(() => {
  init()
})

onUnmounted(() => {
  if (animationId) {
    cancelAnimationFrame(animationId)
  }
})
</script>

<style scoped>
.particle-canvas {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  pointer-events: none;
}
</style>
