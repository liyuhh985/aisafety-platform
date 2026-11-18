<template>
  <div class="login-view page-bg">
    <div class="login-card glass-card">
      <!-- 极简返回按钮 -->
      <router-link to="/" class="back-btn btn-pill btn-pill-secondary">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6"/>
        </svg>
        <span>返回首页</span>
      </router-link>

      <!-- 品牌标识 -->
      <div class="brand">
        <div class="brand-icon">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </div>
        <div class="platform-kicker">智慧应急治理中心</div>
        <h1 class="brand-title">城市安全综合平台</h1>
        <p class="brand-desc">隐患全要素态势感知与协同闭环处置系统</p>
      </div>

      <!-- Tab 切换 -->
      <div class="tab-bar">
        <button class="tab-btn" :class="{ active: mode === 'login' }" @click="mode = 'login'">专员登录</button>
        <button class="tab-btn" :class="{ active: mode === 'register' }" @click="mode = 'register'">账号注册</button>
      </div>

      <!-- 登录表单 -->
      <form v-if="mode === 'login'" class="auth-form" @submit.prevent="handleLogin">
        <div class="form-group">
          <label class="form-label">注册邮箱</label>
          <input v-model="loginForm.email" type="email" class="form-input" placeholder="请输入绑定的政务/办公邮箱" required />
        </div>
        <div class="form-group">
          <label class="form-label">访问密码</label>
          <input v-model="loginForm.password" type="password" class="form-input" placeholder="请输入密码" required />
        </div>
        <button type="submit" class="submit-btn btn-pill btn-pill-primary" :disabled="loading">
          {{ loading ? '身份凭证核验中...' : '登 录 系 统' }}
        </button>
        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
      </form>

      <!-- 注册表单 -->
      <form v-else class="auth-form" @submit.prevent="handleRegister">
        <div class="form-group">
          <label class="form-label">电子邮箱</label>
          <input v-model="registerForm.email" type="email" class="form-input" placeholder="请输入有效邮箱" required />
        </div>
        <div class="form-group code-group">
          <label class="form-label">安全验证码</label>
          <div class="code-row">
            <input v-model="registerForm.code" type="text" class="form-input code-input" placeholder="6位验证码" required />
            <button type="button" class="send-code-btn btn-pill-secondary" :disabled="codeSending" @click="sendCode">
              {{ codeSending ? '发送中...' : codeCountdown > 0 ? `${codeCountdown}s 后重发` : '获取验证码' }}
            </button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">设置密码</label>
          <input v-model="registerForm.password" type="password" class="form-input" placeholder="至少6位组合" required />
        </div>
        <div class="form-group">
          <label class="form-label">专员姓名/昵称</label>
          <input v-model="registerForm.nickname" type="text" class="form-input" placeholder="选填，如：网格巡查员" />
        </div>
        <button type="submit" class="submit-btn btn-pill btn-pill-primary" :disabled="loading">
          {{ loading ? '正在提交注册...' : '注 册 账 号' }}
        </button>
        <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { login, register, sendEmailCode } from '../api/auth.js'

const router = useRouter()
const route = useRoute()

const mode = ref('login')
const loading = ref(false)
const errorMsg = ref('')

const loginForm = reactive({ email: '', password: '' })
const registerForm = reactive({ email: '', password: '', code: '', nickname: '' })

const codeSending = ref(false)
const codeCountdown = ref(0)
let timer = null

function startCountdown() {
  codeCountdown.value = 60
  timer = setInterval(() => {
    codeCountdown.value--
    if (codeCountdown.value <= 0) {
      clearInterval(timer)
      timer = null
    }
  }, 1000)
}

async function sendCode() {
  if (!registerForm.email) {
    errorMsg.value = '请先输入邮箱'
    return
  }
  errorMsg.value = ''
  codeSending.value = true
  try {
    const json = await sendEmailCode(registerForm.email)
    if (json.code === 200) {
      startCountdown()
    } else {
      errorMsg.value = json.message || '验证码发送失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络异常，请重试'
  } finally {
    codeSending.value = false
  }
}

async function handleLogin() {
  errorMsg.value = ''
  loading.value = true
  try {
    const json = await login(loginForm.email, loginForm.password)
    if (json.code === 200 && json.data) {
      localStorage.setItem('token', json.data.token)
      localStorage.setItem('userId', json.data.userId)
      localStorage.setItem('nickname', json.data.nickname || '值班专员')
      localStorage.setItem('role', json.data.role != null ? String(json.data.role) : '0')
      const redirect = route.query.redirect || '/'
      router.push(redirect)
    } else {
      errorMsg.value = json.message || '登录失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络异常，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  errorMsg.value = ''
  loading.value = true
  try {
    const json = await register(registerForm)
    if (json.code === 200) {
      mode.value = 'login'
      loginForm.email = registerForm.email
      loginForm.password = ''
      errorMsg.value = ''
      alert('注册成功，请使用新账号登录')
    } else {
      errorMsg.value = json.message || '注册失败'
    }
  } catch (e) {
    errorMsg.value = e.message || '网络异常，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-view {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 16px;
}

.login-card {
  width: 100%;
  max-width: 440px;
  padding: 36px 32px 40px;
  position: relative;
  border-radius: 24px;
  background: #ffffff;
}

.back-btn {
  position: absolute;
  top: 18px;
  left: 18px;
  padding: 4px 12px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.brand {
  text-align: center;
  margin-top: 20px;
  margin-bottom: 24px;
}

.brand-icon {
  width: 58px;
  height: 58px;
  border-radius: 16px;
  background: #eff6ff;
  border: 1px solid #dbeafe;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}

.platform-kicker {
  font-size: 11px;
  color: #64748b;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}

.brand-title {
  font-size: 20px;
  font-weight: 800;
  color: #0f172a;
  margin-bottom: 6px;
}

.brand-desc {
  font-size: 12px;
  color: #64748b;
}

/* Tab 切换 */
.tab-bar {
  display: flex;
  border-radius: 9999px;
  background: #f1f5f9;
  padding: 4px;
  margin-bottom: 24px;
}

.tab-btn {
  flex: 1;
  padding: 8px 0;
  background: transparent;
  border: none;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s;
}
.tab-btn.active {
  background: #ffffff;
  color: #1a73e8;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
}

/* 表单组 */
.auth-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
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

.form-input {
  width: 100%;
  padding: 10px 14px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  color: #0f172a;
  font-size: 14px;
  outline: none;
  transition: all 0.2s;
}
.form-input:focus {
  background: #ffffff;
  border-color: #1a73e8;
  box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.15);
}

.code-row {
  display: flex;
  gap: 10px;
}

.code-input {
  flex: 1;
}

.send-code-btn {
  flex-shrink: 0;
  padding: 10px 16px;
  font-size: 12px;
  font-weight: 600;
}

.submit-btn {
  margin-top: 6px;
  padding: 12px;
  font-size: 14px;
  width: 100%;
}

.error-msg {
  font-size: 12px;
  color: #ef4444;
  text-align: center;
  margin-top: 4px;
}

@media (max-width: 480px) {
  .login-card {
    padding: 28px 20px;
  }
}
</style>
