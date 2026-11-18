<template>
  <div class="home-view">
    <!-- 顶部全局导航 Header (Antigravity 白底毛玻璃) -->
    <header class="navbar">
      <div class="nav-container">
        <div class="nav-left">
          <div class="brand-logo" title="城市安全智能研判">
            <svg width="26" height="26" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="brandShieldGrad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#2563eb" />
                  <stop offset="55%" stop-color="#1d4ed8" />
                  <stop offset="100%" stop-color="#0f172a" />
                </linearGradient>
                <linearGradient id="cityLightGrad" x1="16" y1="6" x2="16" y2="26" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#ffffff" />
                  <stop offset="100%" stop-color="#93c5fd" />
                </linearGradient>
                <linearGradient id="aiCoreGrad" x1="13" y1="9" x2="19" y2="15" gradientUnits="userSpaceOnUse">
                  <stop offset="0%" stop-color="#38bdf8" />
                  <stop offset="100%" stop-color="#60a5fa" />
                </linearGradient>
              </defs>
              <rect width="32" height="32" rx="9" fill="url(#brandShieldGrad)" />
              <path d="M16 5.5L24.5 9.2V15.8C24.5 21.2 20.8 25.4 16 26.8C11.2 25.4 7.5 21.2 7.5 15.8V9.2L16 5.5Z" 
                    stroke="url(#cityLightGrad)" stroke-width="1.6" stroke-linejoin="round" fill="rgba(255,255,255,0.06)" />
              <path d="M11.5 20.5V15.5H14V20.5M14 20.5V13H18V20.5M18 20.5V15H20.5V20.5" 
                    stroke="rgba(255,255,255,0.6)" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
              <circle cx="16" cy="11.5" r="1.8" fill="url(#aiCoreGrad)" />
              <path d="M16 8.6V9.8M16 13.2V14.4M13.6 11.5H14.8M17.2 11.5H18.4" 
                    stroke="#67e8f9" stroke-width="1.2" stroke-linecap="round" />
            </svg>
          </div>
          <span class="brand-name">
            <span class="brand-text-desktop">城市安全智能研判</span>
            <span class="brand-text-mobile">城市安全研判</span>
          </span>
        </div>

        <!-- 顶部核心工具导航 (统一Apple/SaaS规范的温润果冻微胶囊) -->
        <nav class="nav-right">
          <router-link to="/analysis" class="nav-link" active-class="active-link" title="多模态影像智能研判">
            <div class="nav-icon-box">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                <circle cx="12" cy="13" r="4"/>
              </svg>
            </div>
            <span>影像研判</span>
          </router-link>

          <router-link to="/map" class="nav-link" active-class="active-link" title="城市安全全域空间地图">
            <div class="nav-icon-box">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
                <line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>
              </svg>
            </div>
            <span>隐患地图</span>
          </router-link>

          <router-link to="/hazard" class="nav-link task-nav-link" active-class="active-link" title="工单处置与上报追踪">
            <div class="nav-icon-box">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
                <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
              </svg>
              <span class="nav-pulse-dot"></span>
            </div>
            <span>{{ hazardNavText }}</span>
          </router-link>

          <router-link to="/history" class="nav-link" active-class="active-link" title="查看AI即时诊断报告历史档案">
            <div class="nav-icon-box">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
                <line x1="16" y1="13" x2="8" y2="13"/>
                <line x1="16" y1="17" x2="8" y2="17"/>
              </svg>
            </div>
            <span>研判报告</span>
          </router-link>

          <div class="nav-divider"></div>

          <!-- 现代高雅用户状态胶囊 -->
          <div v-if="isLoggedIn" class="user-pill glass-card">
            <div class="user-avatar-badge" :title="nickname">
              <span class="avatar-char">{{ (nickname || '专')[0] }}</span>
              <span class="user-status-pulse" title="在线状态正常"></span>
            </div>
            <span class="user-name" :title="nickname">{{ nickname }}</span>
            <button class="exit-pill-btn" @click="handleLogout" title="安全退出系统">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
              <span class="exit-text">退出</span>
            </button>
          </div>
          <button v-else class="btn-pill btn-pill-primary login-nav-btn" @click="router.push('/login')">
            登录
          </button>
        </nav>
      </div>
    </header>

    <!-- 核心 Gemini 式 Agent 主控工作区 -->
    <main class="main-stage">
      <div class="stage-container animate-fade-in-up" :class="{ 'has-conversation': messages.length > 0 }">
        <!-- 首页上方已办结安全治理成效动态轮播 -->
        <ClosedHazardsCarousel />

        <!-- 动态大问候语 (对标 Gemini 界面) -->
        <div v-if="messages.length === 0" class="hero-greeting">
          <h1 class="greeting-title">接下来呢，{{ nickname }}？</h1>
          <p class="greeting-subtitle">描述现场安全问题，或上传现场照片即刻启动多模态视觉研判与法规比对</p>
        </div>

        <!-- 聊天/研判流式对话记录 -->
        <div v-if="messages.length > 0" class="conversation-stream">
          <!-- 现代高质感微光流岛会话控制条 -->
          <div class="stream-toolbar">
            <div class="session-status-badge">
              <div class="status-indicator-ring">
                <span class="pulse-dot"></span>
              </div>
              <span class="session-label">
                <span class="label-desktop">AI 多模态智能研判进行中</span>
                <span class="label-mobile">智能研判中</span>
              </span>
              <span class="msg-counter num-font">{{ messages.length }} 条记录</span>
            </div>
            <button class="new-chat-btn" type="button" @click="clearChat" title="清空上下文并开启新一轮对话">
              <div class="new-chat-icon-box">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                  <path d="M12 3v3m0 12v3M3 12h3m12 0h3M5.6 5.6l2.1 2.1m8.6 8.6l2.1 2.1M5.6 18.4l2.1-2.1m8.6-8.6l2.1-2.1"/>
                </svg>
              </div>
              <span class="btn-text-desktop">开启新会话</span>
              <span class="btn-text-mobile">新对话</span>
            </button>
          </div>

          <!-- 常驻锁定领域状态条 (规范第 2 条：locked_* 渲染"本对话正在记录：消防通道占用") -->
          <div v-if="activeLock.title" class="locked-status-strip">
            <div class="locked-status-left">
              <span class="locked-pulse-dot"></span>
              <span class="locked-icon">🔒</span>
              <span class="locked-title-text">本对话正在记录：<strong>{{ activeLock.title }}</strong></span>
            </div>
            <div class="locked-status-right">
              <span class="locked-rule-tip">换隐患就新开一个对话</span>
            </div>
          </div>

          <div v-for="(msg, index) in messages" :key="index" class="chat-row" :class="msg.role">
            <div class="chat-bubble">
              <div v-if="msg.image" class="bubble-image-wrap">
                <img :src="msg.image" alt="现场隐患" class="bubble-img" />
              </div>

              <!-- 若包含 taxonomy 解析事件数据，展示规范分类标签与非阻塞提醒横幅 -->
              <div v-if="msg.taxonomy" class="msg-taxonomy-zone">
                <!-- 跨领域偏离提醒与一键【改报 XX】行动条 (规范核心第 2 条：suggested_major_code 非空时渲染) -->
                <div v-if="msg.taxonomy.suggested_major_code && !msg.suggestedActionHandled" class="suggested-major-banner">
                  <div class="suggested-major-info">
                    <span class="suggested-icon">🧭</span>
                    <span class="suggested-text">
                      检测到偏离了当前锁定的领域范围，推荐改报<strong>「{{ getMajorLabelByCode(msg.taxonomy.suggested_major_code) }}」</strong>
                    </span>
                  </div>
                  <button
                    type="button"
                    class="re-report-btn"
                    :disabled="analyzing"
                    @click="switchAndResend(msg.taxonomy.suggested_major_code, msg)"
                  >
                    <span>改报 {{ getMajorLabelByCode(msg.taxonomy.suggested_major_code) }}</span>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                      <polyline points="9 18 15 12 9 6"/>
                    </svg>
                  </button>
                </div>

                <!-- 即时险情安全避险提示 (immediate_danger 为 true 时呈现高优先级警示) -->
                <div v-if="msg.taxonomy.immediate_danger" class="immediate-danger-banner">
                  <span class="danger-icon">⚠️</span>
                  <span class="danger-text">系统检测到即刻安全险情，请优先注意自身防护并撤离现场危急区域！</span>
                </div>

                <!-- 非阻塞类别差异确认条 (major_mismatch) -->
                <div v-if="msg.taxonomy.major_mismatch && !msg.taxonomyMismatchAccepted" class="taxonomy-mismatch-banner">
                  <span class="mismatch-icon">💡</span>
                  <span class="mismatch-text">
                    已按“{{ getTaxonomyResolutionText(msg.taxonomy) }}”记录
                  </span>
                  <div class="mismatch-actions">
                    <button class="mismatch-btn accept-btn" type="button" @click="acceptMismatch(msg)">[接受]</button>
                    <button class="mismatch-btn modify-btn" type="button" @click="modifyMismatch(msg)">[修改类别]</button>
                  </div>
                </div>

                <!-- 识别到的多重隐患 Issues 标签流 (注意：时机变了，不假设 issues 非空) -->
                <div v-if="msg.taxonomy.issues && msg.taxonomy.issues.length > 0" class="taxonomy-issues-row">
                  <span
                    v-for="(issue, iIdx) in msg.taxonomy.issues"
                    :key="iIdx"
                    class="taxonomy-issue-tag"
                  >
                    🏷️ {{ issue.major_label || issue.major_code }} · {{ issue.subcategory_label || issue.subcategory_code }}
                  </span>
                </div>
              </div>

              <div class="bubble-content" v-html="renderMarkdown(msg.content)"></div>

              <!-- 任务确认中断事件决策卡片 (interrupt 事件契约) -->
              <div v-if="msg.interrupt && !msg.interruptHandled" class="interrupt-confirm-card">
                <div class="interrupt-header">
                  <span class="interrupt-icon">📋</span>
                  <span class="interrupt-question">{{ msg.interrupt.type === 'confirm_create_task' && msg.interrupt.draft ? '请确认工单信息' : (msg.interrupt.question || '需要我帮你在系统建一条隐患任务吗？') }}</span>
                </div>
                <!-- ask_address 卡片按类型分流：追问地址时只显示输入引导，不放确认建单/不用了按钮 -->
                <div v-if="msg.interrupt.type === 'ask_address'" class="interrupt-hint-row">
                  <span class="interrupt-hint">💡 请在下方输入框里写出具体地址后发送，例如：XX 市 XX 区 XX 路 XX 小区 / XX 地标。</span>
                </div>
                <template v-else-if="hasInterruptDraft(msg)">
                  <div class="interrupt-form">
                    <label class="interrupt-field interrupt-field-wide">
                      <span class="interrupt-field-label">地址</span>
                      <input
                        v-model="msg.interrupt.draft.address"
                        type="text"
                        class="interrupt-input"
                        placeholder="请输入具体地址"
                      />
                    </label>
                    <label class="interrupt-field">
                      <span class="interrupt-field-label">类别</span>
                      <select v-model="msg.interrupt.draft.categoryList[0]" class="interrupt-input">
                        <option value="" disabled>请选择类别</option>
                        <option
                          v-for="option in getDraftCategoryOptions(msg)"
                          :key="option.value"
                          :value="option.value"
                        >
                          {{ option.label }}
                        </option>
                      </select>
                    </label>
                    <label class="interrupt-field">
                      <span class="interrupt-field-label">严重度</span>
                      <select v-model.number="msg.interrupt.draft.severity" class="interrupt-input">
                        <option :value="0">0 一般</option>
                        <option :value="1">1 较重</option>
                        <option :value="2">2 严重</option>
                      </select>
                    </label>
                    <label class="interrupt-field interrupt-field-wide">
                      <span class="interrupt-field-label">描述</span>
                      <textarea
                        v-model="msg.interrupt.draft.description"
                        class="interrupt-textarea"
                        rows="2"
                        placeholder="请输入隐患描述"
                      ></textarea>
                    </label>
                    <div v-if="getDraftImageSource(msg)" class="interrupt-image-row">
                      <SecureImage :src="getDraftImageSource(msg)" alt="现场隐患缩略图" class="interrupt-image-thumb" />
                    </div>
                  </div>
                  <div class="interrupt-actions">
                    <button
                      type="button"
                      class="interrupt-btn confirm-btn"
                      :disabled="analyzing"
                      @click="handleInterruptAction(msg, 'confirm')"
                    >
                      <span>确认建单</span>
                    </button>
                    <button
                      type="button"
                      class="interrupt-btn cancel-btn"
                      :disabled="analyzing"
                      @click="handleInterruptAction(msg, 'decline')"
                    >
                      <span>暂不建单</span>
                    </button>
                  </div>
                </template>
                <div v-else class="interrupt-actions">
                  <button
                    type="button"
                    class="interrupt-btn confirm-btn"
                    :disabled="analyzing"
                    @click="handleInterruptAction(msg, 'confirm')"
                  >
                    <span>✓ 好的，立即建单</span>
                  </button>
                  <button
                    type="button"
                    class="interrupt-btn cancel-btn"
                    :disabled="analyzing"
                    @click="handleInterruptAction(msg, 'decline')"
                  >
                    <span>✕ 不用了</span>
                  </button>
                </div>
              </div>

              <!-- 异步建单状态（task_accepted + 状态轮询） -->
              <div v-if="msg.creating" class="task-create-status is-creating">创建中…</div>
              <div v-if="msg.createError" class="task-create-status is-error">{{ msg.createError }}</div>
              <div v-if="msg.pollTimedOut" class="task-create-status is-muted">任务仍在创建，可稍后到工单列表查看</div>

              <!-- 建单成功后的「查看工单」入口（消费 task_created 事件） -->
              <div v-if="msg.taskCreated" class="task-created-row animate-fade-in-up">
                <button
                  type="button"
                  class="task-created-btn"
                  @click="router.push(`/hazard/${msg.taskCreated.hazard_id}`)"
                  title="点击查看隐患工单全要素档案与流转动态"
                >
                  <div class="task-btn-icon-wrap">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                      <line x1="16" y1="13" x2="8" y2="13"/>
                      <line x1="16" y1="17" x2="8" y2="17"/>
                    </svg>
                  </div>
                  <span class="task-btn-label">查看工单</span>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" class="task-btn-arrow">
                    <polyline points="9 18 15 12 9 6"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <div v-if="analyzing && statusText" class="chat-row assistant">
            <div class="chat-bubble typing-bubble">
              <div class="gemini-sparkle"></div>
              <span>{{ statusText }}</span>
            </div>
          </div>
        </div>

        <!-- Gemini 式中央悬浮核心输入卡片 (支持点击加号选图、拖拽放图与文字输入) -->
        <div class="gemini-input-card" :class="{ 'is-focused': isInputFocused, 'dragover': isDragging }"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
        >
          <!-- 顶部辅助操作栏：图片缩略图胶囊 + 预选领域胶囊 (保持布局轻量紧凑) -->
          <div class="input-top-bar">
            <!-- 预选隐患大类提示胶囊 (规范要求：可选，默认自动判断，绝不阻塞发消息) -->
            <div class="major-hint-row">
              <div class="major-selector-capsule" @click.stop="toggleMajorDropdown" title="点击选择或切换隐患领域">
                <span class="selector-icon">🏷️</span>
                <span class="selector-label">
                  {{ selectedMajor ? selectedMajor.label : '隐患领域: 自动判断' }}
                </span>
                <button
                  v-if="selectedMajor"
                  class="remove-major-btn"
                  type="button"
                  @click.stop="clearSelectedMajor"
                  title="清除指定，改为自动判断"
                >✕</button>
                <span v-else class="caret-arrow">▾</span>
              </div>

              <!-- 下拉大类快捷选择菜单 -->
              <div v-if="showMajorDropdown" class="major-dropdown-menu glass-card">
                <div class="dropdown-header">
                  <span>选择预研判领域（可选）</span>
                  <button class="close-dropdown-btn" type="button" @click.stop="showMajorDropdown = false">✕</button>
                </div>
                <div class="dropdown-chips-grid">
                  <button
                    type="button"
                    class="dropdown-chip"
                    :class="{ active: !selectedMajorCode }"
                    @click="chooseMajor('')"
                  >
                    ⚡ 不确定，自动判断
                  </button>
                  <button
                    v-for="m in HAZARD_TAXONOMY"
                    :key="m.code"
                    type="button"
                    class="dropdown-chip"
                    :class="{ active: selectedMajorCode === m.code }"
                    @click="chooseMajor(m.code)"
                  >
                    {{ m.label }}
                  </button>
                </div>
              </div>
            </div>

            <!-- 图片选择后的缩略图胶囊 -->
            <div v-if="previewUrl" class="selected-image-capsule">
              <img :src="previewUrl" alt="已选隐患图片" class="capsule-thumb" />
              <span class="capsule-tip">现场图像已就绪</span>
              <button class="capsule-remove" type="button" @click="removeSelectedImage" title="移除此图">✕</button>
            </div>
          </div>

          <!-- 中部核心大面积多行文本书写区 (纵向视野全面撑开，告别单薄扁平) -->
          <div class="input-editor-zone">
            <textarea
              ref="textareaRef"
              v-model="inputText"
              class="gemini-textarea"
              rows="3"
              placeholder="详细描述现场安全隐患情况、具体问题或现场细节，或上传现场照片启动多模态安全研判..."
              @focus="isInputFocused = true"
              @blur="isInputFocused = false"
              @input="autoResizeTextarea"
              @keydown.enter.exact.prevent="handleSend"
            ></textarea>
          </div>

          <!-- 底部高阶功能操作工具栏 (彻底利用纵向空间，工具与发送自如排开) -->
          <div class="input-bottom-bar">
            <div class="bottom-tools-left">
              <button class="attach-pill-btn" type="button" @click="triggerUpload" title="上传现场照片 / 拍照">
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
                <span class="attach-label">添加现场照片</span>
              </button>
              <input ref="fileInputRef" type="file" accept="image/*" style="display:none" @change="onFileSelected" />

              <div class="model-badge-capsule" title="当前连接多模态视觉研判模型">
                <span class="sparkle-icon">✦</span>
                <span class="model-text">多模态研判模式</span>
              </div>
            </div>

            <div class="bottom-actions-right">
              <span class="shortcut-tip desktop-only">按 Enter 发送 · Shift + Enter 换行</span>
              <button
                class="send-pill-btn"
                type="button"
                :disabled="analyzing || (!inputText.trim() && !selectedFile)"
                @click="handleSend"
                title="发送研判请求"
              >
                <span>启动安全研判</span>
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="22" y1="2" x2="11" y2="13"/>
                  <polygon points="22 2 15 22 11 13 2 9 22 2"/>
                </svg>
              </button>
            </div>
          </div>
        </div>

        <!-- 旗舰级专业影像研判工作台直通看板 -->
        <div v-if="messages.length === 0" class="suggestions-zone animate-fade-in-up">
          <div class="direct-workbench-banner glass-card" @click="router.push('/analysis')">
            <div class="banner-left">
              <div class="banner-icon-wrapper">
                <div class="banner-icon-bg">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2.2">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                    <circle cx="12" cy="13" r="4"/>
                  </svg>
                </div>
                <div class="icon-pulse-glow"></div>
              </div>
              <div class="banner-texts">
                <div class="banner-title-line">
                  <span class="banner-title">专业隐患研判工作台</span>
                  <span class="pro-badge">
                    <span class="sparkle-icon">✨</span>
                    <span>旗舰研判模式 · PRO</span>
                  </span>
                </div>
                <div class="banner-feature-chips">
                  <span class="feature-chip">大视野准星标定</span>
                  <span class="chip-separator">/</span>
                  <span class="feature-chip">四阶段流式研判</span>
                  <span class="chip-separator">/</span>
                  <span class="feature-chip">规范公文鉴定书生成</span>
                </div>
              </div>
            </div>
            <div class="banner-cta-btn">
              <span class="cta-text desktop-text">立即开启专业研判</span>
              <span class="cta-text mobile-text">立即开启</span>
              <div class="cta-arrow-box">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                  <line x1="5" y1="12" x2="19" y2="12"></line>
                  <polyline points="12 5 19 12 12 19"></polyline>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import ClosedHazardsCarousel from '../components/ClosedHazardsCarousel.vue'
import SecureImage from '../components/SecureImage.vue'
import { HAZARD_TAXONOMY, resolveHazard } from '../constants/hazardTaxonomy.js'
import { getHazardRequestStatus } from '../api/hazard.js'
import { HAZARD_POLL_MAX_MS, nextHazardPollDelay } from '../utils/hazardPoll.js'

defineOptions({ name: 'HomeView' })
const router = useRouter()
const isLoggedIn = ref(!!localStorage.getItem('token'))
const nickname = ref(localStorage.getItem('nickname') || '专员')
const userRole = ref(localStorage.getItem('role') || '0')
const hazardNavText = computed(() => {
  if (userRole.value === '1') return '调度指挥'
  if (userRole.value === '2') return '工单处置'
  return '我的上报'
})

// 隐患大类预选提示 (规范第 1 条：可选，默认自动判断发空值，中途改选不清空历史)
const selectedMajorCode = ref('')
const showMajorDropdown = ref(false)
const selectedMajor = computed(() => {
  if (!selectedMajorCode.value || selectedMajorCode.value === 'auto' || selectedMajorCode.value === 'unknown') return null
  return HAZARD_TAXONOMY.find(m => m.code === selectedMajorCode.value) || null
})

function toggleMajorDropdown() {
  showMajorDropdown.value = !showMajorDropdown.value
}

function chooseMajor(code) {
  // 规范第 1 条：「自动判断」必须发空值，不能发 "auto" 或 "unknown"
  if (!code || code === 'auto' || code === 'unknown') {
    selectedMajorCode.value = ''
  } else {
    selectedMajorCode.value = code
  }
  showMajorDropdown.value = false
}

function clearSelectedMajor() {
  selectedMajorCode.value = ''
  showMajorDropdown.value = false
}

// 规范第 2 条：消费 taxonomy 的 locked_* 字段维护常驻持久状态条
const activeLock = ref({
  major: '',
  subcategory: '',
  title: ''
})

function updateActiveLock(tax) {
  if (!tax) return
  const m = tax.locked_major || ''
  const s = tax.locked_subcategory || ''
  if (m || s) {
    let title = ''
    if (s) {
      const resolved = resolveHazard(m ? `${m}/${s}` : s)
      title = resolved.subcategoryLabel || resolved.displayText || s
    } else if (m) {
      const resolved = resolveHazard(m)
      title = resolved.majorLabel || resolved.displayText || m
    }
    if (title) {
      activeLock.value = {
        major: m,
        subcategory: s,
        title: title
      }
    }
  }
}

function getMajorLabelByCode(code) {
  if (!code) return ''
  const item = HAZARD_TAXONOMY.find(m => m.code === code)
  if (item) return item.label
  const resolved = resolveHazard(code)
  return resolved.majorLabel || code
}

function getTaxonomyResolutionText(tax) {
  if (!tax) return ''
  // 规范第 3 条：时机变了，不再假设 issues 非空
  if (tax.issues && tax.issues.length > 0) {
    const first = tax.issues[0]
    return `${first.major_label || first.major_code} / ${first.subcategory_label || first.subcategory_code}`
  }
  if (tax.locked_subcategory || tax.locked_major) {
    const s = tax.locked_subcategory
    const m = tax.locked_major
    const resolved = resolveHazard(s ? `${m}/${s}` : m)
    return resolved.displayText
  }
  const resolved = resolveHazard(tax.selected_major_code)
  return resolved.displayText
}

function getLockedMajorCodes(msg) {
  const locked = msg && msg.taxonomy && msg.taxonomy.locked_majors
  if (!Array.isArray(locked) || locked.length === 0) return []
  return locked
    .map((item) => {
      if (typeof item === 'string') return item.trim()
      return String(item && (item.code || item.majorCode || item.major_code || item.value) || '').trim()
    })
    .filter(Boolean)
}

function getDraftCategoryOptions(msg) {
  const lockedCodes = getLockedMajorCodes(msg)
  const lockedMajors = lockedCodes.length
    ? HAZARD_TAXONOMY.filter((major) => lockedCodes.includes(major.code))
    : []
  const majors = lockedMajors.length ? lockedMajors : HAZARD_TAXONOMY
  return majors.flatMap((major) => major.subcategories.map((sub) => ({
    value: `${major.code}/${sub.code}`,
    label: `${major.label} / ${sub.label}`
  })))
}

function normalizeDraftCategoryList(categoryList) {
  if (Array.isArray(categoryList)) {
    return categoryList
      .map((item) => String(item || '').trim())
      .filter(Boolean)
  }
  if (typeof categoryList === 'string' && categoryList.trim()) {
    return [categoryList.trim()]
  }
  return []
}

function syncDraftCategoryWithLock(msg) {
  const draft = msg && msg.interrupt && msg.interrupt.draft
  if (!draft || !Array.isArray(draft.categoryList)) return
  const options = getDraftCategoryOptions(msg)
  const allowedValues = options.map((option) => option.value)
  const current = draft.categoryList[0]
  if (current && allowedValues.includes(current)) return
  if (options.length) draft.categoryList[0] = options[0].value
}

function hasInterruptDraft(msg) {
  const draft = msg && msg.interrupt && msg.interrupt.draft
  return !!draft && Array.isArray(draft.categoryList) && draft.categoryList.length > 0
}

function ensureInterruptDraft(msg) {
  const interrupt = msg && msg.interrupt
  const draft = interrupt && interrupt.draft
  if (!draft || typeof draft !== 'object') return null

  draft.categoryList = normalizeDraftCategoryList(draft.categoryList)
  draft.address = draft.address == null ? '' : String(draft.address)
  draft.description = draft.description == null ? '' : String(draft.description)
  if (draft.severity === undefined || draft.severity === null || draft.severity === '') {
    draft.severity = 0
  } else if (typeof draft.severity === 'string' && /^[012]$/.test(draft.severity)) {
    draft.severity = Number(draft.severity)
  }
  syncDraftCategoryWithLock(msg)
  return draft
}

function getDraftImageSource(msg) {
  const imageFileId = msg && msg.interrupt && msg.interrupt.draft && msg.interrupt.draft.image_file_id
  if (imageFileId !== undefined && imageFileId !== null && imageFileId !== '') {
    return `/api/files/${encodeURIComponent(String(imageFileId))}`
  }
  return msg && msg.image ? msg.image : ''
}

function acceptMismatch(msg) {
  msg.taxonomyMismatchAccepted = true
  saveChatCache()
}

function modifyMismatch(msg) {
  msg.taxonomyMismatchAccepted = true
  showMajorDropdown.value = true
  saveChatCache()
}

const inputText = ref('')
const textareaRef = ref(null)
const isInputFocused = ref(false)
const isDragging = ref(false)

function autoResizeTextarea() {
  if (!textareaRef.value) return
  textareaRef.value.style.height = 'auto'
  textareaRef.value.style.height = Math.min(textareaRef.value.scrollHeight, 180) + 'px'
}

function scrollToBottom() {
  nextTick(() => {
    window.scrollTo({
      top: document.documentElement.scrollHeight || document.body.scrollHeight,
      behavior: 'smooth'
    })
  })
}

const fileInputRef = ref(null)
const selectedFile = ref(null)
const previewUrl = ref('')
const analyzing = ref(false)
const statusText = ref('')
const messages = ref([])
let chatAbortController = null
const hazardPollingStates = new Map()
// 轮询间隔见 utils/hazardPoll.js（单一事实源）

let sessionId = localStorage.getItem('assistantSessionId') || ''
function saveChatCache() {
  try {
    sessionStorage.setItem('home_chat_messages', JSON.stringify(messages.value))
  } catch (e) {}
}

function getPendingHazardStorageKey() {
  const userId = localStorage.getItem('userId')
  return userId ? `pendingHazardRequest:${userId}` : ''
}

function rememberPendingHazardRequest(requestId) {
  if (!requestId) return
  const key = getPendingHazardStorageKey()
  if (key) localStorage.setItem(key, requestId)
}

function forgetPendingHazardRequest(requestId) {
  const key = getPendingHazardStorageKey()
  if (!key) return
  if (!requestId || localStorage.getItem(key) === requestId) {
    localStorage.removeItem(key)
  }
}

function getHazardPollElapsed(state) {
  return state.activeElapsedMs + (state.activeStartedAt ? Date.now() - state.activeStartedAt : 0)
}

function clearHazardPollTimer(state) {
  if (!state || !state.timerId) return
  clearTimeout(state.timerId)
  state.timerId = null
}

function stopHazardPollingState(state) {
  if (!state) return
  state.stopped = true
  clearHazardPollTimer(state)
  hazardPollingStates.delete(state.requestId)
}

function stopHazardPolling(requestId) {
  const state = hazardPollingStates.get(requestId)
  if (state) stopHazardPollingState(state)
}

function stopAllHazardPolling() {
  Array.from(hazardPollingStates.values()).forEach((state) => stopHazardPollingState(state))
}

function pauseHazardPollingState(state) {
  if (!state || state.stopped) return
  if (state.activeStartedAt) {
    state.activeElapsedMs += Date.now() - state.activeStartedAt
    state.activeStartedAt = 0
  }
  clearHazardPollTimer(state)
}

function finishHazardPollTimeout(state) {
  if (!state || state.stopped) return
  stopHazardPollingState(state)
  state.msg.creating = false
  state.msg.pollTimedOut = true
  state.msg.createError = ''
  saveChatCache()
}

function scheduleHazardPoll(state) {
  if (!state || state.stopped || document.hidden) return
  clearHazardPollTimer(state)

  const delay = nextHazardPollDelay(getHazardPollElapsed(state))
  if (delay < 0) {
    finishHazardPollTimeout(state)
    return
  }
  state.timerId = setTimeout(() => {
    state.timerId = null
    if (state.stopped || document.hidden) return
    if (nextHazardPollDelay(getHazardPollElapsed(state)) < 0) {
      finishHazardPollTimeout(state)
      return
    }
    pollHazardRequest(state)
  }, delay)
}

async function pollHazardRequest(state) {
  if (!state || state.stopped || state.inFlight || document.hidden) return
  state.inFlight = true
  try {
    const response = await getHazardRequestStatus(state.requestId)
    if (state.stopped) return
    const data = response && typeof response === 'object' && response.data && typeof response.data === 'object'
      ? response.data
      : response
    const status = String(data && data.status || '').toUpperCase()

    if (status === 'SUCCESS') {
      const hazardId = data.hazardId !== undefined ? data.hazardId : data.hazard_id
      if (hazardId === undefined || hazardId === null || hazardId === '') {
        stopHazardPollingState(state)
        state.msg.creating = false
        state.msg.pollTimedOut = false
        state.msg.createError = '建单成功但未返回工单号，请到工单列表查看'
        forgetPendingHazardRequest(state.requestId)
        saveChatCache()
        return
      }
      stopHazardPollingState(state)
      state.msg.creating = false
      state.msg.pollTimedOut = false
      state.msg.createError = ''
      state.msg.taskCreated = { hazard_id: hazardId }
      forgetPendingHazardRequest(state.requestId)
      saveChatCache()
      scrollToBottom()
      return
    }

    if (status === 'FAILED') {
      stopHazardPollingState(state)
      state.msg.creating = false
      state.msg.pollTimedOut = false
      state.msg.createError = (data && data.message) || '创建失败'
      forgetPendingHazardRequest(state.requestId)
      saveChatCache()
      return
    }

    state.msg.creating = true
  } catch (error) {
    if (!state.stopped) console.warn('建单状态轮询失败，稍后继续重试', error)
  } finally {
    state.inFlight = false
    if (!state.stopped && !document.hidden) scheduleHazardPoll(state)
  }
}

function refreshHazardPollingNow(state) {
  if (!state || state.stopped || document.hidden) return
  clearHazardPollTimer(state)
  if (getHazardPollElapsed(state) >= HAZARD_POLL_MAX_MS) {
    finishHazardPollTimeout(state)
    return
  }
  pollHazardRequest(state)
}

function startHazardPolling(msg, requestId) {
  if (!msg || !requestId) return
  stopHazardPolling(requestId)

  msg.creating = true
  msg.createError = ''
  msg.pollTimedOut = false

  const state = {
    requestId,
    msg,
    timerId: null,
    activeElapsedMs: 0,
    activeStartedAt: document.hidden ? 0 : Date.now(),
    inFlight: false,
    stopped: false
  }
  hazardPollingStates.set(requestId, state)
  saveChatCache()
  if (!document.hidden) scheduleHazardPoll(state)
}

function handlePageVisibilityChange() {
  if (document.hidden) {
    Array.from(hazardPollingStates.values()).forEach(pauseHazardPollingState)
    return
  }
  Array.from(hazardPollingStates.values()).forEach((state) => {
    if (state.stopped) return
    if (!state.activeStartedAt) state.activeStartedAt = Date.now()
    refreshHazardPollingNow(state)
  })
}

function getOrCreateCurrentAssistantMessage() {
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') return last
  const msg = { role: 'assistant', content: '' }
  messages.value.push(msg)
  return msg
}

function restorePendingHazardPolling() {
  const key = getPendingHazardStorageKey()
  const requestId = key ? (localStorage.getItem(key) || '').trim() : ''
  if (!key || !requestId) {
    if (key && !requestId) localStorage.removeItem(key)
    messages.value.forEach((msg) => {
      if (msg.creating) msg.creating = false
    })
    return
  }

  let msg = null
  for (let i = messages.value.length - 1; i >= 0; i--) {
    if (messages.value[i].role === 'assistant') {
      msg = messages.value[i]
      break
    }
  }
  if (!msg) {
    msg = { role: 'assistant', content: '正在确认工单创建状态…' }
    messages.value.push(msg)
  }
  startHazardPolling(msg, requestId)
}

async function clearChat() {
  chatAbortController?.abort()
  const oldSessionId = sessionId
  const token = localStorage.getItem('token')
  if (token && oldSessionId) {
    try {
      const response = await fetch(`/api/ai/session?sessionId=${encodeURIComponent(oldSessionId)}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) console.warn('服务端会话清理返回 ' + response.status + '，旧会话将不再复用')
    } catch (error) {
      console.warn('服务端会话清理失败，将改用新会话', error)
    }
  }
  messages.value = []
  activeLock.value = { major: '', subcategory: '', title: '' }
  sessionStorage.removeItem('home_chat_messages')
  localStorage.removeItem('assistantSessionId')
  sessionId = ''
}

onMounted(() => {
  try {
    const cached = sessionStorage.getItem('home_chat_messages')
    if (cached && messages.value.length === 0) {
      messages.value = JSON.parse(cached)
      // 遍历恢复持久状态条 activeLock
      for (let i = messages.value.length - 1; i >= 0; i--) {
        const m = messages.value[i]
        if (m.taxonomy && (m.taxonomy.locked_major || m.taxonomy.locked_subcategory)) {
          updateActiveLock(m.taxonomy)
          break
        }
      }
      scrollToBottom()
      saveChatCache()
    }
  } catch (e) {
    console.warn('恢复聊天记录失败', e)
  }
  restorePendingHazardPolling()
  document.addEventListener('visibilitychange', handlePageVisibilityChange)
})

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', handlePageVisibilityChange)
  stopAllHazardPolling()
})

function handleLogout() {
  stopAllHazardPolling()
  // 保留 pendingHazardRequest:${userId}：异步建单与登录态无关，
  // 重登后还要按这个 requestId 继续查结果；key 本身按 userId 隔离。
  localStorage.removeItem('token')
  localStorage.removeItem('userId')
  localStorage.removeItem('nickname')
  localStorage.removeItem('role')
  localStorage.removeItem('assistantSessionId')
  sessionStorage.removeItem('home_chat_messages')
  sessionId = ''
  userRole.value = '0'
  isLoggedIn.value = false
  nickname.value = '专员'
}

function triggerUpload() {
  fileInputRef.value && fileInputRef.value.click()
}

function onFileSelected(e) {
  const f = e.target.files && e.target.files[0]
  if (!f) return
  if (f.size > 20 * 1024 * 1024) {
    alert('图片大小不能超过 20MB')
    return
  }
  selectedFile.value = f
  previewUrl.value = URL.createObjectURL(f)
  e.target.value = ''
}

function handleDrop(e) {
  isDragging.value = false
  const f = e.dataTransfer.files && e.dataTransfer.files[0]
  if (f && f.type.startsWith('image/')) {
    selectedFile.value = f
    previewUrl.value = URL.createObjectURL(f)
  }
}

function removeSelectedImage() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  selectedFile.value = null
}

/**
 * 统一的核心流式研判执行器
 * 严格执行契约：
 * 1. 自动判断发空值（不传或传空，绝不传 auto）
 * 2. 传递 user_id 以满足建单中断契约要求
 * 3. 消费 status, taxonomy, chunk, interrupt, done, error
 */
async function executeStreamChat(text, fileToSend, imgUrl, isSilentUserMsg = false, interruptReply = '') {
  if (analyzing.value) return

  // 用户发起新交互或回复时，收起旧中断卡片，避免重复点击
  messages.value.forEach((m) => {
    if (m.interrupt) m.interruptHandled = true
  })

  const token = localStorage.getItem('token')
  if (!token) {
    messages.value.push({
      role: 'assistant',
      content: '请先点击右上角【登录】后再使用多模态智能研判助手。',
    })
    return
  }

  if (!isSilentUserMsg) {
    messages.value.push({
      role: 'user',
      content: text || '请对此隐患影像进行安全研判与法规比对',
      image: imgUrl || '',
    })
    scrollToBottom()
    saveChatCache()
  } else if (interruptReply) {
    // 结构化确认不新增用户气泡，但本轮回复仍需要独立助手消息承接 chunk / 状态事件
    messages.value.push({
      role: 'assistant',
      content: '',
      taxonomyMismatchAccepted: false,
      suggestedActionHandled: false
    })
    scrollToBottom()
    saveChatCache()
  }

  analyzing.value = true
  if (typeof window !== 'undefined') window.__assistant_analyzing = true
  // 契约规定：前端不自作主张映射或自造营销词，初始兜底显示“处理中...”
  statusText.value = '处理中...'

  try {
    const fd = new FormData()
    fd.append('message', text || (interruptReply ? '' : '请对此隐患影像进行安全研判并出具整改建议'))
    fd.append('session_id', sessionId)
    if (interruptReply) fd.append('interrupt_reply', interruptReply)

    // 携带 user_id (任务创建契约必须)
    const userId = localStorage.getItem('userId')
    if (userId) {
      fd.append('user_id', userId)
    }

    // 规范第 1 条：「自动判断」必须发空值，绝对不能传 'auto' 或 'unknown'
    const majorCode = (selectedMajorCode.value || '').trim()
    if (majorCode && majorCode !== 'auto' && majorCode !== 'unknown') {
      fd.append('selected_major_code', majorCode)
    }

    if (fileToSend) {
      fd.append('file', fileToSend)
    }

    chatAbortController = new AbortController()
    const res = await fetch('/api/ai/assistant/stream', {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
      body: fd,
      signal: chatAbortController.signal,
    })

    if (!res.ok) {
      messages.value.push({ role: 'assistant', content: '研判服务连接受阻，请检查网络或稍后再试。' })
      analyzing.value = false
      return
    }

    const sid = res.headers.get('X-Session-Id')
    if (sid) {
      sessionId = sid
      localStorage.setItem('assistantSessionId', sessionId)
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let answer = ''
    let currentTaxonomy = null
    let currentInterrupt = null

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        let clean = line.trim()
        if (!clean.startsWith('data:')) continue
        clean = clean.replace(/^data:\s*/i, '').trim()
        if (!clean) continue
        try {
          const event = JSON.parse(clean)
          if (event.type === 'status') {
            // 契约第 3 条：只渲染 status.content，同轮内直接替换，空值兜底“处理中...”
            statusText.value = (event.content && typeof event.content === 'string' && event.content.trim())
              ? event.content.trim()
              : '处理中...'
          } else if (event.type === 'taxonomy') {
            // 规范第 2 条：消费 taxonomy 的 locked_* 与 suggested_major_code
            currentTaxonomy = event.content
            updateActiveLock(currentTaxonomy)
            const last = messages.value[messages.value.length - 1]
            if (last && last.role === 'assistant') {
              last.taxonomy = currentTaxonomy
              ensureInterruptDraft(last)
            }
          } else if (event.type === 'chunk') {
            statusText.value = ''
            answer += event.content
            const last = messages.value[messages.value.length - 1]
            if (last && last.role === 'assistant' && last.content === '') {
              last.content = answer
              if (currentTaxonomy) last.taxonomy = currentTaxonomy
            } else if (answer && messages.value[messages.value.length - 1]?.role === 'user') {
              messages.value.push({
                role: 'assistant',
                content: answer,
                taxonomy: currentTaxonomy,
                taxonomyMismatchAccepted: false,
                suggestedActionHandled: false
              })
            } else if (answer && messages.value[messages.value.length - 1]?.role === 'assistant') {
              messages.value[messages.value.length - 1].content = answer
              if (currentTaxonomy) messages.value[messages.value.length - 1].taxonomy = currentTaxonomy
            }
            scrollToBottom()
          } else if (event.type === 'interrupt') {
            // 消费中断事件：confirm_create_task 或 ask_address
            currentInterrupt = event.content
            const last = getOrCreateCurrentAssistantMessage()
            last.interrupt = currentInterrupt
            last.interruptHandled = false
            ensureInterruptDraft(last)
            scrollToBottom()
          } else if (event.type === 'task_accepted') {
            // 建单已受理：在当前助手消息上进入创建中状态，并按 request_id 轮询
            const taskAccepted = event.content || {}
            const requestId = taskAccepted.request_id || taskAccepted.requestId
            if (requestId) {
              const last = getOrCreateCurrentAssistantMessage()
              last.taskAccepted = taskAccepted
              rememberPendingHazardRequest(requestId)
              startHazardPolling(last, requestId)
              scrollToBottom()
            }
          } else if (event.type === 'task_created') {
            // 后端建单成功：把工单信息挂在当前这条助手消息上，渲染「查看工单」按钮
            const t = event.content || {}
            const last = messages.value[messages.value.length - 1]
            if (last && last.role === 'assistant') {
              last.taskCreated = t
            } else {
              // 顺序兜底：事件比正文先到
              messages.value.push({ role: 'assistant', content: '', taskCreated: t })
            }
            saveChatCache()
            scrollToBottom()
          } else if (event.type === 'error') {
            statusText.value = ''
            answer += (answer ? '\n' : '') + event.content
            messages.value.push({ role: 'assistant', content: answer, taxonomy: currentTaxonomy })
          } else if (event.type === 'done') {
            saveChatCache()
          }
        } catch (e) { }
      }
    }
  } catch (e) {
    console.error('研判请求异常', e)
    messages.value.push({ role: 'assistant', content: '连接异常，请重试。' })
  } finally {
    chatAbortController = null
    analyzing.value = false
    if (typeof window !== 'undefined') window.__assistant_analyzing = false
    statusText.value = ''
    saveChatCache()
  }
}

async function handleSend() {
  const text = inputText.value.trim()
  if ((!text && !selectedFile.value) || analyzing.value) return

  const fileToSend = selectedFile.value
  const imgUrl = previewUrl.value

  inputText.value = ''
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
  }
  selectedFile.value = null
  previewUrl.value = ''

  await executeStreamChat(text, fileToSend, imgUrl, false)
}

/**
 * 规范第 2 条：一键【改报 XX】行动按钮点击处理
 * 点击后将选择器设为该大类，并携带有新的 selected_major_code 重新发送
 */
async function switchAndResend(targetMajorCode, msg) {
  if (analyzing.value) return
  msg.suggestedActionHandled = true

  // 1. 设置选择器为目标大类 (大类中途改选，绝不清空聊天历史)
  selectedMajorCode.value = targetMajorCode

  // 2. 找到该条助手消息前紧邻的用户输入文本或图片
  let userText = ''
  let userImg = null
  const msgIdx = messages.value.indexOf(msg)
  if (msgIdx >= 0) {
    for (let i = msgIdx - 1; i >= 0; i--) {
      if (messages.value[i].role === 'user') {
        userText = messages.value[i].content
        userImg = messages.value[i].image
        break
      }
    }
  }

  if (!userText && !userImg) {
    userText = inputText.value.trim()
  }
  if (!userText && !userImg) {
    userText = `请改报【${getMajorLabelByCode(targetMajorCode)}】类隐患并研判`
  }

  // 3. 以新的 selected_major_code 重新发送
  await executeStreamChat(userText, null, userImg, false)
}

/**
 * 响应任务确认中断事件
 */
async function handleInterruptAction(msg, decision) {
  if (analyzing.value || !msg || !msg.interrupt) return
  const normalizedDecision = decision === 'decline' ? 'decline' : 'confirm'
  const interrupt = msg.interrupt
  msg.interruptHandled = true

  // 老后端没有 request_id/draft（或草稿为空）时保留纯文本兜底
  const draftCategoryList = interrupt.draft && Array.isArray(interrupt.draft.categoryList)
    ? interrupt.draft.categoryList.filter(Boolean)
    : []
  if (!interrupt.request_id || !interrupt.draft || !draftCategoryList.length) {
    await executeStreamChat(normalizedDecision === 'confirm' ? '好的' : '不用了', null, null, false)
    return
  }

  const draft = ensureInterruptDraft(msg) || interrupt.draft
  draft.address = String(draft.address || '').replace(/[\r\n\\]/g, ' ').trim()

  saveChatCache()
  await executeStreamChat('', null, null, true, JSON.stringify({
    decision: normalizedDecision,
    request_id: interrupt.request_id,
    draft
  }))
}

function renderMarkdown(text) {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/### (.+)/g, '<h4 class="msg-h4">$1</h4>')
    .replace(/## (.+)/g, '<h3 class="msg-h3">$1</h3>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="msg-strong">$1</strong>')
    .replace(/\n{2,}/g, '</p><p class="msg-p">')
    .replace(/\n/g, '<br/>')
}
</script>

<style scoped>
.home-view {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

/* 顶部通透白底导航 */
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  padding: 12px 24px;
}

.nav-container {
  max-width: 1280px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-logo {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.22);
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
  flex-shrink: 0;
}

.brand-logo:hover {
  transform: translateY(-1px) scale(1.03);
}

.brand-name {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.2px;
  display: flex;
  align-items: center;
}

.brand-text-mobile {
  display: none;
}

/* 顶部核心工具导航组 (统一Apple/Google Workspace风格的微胶囊) */
.nav-right {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-link {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 14px;
  border-radius: 9999px;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  text-decoration: none;
  background: transparent;
  border: 1px solid transparent;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  user-select: none;
}

.nav-icon-box {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.nav-link:hover {
  background: rgba(241, 245, 249, 0.95);
  color: #0f172a;
  border-color: rgba(0, 0, 0, 0.05);
  transform: translateY(-1.5px);
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.03);
}

.nav-link:hover .nav-icon-box {
  transform: scale(1.12);
}

.nav-link:active {
  transform: scale(0.96) translateY(0);
}

/* 激活态：高雅科技微蓝微光 */
.nav-link.active-link {
  background: #eff6ff;
  color: #1a73e8;
  font-weight: 600;
  border-color: rgba(26, 115, 232, 0.2);
  box-shadow: 0 2px 10px rgba(26, 115, 232, 0.15);
}

.nav-link.active-link .nav-icon-box {
  color: #1a73e8;
}

/* 工单处置/我的上报 专属微动态提示点 */
.task-nav-link .nav-icon-box {
  position: relative;
}

.nav-pulse-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #16a34a;
  box-shadow: 0 0 6px rgba(22, 163, 74, 0.8);
  animation: pulse-dot 2s infinite ease-in-out;
}

.nav-divider {
  width: 1px;
  height: 20px;
  background: rgba(0, 0, 0, 0.08);
  margin: 0 6px;
}

/* 现代高雅用户状态胶囊 */
.user-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 4px 8px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.user-pill:hover {
  background: #ffffff;
  border-color: rgba(191, 219, 254, 0.9);
  box-shadow: 0 4px 14px rgba(37, 99, 235, 0.08);
}

.user-avatar-badge {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid #bfdbfe;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  flex-shrink: 0;
}

.avatar-char {
  font-size: 11px;
  font-weight: 700;
  color: #1d4ed8;
  line-height: 1;
}

.user-avatar-badge .user-status-pulse {
  position: absolute;
  bottom: -1px;
  right: -1px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #16a34a;
  border: 1.5px solid #ffffff;
  box-shadow: 0 0 6px rgba(22, 163, 74, 0.8);
  flex-shrink: 0;
  animation: pulse-dot 2.4s infinite ease-in-out;
}

.user-name {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  letter-spacing: -0.2px;
}

.exit-pill-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 8px;
  border-radius: 9999px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 11.5px;
  cursor: pointer;
  transition: all 0.15s;
}

.exit-pill-btn:hover {
  background: #fee2e2;
  border-color: #fca5a5;
  color: #b91c1c;
}

.exit-pill-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 3px 10px;
  border-radius: 9999px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: #ffffff;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.exit-pill-btn:hover {
  background: #fef2f2;
  color: #ef4444;
  border-color: #fee2e2;
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.15);
  transform: scale(1.02);
}

.exit-pill-btn:active {
  transform: scale(0.94);
}

.login-nav-btn {
  padding: 6px 18px;
  font-size: 13px;
}

/* 核心主舞台 */
.main-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px 20px 60px;
  width: 100%;
}

.stage-container {
  width: 100%;
  max-width: 1520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  transition: all 0.3s ease;
}
.stage-container.has-conversation {
  justify-content: flex-start;
}

/* 动态问候标语 (Gemini 风格) */
.hero-greeting {
  text-align: center;
  margin-bottom: 32px;
}

.greeting-title {
  font-size: 38px;
  font-weight: 800;
  color: #0f172a;
  letter-spacing: -0.02em;
  margin-bottom: 10px;
}

.greeting-subtitle {
  font-size: 15px;
  color: #64748b;
  max-width: 720px;
  margin: 0 auto;
  line-height: 1.6;
}

/* 现代高质感微光流岛会话控制栏 */
.stream-toolbar {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px 8px 16px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border: 1px solid rgba(226, 232, 240, 0.9);
  box-shadow: 0 4px 20px -2px rgba(15, 23, 42, 0.05), 0 1px 2px rgba(0, 0, 0, 0.02);
  border-radius: 9999px;
  margin-bottom: 16px;
  transition: all 0.25s ease;
}

.stream-toolbar:hover {
  background: rgba(255, 255, 255, 0.98);
  border-color: rgba(191, 219, 254, 0.9);
  box-shadow: 0 6px 24px -2px rgba(37, 99, 235, 0.08), 0 2px 4px rgba(0, 0, 0, 0.03);
}

.session-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  color: #334155;
}

.status-indicator-ring {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: rgba(22, 163, 74, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-indicator-ring .pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #16a34a;
  box-shadow: 0 0 6px rgba(22, 163, 74, 0.6);
  animation: pulse-dot 1.8s infinite ease-in-out;
}

.session-label {
  font-weight: 600;
  color: #0f172a;
  letter-spacing: -0.2px;
}

.label-mobile {
  display: none;
}

.msg-counter {
  font-size: 11px;
  padding: 1.5px 8px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-weight: 600;
  letter-spacing: 0.2px;
}

/* 全新微光「新会话」高定胶囊按钮 */
.new-chat-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px 5px 10px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%);
  border: 1px solid rgba(191, 219, 254, 0.85);
  color: #1d4ed8;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 1px 4px rgba(37, 99, 235, 0.06);
  white-space: nowrap;
}

.new-chat-icon-box {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #eff6ff;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
  transition: transform 0.3s ease;
}

.new-chat-btn:hover {
  background: linear-gradient(135deg, #ffffff 0%, #e0effe 100%);
  border-color: #60a5fa;
  color: #1e40af;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.14);
}

.new-chat-btn:hover .new-chat-icon-box {
  transform: rotate(90deg);
  background: #dbeafe;
}

.new-chat-btn:active {
  transform: scale(0.97);
}

.btn-text-mobile {
  display: none;
}

/* 常驻锁定领域状态条 (规范第 2 条：locked_* 渲染"本对话正在记录：消防通道占用") */
.locked-status-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 18px;
  margin-bottom: 12px;
  border-radius: 12px;
  background: linear-gradient(135deg, rgba(239, 246, 255, 0.95) 0%, rgba(240, 253, 250, 0.9) 100%);
  border: 1px solid rgba(191, 219, 254, 0.85);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.05);
  backdrop-filter: blur(8px);
  animation: fadeIn 0.25s ease-out;
}

.locked-status-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.locked-pulse-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #2563eb;
  box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
  animation: pulse-dot 2s infinite;
}

.locked-icon {
  font-size: 13px;
}

.locked-title-text {
  font-size: 13px;
  color: #1e3a8a;
  font-weight: 500;
}

.locked-title-text strong {
  color: #1d4ed8;
  font-weight: 700;
}

.locked-status-right {
  display: flex;
  align-items: center;
}

.locked-rule-tip {
  font-size: 11.5px;
  color: #64748b;
  background: rgba(255, 255, 255, 0.7);
  padding: 2px 9px;
  border-radius: 6px;
  border: 1px dashed rgba(203, 213, 225, 0.9);
}

/* 对话流 */
.conversation-stream {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 24px;
}

.chat-row {
  display: flex;
  width: 100%;
}
.chat-row.user {
  justify-content: flex-end;
}
.chat-row.assistant {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 88%;
  padding: 14px 18px;
  border-radius: 18px;
  font-size: 14px;
  line-height: 1.65;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
}

.chat-row.user .chat-bubble {
  background: #eff6ff;
  color: #1e3a8a;
  border: 1px solid #dbeafe;
  border-bottom-right-radius: 4px;
}

.chat-row.assistant .chat-bubble {
  background: #ffffff;
  color: #0f172a;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-bottom-left-radius: 4px;
}

.bubble-image-wrap {
  margin-bottom: 8px;
  border-radius: 10px;
  overflow: hidden;
  max-width: 280px;
}
.bubble-img {
  width: 100%;
  height: auto;
  display: block;
}

.typing-bubble {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #1a73e8;
  font-size: 13px;
}
.gemini-sparkle {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #1a73e8;
  animation: pulse-dot 1.5s infinite;
}

:deep(.msg-h3) { font-size: 16px; font-weight: 700; color: #1a73e8; margin: 12px 0 6px; }
:deep(.msg-h4) { font-size: 14px; font-weight: 600; color: #0f172a; margin: 8px 0 4px; }
:deep(.msg-strong) { color: #1a73e8; font-weight: 600; }

/* 核心 Gemini 胶囊输入卡片 */
.gemini-input-card {
  width: 100%;
  background: #ffffff;
  border-radius: 28px;
  border: 1.5px solid rgba(26, 115, 232, 0.12);
  box-shadow: 0 8px 32px -4px rgba(0, 0, 0, 0.06), 0 3px 10px rgba(26, 115, 232, 0.04);
  padding: 18px 28px;
  margin: 8px 0;
  transition: all 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}
.gemini-input-card.is-focused, .gemini-input-card:hover {
  border-color: rgba(26, 115, 232, 0.45);
  box-shadow: 0 12px 38px -4px rgba(26, 115, 232, 0.18), 0 4px 12px rgba(0, 0, 0, 0.05);
}
.gemini-input-card.dragover {
  border-color: #1a73e8;
  background: #f8fafd;
}

/* 会话中隐患分类识别与非阻塞提醒横幅 */
.msg-taxonomy-zone {
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.taxonomy-mismatch-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 10px;
  background: #fffbeb;
  border: 1px solid #fef3c7;
  font-size: 12px;
  color: #b45309;
  animation: fadeIn 0.2s ease-out;
}
.mismatch-icon { font-size: 13px; }
.mismatch-text { flex: 1; font-weight: 500; }
.mismatch-actions { display: flex; align-items: center; gap: 6px; }
.mismatch-btn {
  background: transparent;
  border: none;
  font-size: 11.5px;
  font-weight: 700;
  cursor: pointer;
  padding: 1px 4px;
}
.mismatch-btn.accept-btn { color: #16a34a; }
.mismatch-btn.modify-btn { color: #2563eb; }
.mismatch-btn:hover { text-decoration: underline; }

.taxonomy-issues-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.taxonomy-issue-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 6px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #166534;
  font-size: 11px;
  font-weight: 600;
}

/* 跨领域偏离提醒与一键【改报 XX】行动横幅 (规范核心第 2 条) */
.suggested-major-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%);
  border: 1px solid #fde68a;
  box-shadow: 0 2px 6px rgba(245, 158, 11, 0.1);
  animation: fadeIn 0.25s ease-out;
}

.suggested-major-info {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: #92400e;
  flex: 1;
}

.suggested-icon {
  font-size: 14px;
}

.suggested-text strong {
  color: #b45309;
  font-weight: 700;
}

.re-report-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #ea580c 0%, #d97706 100%);
  color: #ffffff;
  border: none;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(234, 88, 12, 0.25);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  flex-shrink: 0;
}

.re-report-btn:hover {
  background: linear-gradient(135deg, #c2410c 0%, #b45309 100%);
  box-shadow: 0 4px 10px rgba(234, 88, 12, 0.35);
  transform: translateY(-1px);
}

.re-report-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

/* 即时险情安全避险提示 */
.immediate-danger-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%);
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 12px;
  font-weight: 500;
  animation: fadeIn 0.2s ease-out;
}

.immediate-danger-banner .danger-icon {
  font-size: 15px;
}

.immediate-danger-banner .danger-text {
  line-height: 1.4;
  font-weight: 600;
}

/* 任务确认中断事件决策卡片 */
.interrupt-confirm-card {
  margin-top: 10px;
  padding: 10px 14px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #dbeafe;
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.08);
  animation: fadeIn 0.25s ease-out;
}

.interrupt-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.interrupt-icon {
  font-size: 14px;
}

.interrupt-question {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.interrupt-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.interrupt-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  border: none;
}

.interrupt-btn.confirm-btn {
  background: #2563eb;
  color: #ffffff;
}

.interrupt-btn.confirm-btn:hover {
  background: #1d4ed8;
  transform: translateY(-1px);
}

.interrupt-btn.cancel-btn {
  background: #f1f5f9;
  color: #64748b;
  border: 1px solid #e2e8f0;
}

.interrupt-btn.cancel-btn:hover {
  background: #e2e8f0;
  color: #334155;
}

.interrupt-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
}

/* 确认建单卡片内的可编辑字段 */
.interrupt-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 8px;
  margin-bottom: 10px;
}

.interrupt-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.interrupt-field-wide {
  grid-column: 1 / -1;
}

.interrupt-field-label {
  font-size: 11.5px;
  font-weight: 500;
  color: #64748b;
}

.interrupt-input,
.interrupt-textarea {
  width: 100%;
  box-sizing: border-box;
  padding: 6px 9px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #ffffff;
  color: #1e293b;
  font: inherit;
  font-size: 12px;
  line-height: 1.45;
  outline: none;
  transition: border-color 0.18s ease;
}

.interrupt-input {
  height: 31px;
}

.interrupt-textarea {
  min-height: 52px;
  resize: vertical;
}

.interrupt-input:focus,
.interrupt-textarea:focus {
  border-color: #93c5fd;
}

.interrupt-input::placeholder,
.interrupt-textarea::placeholder {
  color: #94a3b8;
}

.interrupt-image-row {
  grid-column: 1 / -1;
}

.interrupt-image-thumb {
  display: block;
  width: 64px;
  height: 64px;
  object-fit: cover;
  border: 1px solid #dbeafe;
  border-radius: 8px;
}

.task-create-status {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.45;
}

.task-create-status.is-creating {
  color: #2563eb;
}

.task-create-status.is-error {
  color: #b91c1c;
}

.task-create-status.is-muted {
  color: #64748b;
}

@media (max-width: 640px) {
  .interrupt-form {
    grid-template-columns: 1fr;
  }

  .interrupt-field-wide,
  .interrupt-image-row {
    grid-column: auto;
  }
}

/* 输入卡片顶部辅助条 (缩略图与大类胶囊) */
.input-top-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 6px;
  position: relative;
}

.major-hint-row {
  position: relative;
}
.major-selector-capsule {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 9999px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  font-size: 11.5px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s ease;
  user-select: none;
}
.major-selector-capsule:hover {
  background: #e2e8f0;
  color: #1a73e8;
  border-color: #cbd5e1;
}
.selector-icon { font-size: 11px; }
.selector-label { font-weight: 600; }
.remove-major-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 10px;
  cursor: pointer;
  padding: 0 2px;
  border-radius: 50%;
}
.remove-major-btn:hover { color: #ef4444; }
.caret-arrow { font-size: 9px; color: #94a3b8; margin-left: 2px; }

/* 大类选择下拉菜单 */
.major-dropdown-menu {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 50;
  width: 290px;
  padding: 12px;
  background: #ffffff;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  animation: fadeIn 0.18s cubic-bezier(0.16, 1, 0.3, 1);
}
.dropdown-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f1f5f9;
}
.close-dropdown-btn {
  background: transparent;
  border: none;
  color: #94a3b8;
  cursor: pointer;
  font-size: 12px;
}
.close-dropdown-btn:hover { color: #0f172a; }

.dropdown-chips-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.dropdown-chip {
  padding: 4px 10px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-size: 11px;
  color: #475569;
  cursor: pointer;
  transition: all 0.15s;
}
.dropdown-chip:hover {
  background: #eff6ff;
  color: #1a73e8;
  border-color: #bfdbfe;
}
.dropdown-chip.active {
  background: #1a73e8;
  color: #ffffff;
  border-color: #1a73e8;
  font-weight: 600;
}

/* 缩略图胶囊 */
.selected-image-capsule {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px 2px 4px;
  border-radius: 9999px;
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
}
.capsule-thumb {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  object-fit: cover;
}
.capsule-tip {
  font-size: 11px;
  color: #475569;
  font-weight: 500;
}
.capsule-remove {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: #cbd5e1;
  color: #334155;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.capsule-remove:hover {
  background: #94a3b8;
  color: #fff;
}

/* 中部核心大面积多行文本书写区 */
.input-editor-zone {
  width: 100%;
  display: flex;
  margin-bottom: 8px;
}

.gemini-textarea {
  width: 100%;
  border: none;
  background: transparent;
  outline: none;
  resize: none;
  font-size: 16px;
  color: #0f172a;
  font-family: inherit;
  padding: 6px 2px;
  line-height: 1.65;
  min-height: 96px;
  max-height: 240px;
  box-sizing: border-box;
}
.gemini-textarea::placeholder {
  color: #94a3b8;
  font-size: 15px;
}

/* 底部操作工具栏 */
.input-bottom-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
}

.bottom-tools-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.attach-pill-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 9999px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  color: #334155;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.02);
}
.attach-pill-btn:hover {
  background: #eff6ff;
  color: #1a73e8;
  border-color: rgba(26, 115, 232, 0.35);
  transform: translateY(-1.5px);
  box-shadow: 0 3px 10px rgba(26, 115, 232, 0.12);
}
.attach-pill-btn:active {
  transform: scale(0.95);
}

.model-badge-capsule {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 7px 13px;
  border-radius: 9999px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  font-size: 12px;
  color: #475569;
  font-weight: 600;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.model-badge-capsule:hover {
  border-color: rgba(26, 115, 232, 0.3);
  background: #eff6ff;
  color: #1a73e8;
}
.sparkle-icon {
  color: #1a73e8;
  font-size: 13px;
}

.bottom-actions-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.shortcut-tip {
  font-size: 12px;
  color: #94a3b8;
  user-select: none;
}

.send-pill-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px;
  border-radius: 9999px;
  border: none;
  background: linear-gradient(135deg, #1a73e8 0%, #2563eb 100%);
  color: #ffffff;
  font-size: 13.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 4px 14px rgba(26, 115, 232, 0.32);
}
.send-pill-btn:hover:not(:disabled) {
  transform: translateY(-1.5px) scale(1.02);
  background: linear-gradient(135deg, #1557b0 0%, #1d4ed8 100%);
  box-shadow: 0 6px 20px rgba(26, 115, 232, 0.45);
}
.send-pill-btn:active:not(:disabled) {
  transform: scale(0.95);
}
.send-pill-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  box-shadow: none;
  transform: none;
}

/* 底部专业影像深度工作台直通区域 */
.suggestions-zone {
  width: 100%;
  margin-top: 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

/* 旗舰级专业影像研判工作台直通看板 */
.direct-workbench-banner {
  width: 100%;
  padding: 16px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, rgba(248, 250, 252, 0.95) 100%);
  border-radius: 18px;
  border: 1px solid rgba(26, 115, 232, 0.16);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.03), 0 1px 3px rgba(26, 115, 232, 0.04);
  transition: all 0.26s cubic-bezier(0.16, 1, 0.3, 1);
  position: relative;
  overflow: hidden;
}

.direct-workbench-banner:hover {
  transform: translateY(-2px);
  border-color: rgba(26, 115, 232, 0.45);
  box-shadow: 0 8px 28px rgba(26, 115, 232, 0.12), 0 2px 6px rgba(0, 0, 0, 0.04);
}

.direct-workbench-banner:active {
  transform: scale(0.99) translateY(0);
}

.banner-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.banner-icon-wrapper {
  position: relative;
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.banner-icon-bg {
  width: 44px;
  height: 44px;
  border-radius: 14px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid rgba(26, 115, 232, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 3px 10px rgba(26, 115, 232, 0.15);
  position: relative;
  z-index: 2;
  transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1);
}

.direct-workbench-banner:hover .banner-icon-bg {
  transform: scale(1.08) rotate(-2deg);
}

.icon-pulse-glow {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: 16px;
  border: 1.5px solid rgba(26, 115, 232, 0.4);
  animation: hallPulse 2.6s infinite cubic-bezier(0.25, 0.8, 0.25, 1);
  z-index: 1;
}

.banner-texts {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.banner-title-line {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.banner-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.2px;
}

.pro-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  border: 1px solid rgba(26, 115, 232, 0.25);
  color: #1a73e8;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.2px;
}

.pro-badge .sparkle-icon {
  font-size: 11px;
}

.banner-feature-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
}

.feature-chip {
  color: #475569;
  font-weight: 500;
}

.chip-separator {
  color: #cbd5e1;
  font-size: 10px;
}

/* 右侧行动按钮：果冻微光胶囊 */
.banner-cta-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #1a73e8 0%, #2563eb 100%);
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  box-shadow: 0 4px 14px rgba(26, 115, 232, 0.28);
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  flex-shrink: 0;
}

.direct-workbench-banner:hover .banner-cta-btn {
  background: linear-gradient(135deg, #1557b0 0%, #1d4ed8 100%);
  box-shadow: 0 6px 18px rgba(26, 115, 232, 0.38);
  transform: translateY(-1px);
}

.mobile-text {
  display: none;
}

.cta-arrow-box {
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.direct-workbench-banner:hover .cta-arrow-box {
  transform: translateX(4px);
}

/* 手机端与小屏响应式适配 */
@media (max-width: 767px) {
  .navbar {
    padding: 8px 12px;
  }
  .brand-logo {
    width: 30px;
    height: 30px;
    border-radius: 8px;
  }
  .brand-logo svg {
    width: 22px;
    height: 22px;
  }
  .brand-text-desktop {
    display: none !important;
  }
  .brand-text-mobile {
    display: inline !important;
    font-size: 15px !important;
    font-weight: 700 !important;
    letter-spacing: -0.3px !important;
    color: #0f172a !important;
  }
  /* 移动端顶部核心工具导航收归到底部导航栏 */
  .nav-right .nav-link,
  .nav-right .nav-divider {
    display: none !important;
  }
  .nav-right {
    gap: 6px;
  }
  /* 移动端上方用户名展示优化：优雅头像、自适应宽度、精致退出键 */
  .user-pill {
    padding: 3px 6px 3px 6px !important;
    gap: 6px !important;
    border-radius: 9999px !important;
    background: rgba(255, 255, 255, 0.95) !important;
  }
  .user-avatar-badge {
    width: 20px !important;
    height: 20px !important;
  }
  .avatar-char {
    font-size: 10px !important;
  }
  .user-name {
    max-width: 85px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    overflow: hidden !important;
    text-overflow: ellipsis !important;
    white-space: nowrap !important;
  }
  .exit-pill-btn {
    padding: 2px 6px !important;
    font-size: 11px !important;
  }
  .exit-pill-btn svg {
    width: 10px !important;
    height: 10px !important;
  }
  /* 会话工具条移动端自适应 (告别生硬，轻量灵动) */
  .stream-toolbar {
    padding: 6px 10px 6px 12px !important;
    margin-bottom: 12px !important;
  }
  .label-desktop {
    display: none !important;
  }
  .label-mobile {
    display: inline !important;
    font-size: 12px !important;
  }
  .msg-counter {
    font-size: 10px !important;
    padding: 1px 6px !important;
  }
  .new-chat-btn {
    padding: 4px 10px 4px 8px !important;
    font-size: 11.5px !important;
  }
  .new-chat-icon-box {
    width: 16px !important;
    height: 16px !important;
  }
  .new-chat-icon-box svg {
    width: 10px !important;
    height: 10px !important;
  }
  .btn-text-desktop {
    display: none !important;
  }
  .btn-text-mobile {
    display: inline !important;
  }

  .main-stage {
    padding: 12px 10px 24px;
    justify-content: flex-start;
  }
  .hero-greeting {
    margin-bottom: 12px !important;
  }
  .greeting-title {
    font-size: clamp(18px, 5.2vw, 23px) !important;
    margin-bottom: 4px !important;
  }
  .greeting-subtitle {
    font-size: 11.5px !important;
    line-height: 1.45 !important;
    max-width: 92% !important;
  }

  .gemini-input-card {
    border-radius: 20px;
    padding: 12px 14px !important;
  }
  .gemini-textarea {
    font-size: 14.5px !important;
    padding: 4px 2px !important;
    min-height: 64px !important;
    line-height: 1.5 !important;
  }
  .gemini-textarea::placeholder {
    font-size: 13px !important;
  }
  .input-bottom-bar {
    padding-top: 8px;
  }
  .attach-pill-btn {
    padding: 6px 10px;
    font-size: 12px;
  }
  .model-badge-capsule {
    display: none;
  }
  .shortcut-tip {
    display: none !important;
  }
  .send-pill-btn {
    padding: 7px 14px;
    font-size: 12.5px;
  }

  .suggestions-zone {
    margin-top: 12px !important;
  }

  .direct-workbench-banner {
    padding: 12px 14px !important;
    gap: 10px;
    border-radius: 14px;
  }
  .banner-left {
    gap: 10px;
    min-width: 0;
    flex: 1;
  }
  .banner-icon-wrapper {
    width: 38px;
    height: 38px;
  }
  .banner-icon-bg {
    width: 36px;
    height: 36px;
    border-radius: 10px;
  }
  .banner-icon-bg svg {
    width: 18px;
    height: 18px;
  }
  .banner-texts {
    min-width: 0;
    gap: 3px;
  }
  .banner-title-line {
    gap: 6px;
  }
  .banner-title {
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .pro-badge {
    padding: 1px 6px;
    font-size: 9.5px;
  }
  .banner-feature-chips {
    display: none !important;
  }
  .banner-cta-btn {
    padding: 7px 12px !important;
    font-size: 12px !important;
    border-radius: 20px;
    gap: 4px;
    flex-shrink: 0;
  }
  .desktop-text {
    display: none !important;
  }
  .mobile-text {
    display: inline !important;
  }
  .cta-text {
    font-size: 11.5px;
  }
  .cta-arrow-box svg {
    width: 11px;
    height: 11px;
  }

  .conversation-stream {
    padding: 0 4px;
  }
  .chat-bubble {
    max-width: 95% !important;
    font-size: 13px;
    padding: 10px 12px !important;
  }
  .locked-status-strip {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
    padding: 8px 12px;
  }
  .suggested-major-banner {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  .re-report-btn {
    align-self: flex-end;
  }
}
.highlight-task {
  background: #f0fdf4;
  color: #16a34a;
  font-weight: 600;
}
.highlight-task:hover {
  background: #dcfce7;
  color: #15803d;
}
.text-muted {
  color: #94a3b8;
  font-size: 12px;
}

/* ask_address 追问提示样式 */
.interrupt-hint-row {
  padding: 8px 12px;
  border-radius: 8px;
  background: #f8fafc;
  border: 1px dashed #cbd5e1;
}

.interrupt-hint {
  font-size: 12px;
  color: #475569;
  line-height: 1.5;
}

/* 建单成功后「查看工单」行动条 (消费 task_created 事件) */
.task-created-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
}

.task-created-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 16px 7px 12px;
  border-radius: 9999px;
  background: linear-gradient(135deg, #f0fdf4 0%, #e0f2fe 100%);
  border: 1px solid rgba(187, 247, 208, 0.9);
  color: #15803d;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.08);
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.task-btn-icon-wrap {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(22, 163, 74, 0.12);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #16a34a;
  flex-shrink: 0;
}

.task-created-code {
  font-size: 11.5px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid rgba(134, 239, 172, 0.6);
  color: #166534;
  letter-spacing: 0.2px;
}

.task-btn-arrow {
  color: #15803d;
  transition: transform 0.2s ease;
}

.task-created-btn:hover {
  background: linear-gradient(135deg, #dcfce7 0%, #bae6fd 100%);
  border-color: #86efac;
  color: #14532d;
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(22, 163, 74, 0.18);
}

.task-created-btn:hover .task-btn-arrow {
  transform: translateX(2px);
}

.task-created-btn:active {
  transform: scale(0.98);
}

</style>




