<template>
  <div class="hazard-list-view">
    <div class="content-wrapper">
      <!-- 头部操作与导航栏 -->
      <header class="page-header">
        <div class="header-left">
          <router-link to="/" class="back-btn" title="返回主控中心">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <span>返回主控</span>
          </router-link>
          <div class="header-titles">
            <div class="system-tag">
              <span class="status-indicator-dot"></span>
              <span class="role-badge">{{ roleBadgeText }}</span>
              <span>三明市城市安全综合治理工单系统</span>
            </div>
            <h1 class="page-title">{{ pageTitleText }}</h1>
          </div>
        </div>

        <div class="header-right">
          <router-link to="/map" class="map-shortcut btn-pill-secondary">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/>
              <line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/>
            </svg>
            <span>空间地图态势</span>
          </router-link>
          <button class="refresh-btn btn-pill-secondary" :disabled="loading" @click="fetchHazards">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="{ 'spin-anim': loading }">
              <polyline points="23 4 23 10 17 10"/>
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
            </svg>
            <span>刷新任务</span>
          </button>
        </div>
      </header>

      <!-- 管理员全域治理指标看板 (含已撤回统计指标) -->
      <section v-if="userRole === '1' && adminStats" class="admin-stats-bar glass-card animate-fade-in-up">
        <div class="stat-pill-item">
          <span class="stat-pill-label">治理工单总量</span>
          <span class="stat-pill-val num-font">{{ adminStats.total ?? '--' }}</span>
        </div>
        <div class="stat-pill-divider"></div>
        <div class="stat-pill-item">
          <span class="stat-pill-label">现场处置中</span>
          <span class="stat-pill-val num-font text-warning">{{ adminStats.processing ?? '--' }}</span>
        </div>
        <div class="stat-pill-divider"></div>
        <div class="stat-pill-item">
          <span class="stat-pill-label">已核准办结</span>
          <span class="stat-pill-val num-font text-success">{{ adminStats.processed ?? '--' }}</span>
        </div>
        <div class="stat-pill-divider"></div>
        <div class="stat-pill-item">
          <span class="stat-pill-label">综合治理率</span>
          <span class="stat-pill-val num-font text-primary">{{ adminStats.rate ?? '--' }}</span>
        </div>
        <div class="stat-pill-divider"></div>
        <div class="stat-pill-item stat-pill-withdrawn" :class="{ active: selectedStatus === 5 }" @click="selectedStatus = 5" title="点击筛选已撤回工单">
          <span class="stat-pill-label">已撤回工单</span>
          <span class="stat-pill-val num-font text-muted">{{ adminStats.withdrawn ?? 0 }}</span>
          <span class="stat-pill-tip">不计入考核</span>
        </div>
      </section>

      <!-- 普通市民专属视角切换栏：我的上报记录 与 全城治理公示 -->
      <section v-if="userRole === '0'" class="citizen-view-switcher glass-card">
        <div class="switcher-pills">
          <button
            type="button"
            class="switcher-pill-btn"
            :class="{ active: filterViewMode === 'mine' }"
            @click="switchViewMode('mine')"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
              <circle cx="12" cy="7" r="4"/>
            </svg>
            <span class="pill-text">我的上报记录</span>
            <span class="pill-count num-font">{{ myReportCount }}</span>
          </button>
          <button
            type="button"
            class="switcher-pill-btn"
            :class="{ active: filterViewMode === 'public' }"
            @click="switchViewMode('public')"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="2" y1="12" x2="22" y2="12"/>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
            <span class="pill-text">全城治理公示</span>
            <span class="pill-tag">公开成果</span>
          </button>
        </div>
        <div class="switcher-tip">
          <span v-if="filterViewMode === 'mine'">展示您作为热心市民巡查上报的现场隐患处理全流程</span>
          <span v-else>查阅三明市全域已现场整改达标、实地复核闭环的安全治理实况</span>
        </div>
      </section>

      <!-- 筛选工具条：状态 Tabs + 类别 Chips + 管理员快捷全选 -->
      <section class="filters-bar glass-card">
        <!-- 状态流转 Tabs (在全城公示模式下智能收起流转状态) -->
        <div v-if="!(userRole === '0' && filterViewMode === 'public')" class="status-tabs">
          <button
            v-for="tab in statusTabs"
            :key="tab.val"
            class="status-tab-btn"
            :class="{
              active: selectedStatus === tab.val,
              'tab-pending-review': tab.val === 30,
              'tab-reject': tab.val === 4,
              'tab-withdrawn': tab.val === 5
            }"
            @click="selectedStatus = tab.val"
          >
            <span class="tab-label">{{ tab.label }}</span>
            <span class="tab-count num-font" :class="{ 'highlight-badge': tab.val === 30 && getStatusCount(30) > 0 }">
              {{ getStatusCount(tab.val) }}
            </span>
          </button>
        </div>

        <!-- 分割线 (在全城公示模式下智能隐藏) -->
        <div v-if="!(userRole === '0' && filterViewMode === 'public')" class="filter-divider"></div>

        <!-- 两级类别联动筛选 Chips + 管理员批量操作快捷触发 -->
        <div class="filter-bottom-row">
          <div class="taxonomy-filter-wrapper">
            <!-- 一级大类 Chips -->
            <div class="category-chips major-chips touch-scroll-x no-scrollbar">
              <span class="filter-caption">隐患领域：</span>
              <button
                v-for="major in majorCategoryOptions"
                :key="major.code"
                class="chip-btn"
                :class="{ active: selectedMajorCode === major.code }"
                @click="selectMajor(major.code)"
              >
                {{ major.label }}
              </button>
            </div>

            <!-- 二级细分 Chips (选定特定大类时平滑展示) -->
            <div v-if="selectedMajorCode !== 'all' && currentSubcategories.length > 0" class="category-chips sub-chips touch-scroll-x no-scrollbar">
              <span class="filter-caption sub-caption">细分类型：</span>
              <button
                class="chip-btn sub-chip-btn"
                :class="{ active: selectedSubcategoryCode === 'all' }"
                @click="selectSubcategory('all')"
              >
                全部
              </button>
              <button
                v-for="sub in currentSubcategories"
                :key="sub.code"
                class="chip-btn sub-chip-btn"
                :class="{ active: selectedSubcategoryCode === sub.code }"
                @click="selectSubcategory(sub.code)"
              >
                {{ sub.label }}
              </button>
            </div>
          </div>

          <!-- 管理员快速批选控制 -->
          <div v-if="userRole === '1'" class="admin-quick-select">
            <button
              type="button"
              class="quick-select-btn"
              :class="{ active: isAllCurrentPageSelected, disabled: !currentPagePendingCount }"
              :disabled="!currentPagePendingCount"
              @click="toggleSelectAllCurrentPage"
              :title="currentPagePendingCount ? '全选/取消当前页所有待验收工单' : '当前页暂无可审批的待验收工单'"
            >
              <input
                type="checkbox"
                :checked="isAllCurrentPageSelected"
                :disabled="!currentPagePendingCount"
                @click.stop="toggleSelectAllCurrentPage"
                class="header-checkbox"
              />
              <span>全选当前页待验收 ({{ currentPagePendingCount }})</span>
            </button>
            <button
              v-if="pendingReviewCount > 0"
              type="button"
              class="quick-select-btn select-pending-btn"
              @click="selectAllPendingReview"
            >
              <span>快速选中全部待验收 ({{ pendingReviewCount }})</span>
            </button>
          </div>
        </div>
      </section>

      <!-- 核心内容展示区 -->
      <main class="main-content">
        <!-- 加载中 -->
        <div v-if="loading" class="state-card glass-card">
          <div class="spinner"></div>
          <p>正在同步全域隐患处置工单流水...</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMessage" class="state-card glass-card error-card">
          <p class="error-msg">{{ errorMessage }}</p>
          <button class="btn-pill btn-pill-primary" @click="fetchHazards">重新加载</button>
        </div>

        <!-- 场景A：普通市民未上报记录时的【城市安全共治引导大厅】看板 (消灭生硬空白) -->
        <div
          v-else-if="userRole === '0' && filterViewMode === 'mine' && (!filteredHazards.length || !hazards.length)"
          class="citizen-hall-card glass-card animate-fade-in-up"
        >
          <div class="hall-badge-wrap">
            <div class="hall-shield-badge">
              <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                <path d="m9 12 2 2 4-4"/>
              </svg>
            </div>
            <div class="hall-pulse-ring"></div>
          </div>
          
          <div class="hall-header-group">
            <span class="hall-pill-tag">人人有责 · 全民共治</span>
            <h2 class="hall-title">三明市城市安全 · 市民共治服务大厅</h2>
            <p class="hall-subtitle">您暂未提交过现场隐患记录，让安全防线延伸至城市每一个角落</p>
          </div>
          
          <p class="hall-intro">
            当您在日常出行或工作生活中发现路面坍塌、消防通道占用、井盖破损、危树倒伏等各类隐患时，可随时拍照上报。网格处置专员将第一时间响应排险，处置全流程在此向您透明溯源。
          </p>

          <!-- 四步治理闭环指示图示 -->
          <div class="governance-steps-grid">
            <div class="step-card">
              <div class="step-badge">第 1 步</div>
              <div class="step-icon">📸</div>
              <div class="step-name">现场拍照取证</div>
              <div class="step-desc">随时拍摄现场照片，自动定位经纬度</div>
            </div>
            <div class="step-card">
              <div class="step-badge">第 2 步</div>
              <div class="step-icon">⚡</div>
              <div class="step-name">AI 智能研判</div>
              <div class="step-desc">多模态大模型秒级定性并匹配法律法规</div>
            </div>
            <div class="step-card">
              <div class="step-badge">第 3 步</div>
              <div class="step-icon">👷</div>
              <div class="step-name">网格专员排险</div>
              <div class="step-desc">调度指派责任专员，现场施工整治清零</div>
            </div>
            <div class="step-card">
              <div class="step-badge">第 4 步</div>
              <div class="step-icon">🛡️</div>
              <div class="step-name">终审复核闭环</div>
              <div class="step-desc">指挥中心实地复核合格，结果全流程透明反馈</div>
            </div>
          </div>

          <!-- 双通道核心行动按钮 -->
          <div class="hall-actions">
            <button type="button" class="btn-hall-primary" @click="goToReport">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                <circle cx="12" cy="13" r="4"/>
              </svg>
              <span>立即现场拍照取证上报</span>
            </button>
            <button type="button" class="btn-hall-secondary" @click="switchViewMode('public')">
              <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="2" y1="12" x2="22" y2="12"/>
                <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
              </svg>
              <span>查阅全城治理成效公示</span>
            </button>
          </div>
        </div>

        <!-- 场景B：管理员/专员视角或有筛选条件下的标准空态 -->
        <div v-else-if="!filteredHazards.length" class="state-card glass-card">
          <div class="empty-icon-circle">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="1.6">
              <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/>
              <rect x="8" y="2" width="8" height="4" rx="1" ry="1"/>
            </svg>
          </div>
          <h3 class="empty-title">当前无匹配的隐患工单</h3>
          <p class="empty-desc">当前筛选条件下暂无工单记录，请切换状态标签或稍后刷新查看。</p>
          <button class="btn-pill btn-pill-primary mt-3" @click="resetFilters">查看全部工单</button>
        </div>

        <!-- 工单卡片列表 -->
        <div v-else class="hazard-items-list">
          <article
            v-for="item in filteredHazards"
            :key="item.id"
            class="hazard-card glass-card animate-fade-in-up"
            :class="{
              'card-selected': isSelected(item.id),
              'card-pending-review': isPendingReview(item)
            }"
          >
            <!-- 管理员勾选框：仅待验收工单可勾选终审 -->
            <div v-if="userRole === '1'" class="card-select-cell">
              <div
                v-if="isPendingReview(item)"
                class="custom-checkbox"
                :class="{ checked: isSelected(item.id) }"
                title="勾选此工单参与批量终审验收/驳回"
                @click.stop="toggleSelect(item.id)"
              >
                <svg v-if="isSelected(item.id)" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              </div>
              <div
                v-else
                class="custom-checkbox disabled-checkbox"
                :title="item.status === 3 && item.reviewed === 1 ? '该工单已办结归档，无需再次审批' : '非待验收工单，暂不支持终审审批'"
                @click.stop
              >
                <span class="disabled-dot"></span>
              </div>
            </div>

            <!-- 左侧缩略图与编号 -->
            <div class="card-thumb-area" @click="viewDetail(item.id)">
              <SecureImage v-if="item.imageUrl" :src="item.imageUrl" alt="现场隐患" class="thumb-img" />
              <div v-else class="no-thumb">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.8">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                  <circle cx="12" cy="13" r="4"/>
                </svg>
                <span>无现场影像</span>
              </div>
            </div>

            <!-- 中间核心信息区 -->
            <div class="card-main-info" @click="viewDetail(item.id)">
              <div class="info-top-row">
                <!-- 状态徽章 (精细支持待验收与已办结) -->
                <span class="status-pill" :class="getStatusBadgeClass(item)">
                  <span class="dot"></span>
                  <span>{{ formatStatusText(item) }}</span>
                </span>

                <!-- 类别胶囊：复合隐患同级并列展示 -->
                <span
                  v-for="cat in resolveHazardList(item.hazardTypes)"
                  :key="`${cat.majorCode}/${cat.subcategoryCode}`"
                  class="category-pill"
                >{{ cat.displayText }}</span>

                <!-- 发生地址 -->
                <div class="address-text" :title="item.address">
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                    <circle cx="12" cy="10" r="3"/>
                  </svg>
                  <span>{{ item.address || '三明市辖区未定具体门牌' }}</span>
                </div>
              </div>

              <!-- 隐患描述 -->
              <p class="hazard-desc-text">{{ item.description || '现场隐患巡查取证记录，等待责任专员进行现场处置。' }}</p>

              <!-- 底部追溯元信息 -->
              <div class="meta-bottom-row">
                <span class="meta-item">
                  <span class="lbl">上报来源：</span>
                  <span class="val">市民上报</span>
                </span>
                <span class="meta-item">
                  <span class="lbl">责任人：</span>
                  <span class="val" :class="item.handlerId ? 'highlight-handler' : 'text-muted'">
                    {{ item.handlerId ? '已指派专员' : '待调度派单' }}
                  </span>
                </span>
                <span v-if="item.reviewRemark" class="meta-item review-meta-item" :title="item.reviewRemark">
                  <span class="lbl">审查意见：</span>
                  <span class="val review-val">{{ item.reviewRemark }}</span>
                </span>
                <span v-if="item.withdrawnReason" class="meta-item review-meta-item" :title="item.withdrawnReason">
                  <span class="lbl">撤回原因：</span>
                  <span class="val review-val">{{ item.withdrawnReason }}</span>
                </span>
                <span class="meta-item date-val num-font">
                  {{ formatDate(item.createTime) }}
                </span>
              </div>

              <!-- 顺丰物流式透明全生命周期步进轴 (面向普通市民或全城公示) -->
              <div v-if="userRole === '0'" class="logistic-timeline-bar" :class="{ 'is-rejected': item.status === 4 }">
                <div class="timeline-track">
                  <!-- 节点 1：已上报立案 -->
                  <div class="timeline-node" :class="{ completed: isStepCompleted(item, 1), current: isStepCurrent(item, 1) }">
                    <div class="node-dot">
                      <span v-if="isStepCompleted(item, 1)" class="check-mark">✓</span>
                      <span v-else class="dot-num">1</span>
                    </div>
                    <div class="node-text">
                      <span class="node-label">已上报立案</span>
                      <span class="node-sub">市民取证上报</span>
                    </div>
                  </div>

                  <div class="timeline-line" :class="{ active: isStepLineActive(item, 1) }"></div>

                  <!-- 节点 2：已受理派单 -->
                  <div class="timeline-node" :class="{ completed: isStepCompleted(item, 2), current: isStepCurrent(item, 2) }">
                    <div class="node-dot">
                      <span v-if="isStepCompleted(item, 2)" class="check-mark">✓</span>
                      <span v-else class="dot-num">2</span>
                    </div>
                    <div class="node-text">
                      <span class="node-label">{{ item.handlerId ? '专员已受理' : '调度派单中' }}</span>
                      <span class="node-sub">{{ item.handlerId ? '已指派专员' : '待指派' }}</span>
                    </div>
                  </div>

                  <div class="timeline-line" :class="{ active: isStepLineActive(item, 2) }"></div>

                  <!-- 节点 3：排险施治中 -->
                  <div class="timeline-node" :class="{ completed: isStepCompleted(item, 3), current: isStepCurrent(item, 3) }">
                    <div class="node-dot">
                      <span v-if="isStepCompleted(item, 3)" class="check-mark">✓</span>
                      <span v-else class="dot-num">3</span>
                    </div>
                    <div class="node-text">
                      <span class="node-label">{{ item.status >= 3 ? '排险已完成' : (item.status === 2 ? '排险施治中' : '待施工') }}</span>
                      <span class="node-sub">{{ item.status >= 3 ? '施工完毕' : (item.status === 2 ? '现场作业中' : '等待处置') }}</span>
                    </div>
                  </div>

                  <div class="timeline-line" :class="{ active: isStepLineActive(item, 3) }"></div>

                  <!-- 节点 4：验收已办结 -->
                  <div class="timeline-node" :class="{ completed: isStepCompleted(item, 4), current: isStepCurrent(item, 4), rejected: item.status === 4 }">
                    <div class="node-dot">
                      <span v-if="item.status === 4" class="reject-mark">✕</span>
                      <span v-else-if="isStepCompleted(item, 4)" class="check-mark">✓</span>
                      <span v-else class="dot-num">4</span>
                    </div>
                    <div class="node-text">
                      <span class="node-label">{{ item.status === 4 ? '整改待补正' : (item.status === 3 && item.reviewed == 1 ? '验收已办结' : (item.status === 3 ? '终审验收中' : '待实地验收')) }}</span>
                      <span class="node-sub">{{ item.status === 4 ? '退回重新整改' : (item.status === 3 && item.reviewed == 1 ? '全流程闭环' : (item.status === 3 ? '指挥复核中' : '等待核验')) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!-- 右侧动作流转区 (严格依据 SOD 与终审质量机制) -->
            <div class="card-action-bar">
              <!-- 管理员全权调度与终审把关 -->
              <template v-if="userRole === '1'">
                <!-- 待处理 (0): 派发责任人 + 审查驳回 -->
                <div v-if="item.status === 0" class="action-btn-group">
                  <button
                    class="action-flow-btn btn-assign"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="openAssignModal(item)"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    <span>调度派单</span>
                  </button>
                  <button
                    class="action-flow-btn btn-admin-withdraw"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="openAdminWithdrawDialog(item)"
                  >
                    <span>撤回工单</span>
                  </button>
                </div>

                <!-- 已接单 (1): 管理员可督促或改派 -->
                <div v-else-if="item.status === 1" class="action-btn-group">
                  <button
                    class="action-flow-btn btn-sub-assign"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="openAssignModal(item)"
                  >
                    <span>改派专员</span>
                  </button>
                  <button
                    class="action-flow-btn btn-admin-withdraw"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="openAdminWithdrawDialog(item)"
                  >
                    <span>终止并撤回</span>
                  </button>
                </div>

                <!-- 整改中 (2): 管理员督促施工 -->
                <div v-else-if="item.status === 2" class="action-btn-group">
                  <span class="flow-inprogress-tag">专员施工中...</span>
                  <button
                    class="action-flow-btn btn-admin-withdraw"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="openAdminWithdrawDialog(item)"
                  >
                    <span>终止并撤回</span>
                  </button>
                </div>

                <!-- 待验收 (3 且 reviewed = 0): 管理员终审把关核心入口 -->
                <div v-else-if="item.status === 3 && (item.reviewed === 0 || !item.reviewed)" class="action-btn-group">
                  <button
                    class="action-flow-btn btn-pass-quick"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="quickSingleReview(item, true)"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                    <span>核准办结</span>
                  </button>
                  <button
                    class="action-flow-btn btn-reject"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="quickSingleReview(item, false)"
                  >
                    <span>驳回返工</span>
                  </button>
                </div>

                <!-- 已办结 (3 且 reviewed = 1) -->
                <div v-else-if="item.status === 3 && item.reviewed == 1" class="flow-done-tag">
                  <span>已闭环归档 ✓</span>
                </div>

                <!-- 已驳回 (4): 管理员可重新派单返工 -->
                <div v-else-if="item.status === 4" class="action-btn-group">
                  <button
                    class="action-flow-btn btn-reassign"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="openAssignModal(item)"
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>
                    <span>重新派单返工</span>
                  </button>
                  <span class="flow-rejected-tag">已驳回</span>
                </div>
              </template>

              <!-- 处理专员: 严格遵循专员处置权责 -->
              <template v-else-if="userRole === '2'">
                <!-- 待处理且未指派: 可接单认领 -->
                <button
                  v-if="item.status === 0"
                  class="action-flow-btn btn-accept"
                  :disabled="actionLoadingId === item.id"
                  @click.stop="handleFlow(item, 'accept')"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                  <span>接单认领</span>
                </button>

                <!-- 派发给当前专员 -->
                <template v-else-if="isAssignedToMe(item)">
                  <button
                    v-if="item.status === 1"
                    class="action-flow-btn btn-start"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="handleFlow(item, 'start')"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    <span>开始整改</span>
                  </button>

                  <button
                    v-else-if="item.status === 2"
                    class="action-flow-btn btn-complete"
                    :disabled="actionLoadingId === item.id"
                    @click.stop="handleFlow(item, 'complete')"
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                    <span>整改完成</span>
                  </button>

                  <!-- 待验收状态：专员端锁定，提示等待终审 -->
                  <div v-else-if="item.status === 3 && (item.reviewed === 0 || !item.reviewed)" class="flow-wait-tag">
                    <span class="wait-icon">⏳</span>
                    <span>等待终审验收</span>
                  </div>

                  <div v-else-if="item.status === 3 && item.reviewed == 1" class="flow-done-tag">
                    <span>处置已闭环 ✓</span>
                  </div>

                  <div v-else-if="item.status === 4" class="flow-rejected-tag">
                    <span>整改未达标已驳回 ✕</span>
                  </div>
                </template>

                <!-- 派发给其他专员 -->
                <div v-else class="other-handler-tag">
                  <span v-if="item.handlerId">责任专员处置中</span>
                  <span v-else>尚未指派处理人员</span>
                </div>
              </template>

              <!-- 普通用户或无权限时仅查看 -->
              <template v-else>
                <div class="user-flow-status" :class="'user-status-' + item.status">
                  {{ formatUserFlowStatus(item) }}
                </div>
              </template>

              <!-- 隐患「撤回」按钮：仅创建人本人且未被接单 (status === 0) 可撤回 -->
              <button
                v-if="canWithdraw(item)"
                type="button"
                class="action-flow-btn btn-withdraw"
                :disabled="actionLoadingId === item.id"
                @click.stop="handleWithdraw(item)"
                title="撤回后该上报记录只对管理员可见"
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                  <path d="M3 10h10a5 5 0 0 1 5 5v2"/>
                  <polyline points="7 6 3 10 7 14"/>
                </svg>
                <span>{{ actionLoadingId === item.id ? '撤回中...' : '撤回上报' }}</span>
              </button>

              <button class="view-detail-btn btn-pill-secondary" @click="viewDetail(item.id)">
                <span>详情</span>
                <span class="arrow">→</span>
              </button>
            </div>
          </article>
        </div>
      </main>
    </div>

    <!-- 浮动批量审批控制栏 (管理员勾选时平滑弹出) -->
    <transition name="slide-up">
      <div v-if="userRole === '1' && selectedIds.length > 0" class="batch-bar-container">
        <div class="batch-floating-card glass-card">
          <div class="batch-left">
            <div class="batch-count-pill">
              <span class="num-font">{{ selectedIds.length }}</span>
            </div>
            <div class="batch-text-group">
              <span class="batch-title">已选中 {{ selectedIds.length }} 项隐患工单</span>
              <span class="batch-sub">可由指挥长执行批量终审验收或批量驳回返工</span>
            </div>
          </div>

          <div class="batch-actions">
            <button class="batch-btn btn-batch-pass" :disabled="batchSubmitting" @click="openBatchModal(true)">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <polyline points="20 6 9 17 4 12"/>
              </svg>
              <span>批量核准办结 ({{ selectedIds.length }})</span>
            </button>
            <button class="batch-btn btn-batch-reject" :disabled="batchSubmitting" @click="openBatchModal(false)">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
              <span>批量驳回返工</span>
            </button>
            <button class="batch-btn btn-batch-clear" @click="clearSelection">
              <span>取消勾选</span>
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- 管理员批量审批模态框 -->
    <div v-if="batchModalVisible" class="modal-mask" @click.self="batchModalVisible = false">
      <div class="modal-box glass-card">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">{{ batchPass ? '✅' : '⚠️' }}</span>
            <h3 class="modal-title">{{ batchPass ? '批量终审验收通过' : '批量终审驳回返工' }}</h3>
          </div>
          <button class="modal-close-btn" @click="batchModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <p class="modal-hint">
            即将对选中的 <span class="num-font highlight-id">{{ selectedIds.length }}</span> 个工单执行
            <strong :class="batchPass ? 'text-pass' : 'text-reject'">{{ batchPass ? '【终审办结】' : '【驳回返工】' }}</strong> 批处理：
          </p>
          <div class="batch-selected-chips">
            <span class="batch-chip num-font">已选 {{ selectedIds.length }} 项工单</span>
          </div>
          <div class="form-group mt-3">
            <label class="form-label">调度终审批注意见：</label>
            <textarea
              v-model="batchRemark"
              rows="3"
              class="form-textarea"
              :placeholder="batchPass ? '请输入核准办结意见，如：现场复核合格，准予闭环归档。' : '请输入驳回理由，如：现场施工未彻底清理，要求重新整改。'"
            ></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" @click="batchModalVisible = false">取消</button>
          <button
            class="modal-btn"
            :class="batchPass ? 'confirm-pass' : 'confirm-reject'"
            :disabled="batchSubmitting"
            @click="submitBatchReview"
          >
            {{ batchSubmitting ? '正在批量处理中...' : (batchPass ? '确认批量核准通过' : '确认批量驳回返工') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 管理员派单/改派模态框 -->
    <div v-if="assignModalVisible" class="modal-mask" @click.self="assignModalVisible = false">
      <div class="modal-box assign-modal-box glass-card">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">👷</span>
            <div>
              <h3 class="modal-title">{{ assignDialogTitle }}</h3>
              <p class="modal-subtitle">工单：{{ hazardTitle(currentOperatingItem) }}</p>
            </div>
          </div>
          <button class="modal-close-btn" @click="assignModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="assign-context-strip">
            <span class="assign-context-dot"></span>
            <span v-if="currentOperatingItem?.status === 1">当前工单已指派责任人，选择新的处理人员后将立即完成改派。</span>
            <span v-else-if="currentOperatingItem?.status === 4">该工单已被驳回，选择处理人员后将重新进入处置流程。</span>
            <span v-else>请选择真实处理人员，派单后工单进入“已接单”状态。</span>
          </div>

          <div class="form-group handler-search-group">
            <label class="form-label">搜索处理人员</label>
            <div class="handler-search-wrap">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
              <input
                v-model="handlerSearch"
                class="form-input"
                placeholder="按昵称或邮箱搜索"
              />
            </div>
          </div>

          <div v-if="handlerLoading" class="handler-state">
            <span class="handler-state-spinner"></span>
            正在同步处理人员名单...
          </div>
          <div v-else-if="handlerError" class="handler-state handler-state-error">
            <span>{{ handlerError }}</span>
            <button type="button" class="handler-retry" @click="fetchHandlers">重新加载</button>
          </div>
          <div v-else-if="!filteredHandlers.length" class="handler-state">暂无匹配的处理人员</div>
          <div v-else class="handler-grid" data-testid="handler-picker">
            <button
              v-for="handler in filteredHandlers"
              :key="handler.id"
              type="button"
              class="handler-card"
              :class="{ selected: Number(selectedHandlerId) === Number(handler.id) }"
              @click="selectedHandlerId = handler.id"
            >
              <span class="handler-avatar">{{ (handler.nickname || handler.email || '处').slice(0, 1) }}</span>
              <span class="handler-copy">
                <span class="handler-name">{{ handler.nickname || '未命名处理人员' }}</span>
                <span class="handler-email">{{ handler.email }}</span>
              </span>
              <span v-if="Number(currentOperatingItem?.handlerId) === Number(handler.id)" class="handler-current">当前负责人</span>
              <span v-if="Number(selectedHandlerId) === Number(handler.id)" class="handler-check">✓</span>
            </button>
          </div>

          <div v-if="selectedHandler" class="selected-handler-summary">
            <span class="summary-label">已选择</span>
            <strong>{{ selectedHandler.nickname || selectedHandler.email }}</strong>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" @click="assignModalVisible = false">取消</button>
          <button
            class="modal-btn confirm"
            :disabled="!selectedHandlerId || modalLoading || handlerLoading"
            @click="submitAssign"
          >
            {{ modalLoading ? '提交中...' : assignActionText }}
          </button>
        </div>
      </div>
    </div>

    <!-- 管理员撤回无效工单模态框 -->
    <div v-if="adminWithdrawModalVisible" class="modal-mask" @click.self="closeAdminWithdrawDialog">
      <div class="modal-box admin-withdraw-modal glass-card" data-testid="admin-withdraw-dialog">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">↩️</span>
            <div>
              <h3 class="modal-title">{{ adminWithdrawTarget?.status === 0 ? '撤回无效工单' : '终止并撤回工单' }}</h3>
              <p class="modal-subtitle">工单：{{ hazardTitle(adminWithdrawTarget) }}</p>
            </div>
          </div>
          <button class="modal-close-btn" @click="closeAdminWithdrawDialog">✕</button>
        </div>
        <div class="modal-body">
          <div class="admin-withdraw-warning">
            <span class="warning-dot"></span>
            <span>撤回后该工单仅管理员可见，处理人员将无法继续操作。请说明无效原因。</span>
          </div>
          <div class="form-group">
            <label class="form-label">撤回原因 <span class="required-mark">*</span></label>
            <textarea
              v-model="adminWithdrawReason"
              rows="4"
              maxlength="500"
              class="form-textarea"
              placeholder="例如：AI 误识别建单、重复上报、内容与隐患平台业务无关..."
            ></textarea>
            <div class="reason-counter num-font">{{ adminWithdrawReason.length }}/500</div>
          </div>
          <p v-if="adminWithdrawError" class="admin-withdraw-error">{{ adminWithdrawError }}</p>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" @click="closeAdminWithdrawDialog">取消</button>
          <button
            class="modal-btn confirm-reject"
            :disabled="!adminWithdrawReason.trim() || adminWithdrawLoading"
            @click="submitAdminWithdraw"
          >
            {{ adminWithdrawLoading ? '撤回中...' : '确认撤回' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 管理员单单审查/驳回模态框 -->
    <div v-if="reviewModalVisible" class="modal-mask" @click.self="reviewModalVisible = false">
      <div class="modal-box glass-card">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">⚖️</span>
            <h3 class="modal-title">工单调度审查</h3>
          </div>
          <button class="modal-close-btn" @click="reviewModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <p class="modal-hint">
            工单：{{ hazardTitle(currentOperatingItem) }}
          </p>
          <div class="review-type-selector">
            <label class="radio-label">
              <input type="radio" :value="false" v-model="reviewPass" />
              <span class="radio-badge badge-reject">审查驳回（将工单置为已驳回状态）</span>
            </label>
            <label class="radio-label">
              <input type="radio" :value="true" v-model="reviewPass" />
              <span class="radio-badge badge-pass">审查通过（核准通过并归档闭环）</span>
            </label>
          </div>
          <div class="form-group mt-3">
            <label class="form-label">审查审核备注 / 驳回理由：</label>
            <textarea
              v-model="reviewRemark"
              rows="3"
              class="form-textarea"
              placeholder="请输入审查意见或说明驳回原因..."
            ></textarea>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" @click="reviewModalVisible = false">取消</button>
          <button
            class="modal-btn"
            :class="reviewPass ? 'confirm-pass' : 'confirm-reject'"
            :disabled="modalLoading"
            @click="submitReview"
          >
            {{ modalLoading ? '提交中...' : (reviewPass ? '核准通过' : '确认驳回') }}
          </button>
        </div>
      </div>
    </div>

    <!-- 撤回确认：站内弹窗，替代浏览器原生 confirm -->
    <ConfirmDialog
      :visible="withdrawDialogVisible"
      icon="↩️"
      title="撤回上报"
      :message="withdrawTarget ? ('撤回后该上报记录只对管理员可见。工单“' + hazardTitle(withdrawTarget) + '”将终止处置流转。') : ''"
      detail="此操作不可撤销。"
      :error="withdrawError"
      confirm-text="确定撤回"
      :loading="actionLoadingId !== null"
      loading-text="撤回中..."
      danger
      @confirm="confirmWithdraw"
      @cancel="closeWithdrawDialog"
    />
    <AppToast :text="toastText" :type="toastType" />
  </div>
</template>

<script setup>
import SecureImage from '../components/SecureImage.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import AppToast from '../components/AppToast.vue'
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  HAZARD_TAXONOMY,
  resolveHazardList,
  matchHazardFilter,
  getSubcategoriesByMajor
} from '../constants/hazardTaxonomy.js'

const router = useRouter()
const userRole = ref(localStorage.getItem('role') || '0')
const currentUserId = ref(Number(localStorage.getItem('userId')) || null)

const loading = ref(true)
const errorMessage = ref('')
const hazards = ref([])
const actionLoadingId = ref(null)

// 撤回确认弹窗 + 轻提示：替代浏览器原生 confirm()/alert()，视觉与全站弹窗一致
const withdrawDialogVisible = ref(false)
const withdrawTarget = ref(null)
const withdrawError = ref('')
const toastText = ref('')
const toastType = ref('success')
let toastTimer = null

function showToast(text, type = 'success') {
  toastText.value = text
  toastType.value = type
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toastText.value = '' }, 2600)
}

function openWithdrawDialog(item) {
  withdrawTarget.value = item
  withdrawError.value = ''
  withdrawDialogVisible.value = true
}

function closeWithdrawDialog() {
  if (actionLoadingId.value !== null) return
  withdrawDialogVisible.value = false
  withdrawError.value = ''
}

// 批量终审与调度模态框响应式状态
const selectedIds = ref([])
const batchModalVisible = ref(false)
const batchPass = ref(true)
const batchSubmitting = ref(false)
const batchReviewRemark = ref('')

const assignModalVisible = ref(false)
const reviewModalVisible = ref(false)
const currentOperatingItem = ref(null)
const selectedHandlerId = ref(null)
const handlerOptions = ref([])
const handlerLoading = ref(false)
const handlerError = ref('')
const handlerSearch = ref('')
const reviewPass = ref(true)
const reviewRemark = ref('')
const modalLoading = ref(false)
const adminWithdrawModalVisible = ref(false)
const adminWithdrawTarget = ref(null)
const adminWithdrawReason = ref('')
const adminWithdrawError = ref('')
const adminWithdrawLoading = ref(false)

// 选中过滤
const selectedStatus = ref(-1) // -1: 全部, 0: 待处理, 1: 已接单, 2: 整改中, 30: 待验收, 31: 已办结, 4: 已驳回, 5: 已撤回
const selectedMajorCode = ref('all') // 'all' 或 'traffic', 'fire', ...
const selectedSubcategoryCode = ref('all') // 'all' 或 'road_occupancy', ...

// 状态流转选项卡 Tabs (需求2: 仅 role===1 显示已撤回筛选项，筛 status===5)
const statusTabs = computed(() => {
  const tabs = [
    { val: -1, label: '全部' },
    { val: 0, label: '待处理' },
    { val: 1, label: '已接单' },
    { val: 2, label: '整改中' },
    { val: 30, label: '待验收' },
    { val: 31, label: '已办结' },
    { val: 4, label: '已驳回' },
  ]
  if (userRole.value === '1') {
    tabs.push({ val: 5, label: '已撤回' })
  }
  return tabs
})

const assignDialogTitle = computed(() => {
  if (currentOperatingItem.value?.status === 1) return '工单改派处理人员'
  if (currentOperatingItem.value?.status === 4) return '工单重新派单'
  return '工单调度派单'
})

const assignActionText = computed(() => {
  if (currentOperatingItem.value?.status === 1) return '确认改派'
  if (currentOperatingItem.value?.status === 4) return '确认重新派单'
  return '确认派单'
})

const filteredHandlers = computed(() => {
  const keyword = handlerSearch.value.trim().toLowerCase()
  if (!keyword) return handlerOptions.value
  return handlerOptions.value.filter((handler) =>
    String(handler.id).includes(keyword) ||
    (handler.nickname || '').toLowerCase().includes(keyword) ||
    (handler.email || '').toLowerCase().includes(keyword)
  )
})

const selectedHandler = computed(() =>
  handlerOptions.value.find((handler) => Number(handler.id) === Number(selectedHandlerId.value)) || null
)

async function fetchHandlers() {
  const token = localStorage.getItem('token')
  if (!token) {
    router.push('/login')
    return
  }
  handlerLoading.value = true
  handlerError.value = ''
  try {
    const res = await fetch('/api/users/handlers', {
      headers: { Authorization: 'Bearer ' + token }
    })
    const json = await res.json().catch(() => ({}))
    if (res.status === 401) {
      router.replace('/login?redirect=' + encodeURIComponent('/hazard'))
      return
    }
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '加载处理人员失败')
    }
    handlerOptions.value = Array.isArray(json.data) ? json.data : []
  } catch (err) {
    handlerError.value = err.message || '加载处理人员失败'
  } finally {
    handlerLoading.value = false
  }
}

// 隐患「撤回」判断：显示条件为 status === 0 && item.userId === 当前登录 userId (未被接单且创建人本人)
function canWithdraw(item) {
  if (!item || item.status !== 0) return false
  if (currentUserId.value == null) return false
  return Number(item.userId) === Number(currentUserId.value)
}

// 管理员统计指标 (包含 withdrawn 字段，不计入 total/rate)
const adminStats = ref(null)

async function fetchStats() {
  if (userRole.value !== '1') return
  try {
    const token = localStorage.getItem('token')
    const res = await fetch('/api/hazard/stats', {
      headers: { Authorization: 'Bearer ' + token }
    })
    const json = await res.json().catch(() => ({}))
    if (json.code === 200 && json.data) {
      adminStats.value = json.data
    }
  } catch (e) {
    console.warn('获取隐患统计失败', e)
  }
}

// 隐患「撤回」操作：POST /api/hazard/{id}/withdraw (带 Bearer token，无 body)
async function handleWithdraw(item) {
  const token = localStorage.getItem('token')
  if (!token) {
    router.push('/login')
    return
  }

  openWithdrawDialog(item)
}

// 用户在站内弹窗里点了「确定撤回」之后才真正发请求
async function confirmWithdraw() {
  const item = withdrawTarget.value
  if (!item) return
  const token = localStorage.getItem('token')
  if (!token) {
    closeWithdrawDialog()
    router.push('/login')
    return
  }
  withdrawError.value = ''
  actionLoadingId.value = item.id
  try {
    const res = await fetch(`/api/hazard/${item.id}/withdraw`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + token
      }
    })
    const json = await res.json().catch(() => ({}))
    if (json.code === 200) {
      withdrawDialogVisible.value = false
      showToast('上报记录已成功撤回')
      // 成功：用返回的 data 刷新该项 (status: 5, statusText: "已撤回")
      if (json.data) {
        item.status = json.data.status ?? 5
        item.statusText = json.data.statusText || '已撤回'
      } else {
        item.status = 5
        item.statusText = '已撤回'
      }
      // 刷新列表与统计，确保与服务端权限和过滤完全同步
      fetchHazards()
      fetchStats()
    } else {
      // 需求3: 错误码语义化分支 (必须读 json.code，HTTP 仍为 200)
      if (json.code === 401) {
        withdrawDialogVisible.value = false
        showToast('登录凭证已失效，请重新登录', 'error')
        localStorage.removeItem('token')
        router.push('/login')
      } else if (json.code === 409) {
        withdrawError.value = json.message || '该任务已被受理，无法撤回'
        fetchHazards()
      } else if (json.code === 404) {
        withdrawDialogVisible.value = false
        showToast(json.message || '任务不存在或无权限', 'error')
        fetchHazards()
      } else if (json.code === 403) {
        withdrawError.value = json.message || '无权限执行此撤回操作'
      } else {
        withdrawError.value = json.message || '撤回处理未成功，请稍后重试'
      }
    }
  } catch (err) {
    console.error('撤回请求失败', err)
    withdrawError.value = '网络请求异常，请稍后重试'
  } finally {
    actionLoadingId.value = null
  }
}

// 一级大类列表选项：包含“全部”与 8 大标准一级分类
const majorCategoryOptions = computed(() => [
  { code: 'all', label: '全部' },
  ...HAZARD_TAXONOMY.map(m => ({ code: m.code, label: m.label }))
])

// 选中的一级大类下的二级细分子项列表
const currentSubcategories = computed(() => {
  return getSubcategoriesByMajor(selectedMajorCode.value)
})

function selectMajor(code) {
  selectedMajorCode.value = code
  // 规范要求：切换一级大类时，二级自动重置为“全部”
  selectedSubcategoryCode.value = 'all'
}

function selectSubcategory(code) {
  selectedSubcategoryCode.value = code
}

// 市民视角专享模式: 'mine' (我的上报) 或 'public' (全城公示)
const filterViewMode = ref('mine')
const myReportCount = ref(0)

function switchViewMode(mode) {
  filterViewMode.value = mode
  selectedStatus.value = -1
  selectedMajorCode.value = 'all'
  selectedSubcategoryCode.value = 'all'
  fetchHazards()
}

const roleBadgeText = computed(() => {
  if (userRole.value === '1') return '调度指挥长'
  if (userRole.value === '2') return '处突责任人'
  if (filterViewMode.value === 'public') return '全城公开'
  return '巡查市民'
})

const pageTitleText = computed(() => {
  if (userRole.value === '1') return '全域隐患闭环调度指挥中心'
  if (userRole.value === '2') return '隐患整治待办与处置工作台'
  if (filterViewMode.value === 'public') return '三明市城市安全综合治理 · 全城公示'
  return '我的隐患上报与处置追踪'
})

// 顺丰物流步进轴辅助判断
function isStepCompleted(item, step) {
  if (!item) return false
  if (item.status === 4) {
    return step <= 2
  }
  if (step === 1) return true
  if (step === 2) return item.status >= 1 || (item.handlerId != null)
  if (step === 3) return item.status >= 3
  if (step === 4) return item.status === 3 && item.reviewed == 1
  return false
}

function isStepCurrent(item, step) {
  if (!item) return false
  if (item.status === 4) return step === 4
  if (step === 1) return item.status === 0
  if (step === 2) return item.status === 1
  if (step === 3) return item.status === 2
  if (step === 4) return item.status === 3 && (item.reviewed === 0 || !item.reviewed)
  return false
}

function isStepLineActive(item, lineIndex) {
  if (!item) return false
  if (item.status === 4) return lineIndex <= 2
  if (lineIndex === 1) return item.status >= 1 || (item.handlerId != null)
  if (lineIndex === 2) return item.status >= 2
  if (lineIndex === 3) return item.status >= 3
  return false
}

function goToReport() {
  router.push('/')
}

function resetFilters() {
  selectedStatus.value = -1
  selectedMajorCode.value = 'all'
  selectedSubcategoryCode.value = 'all'
}

function isAssignedToMe(item) {
  return item.handlerId != null && Number(item.handlerId) === currentUserId.value
}

function isPendingReview(item) {
  return item.status === 3 && (item.reviewed === 0 || !item.reviewed)
}

function formatStatusText(item) {
  if (item.status === 3) {
    return isPendingReview(item) ? '待验收' : '已办结'
  }
  if (item.status === 5) {
    return item.statusText || '已撤回'
  }
  const map = { 0: '待处理', 1: '已接单', 2: '整改中', 4: '已驳回' }
  return map[item.status] || item.statusText || '未知'
}

function getStatusBadgeClass(item) {
  if (item.status === 3) {
    return isPendingReview(item) ? 'status-pending-review' : 'status-3'
  }
  if (item.status === 5) {
    return 'status-5 status-withdrawn'
  }
  return 'status-' + item.status
}

function formatUserFlowStatus(item) {
  if (item.status === 3) {
    return isPendingReview(item) ? '整改已完成，等待终审 ⏳' : '处置已办结归档 ✓'
  }
  if (item.status === 4) return '工单已审查驳回 ✕'
  if (item.status === 5) return '工单已撤回 ↩'
  return '处理推进中...'
}

function hazardTitle(item) {
  const text = (item?.description || item?.address || '隐患工单').trim()
  return text.length > 28 ? text.slice(0, 28) + '…' : text
}

function formatDate(val) {
  if (!val) return ''
  return String(val).replace('T', ' ').slice(0, 16)
}

function getStatusCount(statusVal) {
  if (statusVal === -1) return hazards.value.length
  if (statusVal === 30) {
    return hazards.value.filter(h => isPendingReview(h)).length
  }
  if (statusVal === 31) {
    return hazards.value.filter(h => h.status === 3 && h.reviewed == 1).length
  }
  if (statusVal === 5 && adminStats.value && adminStats.value.withdrawn != null) {
    return adminStats.value.withdrawn
  }
  return hazards.value.filter(h => h.status === statusVal).length
}

const pendingReviewCount = computed(() => {
  return hazards.value.filter(h => isPendingReview(h)).length
})

const filteredHazards = computed(() => {
  return hazards.value.filter(item => {
    // 状态过滤
    if (selectedStatus.value === 30) {
      if (!isPendingReview(item)) return false
    } else if (selectedStatus.value === 31) {
      if (!(item.status === 3 && item.reviewed == 1)) return false
    } else if (selectedStatus.value !== -1 && item.status !== selectedStatus.value) {
      return false
    }

    // 规范两级类别联合过滤
    if (!matchHazardFilter(item.hazardTypes, selectedMajorCode.value)) {
      return false
    }
    return true
  })
})

// 批量选择逻辑
function isSelected(id) {
  return selectedIds.value.includes(id)
}

function toggleSelect(id) {
  const item = hazards.value.find(h => h.id === id)
  if (!item || !isPendingReview(item)) {
    // 严密防御：已办结或非待验收工单严禁参与终审审批
    return
  }
  const index = selectedIds.value.indexOf(id)
  if (index > -1) {
    selectedIds.value.splice(index, 1)
  } else {
    selectedIds.value.push(id)
  }
}

// 当前页可供审批的待验收工单集合
const currentPagePendingHazards = computed(() => {
  return filteredHazards.value.filter(isPendingReview)
})

const currentPagePendingCount = computed(() => {
  return currentPagePendingHazards.value.length
})

const isAllCurrentPageSelected = computed(() => {
  const list = currentPagePendingHazards.value
  if (!list.length) return false
  return list.every(item => selectedIds.value.includes(item.id))
})

function toggleSelectAllCurrentPage() {
  const list = currentPagePendingHazards.value
  if (!list.length) return
  if (isAllCurrentPageSelected.value) {
    // 取消当前页中的待验收工单
    const curIds = new Set(list.map(i => i.id))
    selectedIds.value = selectedIds.value.filter(id => !curIds.has(id))
  } else {
    // 仅勾选当前页中的待验收工单
    const set = new Set(selectedIds.value)
    list.forEach(i => set.add(i.id))
    selectedIds.value = Array.from(set)
  }
}

function selectAllPendingReview() {
  const pending = hazards.value.filter(h => isPendingReview(h))
  selectedIds.value = pending.map(h => h.id)
  selectedStatus.value = 30
}

function clearSelection() {
  selectedIds.value = []
}

function viewDetail(id) {
  router.push(`/hazard/${id}`)
}

async function fetchHazards() {
  const token = localStorage.getItem('token')
  if (!token) {
    router.replace('/login?redirect=' + encodeURIComponent('/hazard'))
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    // 若市民视角且切换为全城公示，则拉取全城已办结公开成果 (status=3)；否则拉取日常工单流水
    const isPublicMode = userRole.value === '0' && filterViewMode.value === 'public'
    const apiUrl = isPublicMode
      ? '/api/hazard?status=3&current=1&size=50'
      : '/api/hazard?current=1&size=100'

    const res = await fetch(apiUrl, {
      headers: { Authorization: 'Bearer ' + token },
    })
    const json = await res.json().catch(() => ({}))
    if (res.status === 401) {
      router.replace('/login?redirect=' + encodeURIComponent('/hazard'))
      return
    }
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || `加载工单失败（${res.status}）`)
    }
    const list = json.data?.records || json.data || []
    const safeList = Array.isArray(list) ? list : []
    hazards.value = safeList

    if (userRole.value === '1') {
      fetchStats()
    }

    // 记录市民本人的上报条数
    if (userRole.value === '0' && filterViewMode.value === 'mine') {
      myReportCount.value = safeList.length
    }
  } catch (err) {
    console.error('获取隐患任务失败', err)
    errorMessage.value = err.message || '获取工单列表异常，请检查网络后重试'
  } finally {
    loading.value = false
  }
}

// 状态流转操作：accept (0->1), start (1->2), complete (2->3)
async function handleFlow(item, action) {
  const token = localStorage.getItem('token')
  if (!token) {
    alert('请先登录')
    router.push('/login')
    return
  }

  actionLoadingId.value = item.id
  try {
    const res = await fetch(`/api/hazard/${item.id}/${action}`, {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || `操作失败 (${res.status})`)
    }

    if (action === 'accept') {
      item.status = 1
      item.statusText = '已接单'
      item.handlerId = currentUserId.value || 1
    } else if (action === 'start') {
      item.status = 2
      item.statusText = '整改中'
    } else if (action === 'complete') {
      // 专员点击完成 -> 跃迁为待验收 (status=3, reviewed=0)
      item.status = 3
      item.reviewed = 0
      item.statusText = '待验收'
    }
  } catch (err) {
    console.error(`执行 ${action} 异常`, err)
    alert(err.message || '操作未成功，请稍后重试')
  } finally {
    actionLoadingId.value = null
  }
}

// 单条快捷审批
async function quickSingleReview(item, pass) {
  const token = localStorage.getItem('token')
  if (!token) return

  const defaultRemark = pass ? '调度指挥中心现场终审通过，核准办结。' : '整改质量未达标，驳回重新整改。'
  const remark = prompt(`请确认对工单“${hazardTitle(item)}”进行【${pass ? '核准办结' : '驳回返工'}】：`, defaultRemark)
  if (remark === null) return // 点击取消

  actionLoadingId.value = item.id
  try {
    const res = await fetch(`/api/hazard/${item.id}/review`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({
        pass: pass,
        remark: remark || defaultRemark,
      }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '审查提交失败')
    }

    if (pass) {
      item.status = 3
      item.reviewed = 1
      item.statusText = '已办结'
    } else {
      item.status = 4
      item.reviewed = 1
      item.statusText = '已驳回'
    }
    item.reviewRemark = remark || defaultRemark
  } catch (err) {
    alert(err.message || '操作失败')
  } finally {
    actionLoadingId.value = null
  }
}

// 批量审批弹窗
function openBatchModal(pass) {
  if (!selectedIds.value.length) return
  batchPass.value = pass
  batchRemark.value = pass ? '现场整改复核合格，指挥调度中心核准办结。' : '整改不彻底，要求责任人重新进场整改。'
  batchModalVisible.value = true
}

// 提交批量审批
async function submitBatchReview() {
  const token = localStorage.getItem('token')
  if (!token || !selectedIds.value.length) return

  batchSubmitting.value = true
  try {
    const res = await fetch('/api/hazard/batch-review', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({
        ids: selectedIds.value,
        pass: batchPass.value,
        remark: batchRemark.value || (batchPass.value ? '批量核准通过' : '批量驳回返工'),
      }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '批量审批请求失败')
    }

    // 本地即时更新已选工单状态
    const updatedIds = new Set(selectedIds.value)
    hazards.value.forEach(h => {
      if (updatedIds.has(h.id)) {
        if (batchPass.value) {
          h.status = 3
          h.reviewed = 1
          h.statusText = '已办结'
        } else {
          h.status = 4
          h.reviewed = 1
          h.statusText = '已驳回'
        }
        h.reviewRemark = batchRemark.value
      }
    })

    const count = selectedIds.value.length
    selectedIds.value = []
    batchModalVisible.value = false
    alert(`成功批量${batchPass.value ? '核准办结' : '驳回返工'} ${count} 项隐患工单！`)
  } catch (err) {
    alert(err.message || '批量审批失败，请稍后重试')
  } finally {
    batchSubmitting.value = false
  }
}

// 派单弹窗
async function openAssignModal(item) {
  currentOperatingItem.value = item
  selectedHandlerId.value = item.handlerId ? Number(item.handlerId) : null
  handlerSearch.value = ''
  assignModalVisible.value = true
  await fetchHandlers()
}

async function submitAssign() {
  const token = localStorage.getItem('token')
  if (!token || !currentOperatingItem.value || !selectedHandlerId.value) return
  if (currentOperatingItem.value.status === 1 &&
      Number(selectedHandlerId.value) === Number(currentOperatingItem.value.handlerId)) {
    showToast('请选择新的处理人员', 'error')
    return
  }

  modalLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${currentOperatingItem.value.id}/assign`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ handlerId: Number(selectedHandlerId.value) }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '派单失败')
    }

    const assignedName = selectedHandler.value?.nickname || selectedHandler.value?.email || '所选处理人员' 
    const action = currentOperatingItem.value.status === 1 ? '改派' :
      (currentOperatingItem.value.status === 4 ? '重新派单' : '派单')
    assignModalVisible.value = false
    showToast(`工单“${hazardTitle(currentOperatingItem.value)}”已成功${action}给 ${assignedName}`)
    await fetchHazards()
  } catch (err) {
    showToast(err.message || '派单未成功，请稍后重试', 'error')
  } finally {
    modalLoading.value = false
  }
}

function openAdminWithdrawDialog(item) {
  adminWithdrawTarget.value = item
  adminWithdrawReason.value = ''
  adminWithdrawError.value = ''
  adminWithdrawModalVisible.value = true
}

function closeAdminWithdrawDialog() {
  if (adminWithdrawLoading.value) return
  adminWithdrawModalVisible.value = false
  adminWithdrawError.value = ''
}

async function submitAdminWithdraw() {
  const reason = adminWithdrawReason.value.trim()
  if (!reason || !adminWithdrawTarget.value) {
    adminWithdrawError.value = '请输入撤回原因'
    return
  }
  const token = localStorage.getItem('token')
  if (!token) {
    router.push('/login')
    return
  }
  adminWithdrawLoading.value = true
  adminWithdrawError.value = ''
  try {
    const res = await fetch(`/api/hazard/${adminWithdrawTarget.value.id}/admin-withdraw`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ reason }),
    })
    const json = await res.json().catch(() => ({}))
    if (res.status === 401) {
      router.replace('/login?redirect=' + encodeURIComponent('/hazard'))
      return
    }
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '撤回失败')
    }
    const action = adminWithdrawTarget.value.status === 0 ? '撤回' : '终止并撤回'
    adminWithdrawModalVisible.value = false
    showToast(`工单已成功${action}`)
    await fetchHazards()
  } catch (err) {
    adminWithdrawError.value = err.message || '撤回失败，请稍后重试'
  } finally {
    adminWithdrawLoading.value = false
  }
}

// 审查驳回单单弹窗
function openReviewModal(item) {
  currentOperatingItem.value = item
  reviewPass.value = false
  reviewRemark.value = ''
  reviewModalVisible.value = true
}

async function submitReview() {
  const token = localStorage.getItem('token')
  if (!token || !currentOperatingItem.value) return

  modalLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${currentOperatingItem.value.id}/review`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({
        pass: reviewPass.value,
        remark: reviewRemark.value || (reviewPass.value ? '审查通过' : '审查驳回'),
      }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '审查提交失败')
    }

    if (reviewPass.value) {
      currentOperatingItem.value.status = 3
      currentOperatingItem.value.reviewed = 1
      currentOperatingItem.value.statusText = '已办结'
    } else {
      currentOperatingItem.value.status = 4
      currentOperatingItem.value.reviewed = 1
      currentOperatingItem.value.statusText = '已驳回'
    }
    currentOperatingItem.value.reviewRemark = reviewRemark.value
    reviewModalVisible.value = false
    alert(reviewPass.value ? '审查核准通过，工单已办结！' : '该工单已审查驳回！')
  } catch (err) {
    alert(err.message || '审查提交失败')
  } finally {
    modalLoading.value = false
  }
}

onMounted(() => {
  fetchHazards()
  if (userRole.value === '1') {
    fetchStats()
  }
})
</script>

<style scoped>
.hazard-list-view {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  overflow-x: hidden;
  position: relative;
}

.content-wrapper {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px 24px 100px;
}

/* 头部样式 */
.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 9999px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.1);
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.back-btn:hover {
  background: #f8fafc;
  border-color: #1a73e8;
  color: #1a73e8;
  transform: translateY(-1px);
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 16px;
}
.header-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.system-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}
.status-indicator-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #16a34a;
}
.role-badge {
  padding: 1px 6px;
  border-radius: 4px;
  background: #eff6ff;
  color: #1a73e8;
  font-weight: 600;
  font-size: 11px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.btn-pill-secondary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 9999px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.1);
  color: #334155;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.btn-pill-secondary:hover {
  background: #f8fafc;
  border-color: #1a73e8;
  color: #1a73e8;
  transform: translateY(-1px);
}

.spin-anim {
  animation: spin 1s linear infinite;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* 筛选工具栏 */
.filters-bar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
  border-radius: 16px;
  margin-bottom: 20px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.03);
}

.status-tabs {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.status-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 9999px;
  background: #f8fafc;
  border: 1px solid transparent;
  color: #475569;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.status-tab-btn:hover {
  background: #f1f5f9;
}
.status-tab-btn.active {
  background: #1a73e8;
  color: #ffffff;
  border-color: #1a73e8;
}
.status-tab-btn.active.tab-pending-review {
  background: #d97706;
  border-color: #d97706;
  color: #ffffff;
}
.status-tab-btn.active.tab-reject {
  background: #dc2626;
  border-color: #dc2626;
  color: #ffffff;
}
.tab-count {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 9999px;
  background: rgba(0, 0, 0, 0.06);
}
.status-tab-btn.active .tab-count {
  background: rgba(255, 255, 255, 0.25);
  color: #ffffff;
}
.highlight-badge {
  background: #fef3c7;
  color: #b45309;
  font-weight: 700;
}

.filter-divider {
  height: 1px;
  background: rgba(0, 0, 0, 0.05);
}

.filter-bottom-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.taxonomy-filter-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.category-chips {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-caption {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
  flex-shrink: 0;
}
.sub-caption {
  color: #0284c7;
}

.chip-btn {
  padding: 4px 12px;
  border-radius: 9999px;
  background: #f1f5f9;
  border: 1px solid transparent;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1);
  white-space: nowrap;
}
.chip-btn:hover {
  background: #e2e8f0;
}
.chip-btn.active {
  background: #eff6ff;
  border-color: #1a73e8;
  color: #1a73e8;
  box-shadow: 0 1px 4px rgba(26, 115, 232, 0.12);
}

.sub-chips {
  padding-left: 2px;
  animation: fadeIn 0.2s ease-out;
}
.sub-chip-btn {
  font-size: 11.5px;
  padding: 3px 10px;
  background: #f8fafc;
  border-color: #e2e8f0;
  color: #64748b;
}
.sub-chip-btn:hover {
  background: #f0f9ff;
  color: #0284c7;
}
.sub-chip-btn.active {
  background: #e0f2fe;
  border-color: #38bdf8;
  color: #0369a1;
  font-weight: 700;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.admin-quick-select {
  display: flex;
  align-items: center;
  gap: 8px;
}
.quick-select-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 9999px;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.quick-select-btn:hover {
  border-color: #1a73e8;
  color: #1a73e8;
}
.header-checkbox {
  cursor: pointer;
}
.select-pending-btn {
  background: #fffbeb;
  border-color: #fde68a;
  color: #b45309;
}
.select-pending-btn:hover {
  background: #fef3c7;
  border-color: #f59e0b;
}

/* 状态展示卡片 */
.state-card {
  padding: 48px 24px;
  text-align: center;
  border-radius: 16px;
  background: #ffffff;
  border: 1px solid rgba(0, 0, 0, 0.06);
}
.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e2e8f0;
  border-top-color: #1a73e8;
  border-radius: 50%;
  margin: 0 auto 16px;
  animation: spin 0.8s linear infinite;
}
.empty-icon-circle {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: #eff6ff;
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}
.empty-title {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 6px;
}
.empty-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0;
}

/* 工单卡片列表 */
.hazard-items-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hazard-card {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  background: #ffffff;
  border-radius: 18px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.04);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  gap: 16px;
}
.hazard-card:hover {
  border-color: #93c5fd;
  box-shadow: 0 8px 28px -4px rgba(26, 115, 232, 0.12);
  transform: translateY(-2px);
}
.hazard-card.card-selected {
  border-color: #1a73e8;
  background: #f8fbff;
  box-shadow: 0 4px 20px rgba(26, 115, 232, 0.15);
}
.hazard-card.card-pending-review {
  border-left: 4px solid #f59e0b;
}

/* 复选框样式 */
.card-select-cell {
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 4px;
}
.custom-checkbox {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 2px solid #cbd5e1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  transition: all 0.15s;
}
.custom-checkbox.checked {
  background: #1a73e8;
  border-color: #1a73e8;
  color: #ffffff;
}

.card-thumb-area {
  position: relative;
  width: 100px;
  height: 80px;
  border-radius: 12px;
  overflow: hidden;
  background: #f1f5f9;
  flex-shrink: 0;
  cursor: pointer;
}
.thumb-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.no-thumb {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #94a3b8;
  font-size: 10px;
}
.hazard-id-tag {
  position: absolute;
  top: 4px;
  left: 4px;
  background: rgba(15, 23, 42, 0.75);
  color: #ffffff;
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 4px;
}

.card-main-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.info-top-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}

/* 状态徽章 */
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 8px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 700;
}
.status-pill .dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}
.status-0 { background: #f1f5f9; color: #475569; }
.status-1 { background: #eff6ff; color: #1d4ed8; }
.status-2 { background: #fff7ed; color: #c2410c; }
.status-3 { background: #f0fdf4; color: #15803d; border: 1px solid #bbf7d0; }
.status-pending-review { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.status-pending-review .dot { background: #d97706; }
.status-4 { background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }

.category-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e2e8f0;
}
.address-text {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.hazard-desc-text {
  font-size: 13px;
  color: #1e293b;
  margin: 0 0 8px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.meta-bottom-row {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 11px;
  color: #64748b;
}
.meta-item .lbl {
  color: #94a3b8;
}
.highlight-handler {
  color: #1a73e8;
  font-weight: 600;
}
.review-val {
  color: #dc2626;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.text-muted {
  color: #94a3b8;
}
.date-val {
  margin-left: auto;
  color: #94a3b8;
}

/* 右侧动作控制条 */
.card-action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.action-btn-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.action-flow-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 14px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.action-flow-btn:hover {
  transform: translateY(-1px);
}
.btn-assign {
  background: #1a73e8;
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(26, 115, 232, 0.25);
}
.btn-sub-assign {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
}
.btn-accept {
  background: #1a73e8;
  color: #ffffff;
}
.btn-start {
  background: #ea580c;
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(234, 88, 12, 0.25);
}
.btn-complete {
  background: #16a34a;
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.25);
}
.btn-pass-quick {
  background: #16a34a;
  color: #ffffff;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.25);
}
.btn-reassign {
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  color: #334155;
}
.btn-reject {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #dc2626;
}

.flow-wait-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: 9999px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  color: #b45309;
  font-size: 12px;
  font-weight: 600;
}
.flow-inprogress-tag {
  font-size: 12px;
  color: #ea580c;
  font-weight: 600;
  padding: 4px 8px;
}
.flow-done-tag {
  font-size: 12px;
  color: #16a34a;
  font-weight: 600;
  padding: 4px 8px;
}
.flow-rejected-tag {
  font-size: 12px;
  color: #dc2626;
  font-weight: 600;
  padding: 4px 8px;
}
.other-handler-tag {
  font-size: 12px;
  color: #64748b;
  padding: 4px 8px;
}
.user-flow-status {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: 9999px;
  background: #f1f5f9;
  color: #475569;
}
.user-flow-status.user-status-0 {
  background: #eff6ff;
  color: #1d4ed8;
}
.user-flow-status.user-status-1 {
  background: #fef3c7;
  color: #b45309;
}
.user-flow-status.user-status-2 {
  background: #e0e7ff;
  color: #4338ca;
}
.user-flow-status.user-status-3 {
  background: #ecfdf5;
  color: #047857;
}
.user-flow-status.user-status-4 {
  background: #fef2f2;
  color: #b91c1c;
}

.view-detail-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: 9999px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.view-detail-btn:hover {
  background: #ffffff;
  border-color: #1a73e8;
  color: #1a73e8;
}

/* 浮动批量操作条 */
.batch-bar-container {
  position: fixed;
  bottom: 28px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  z-index: 999;
  padding: 0 20px;
  pointer-events: none;
}
.batch-floating-card {
  pointer-events: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 12px 24px;
  border-radius: 9999px;
  background: rgba(15, 23, 42, 0.92);
  backdrop-filter: blur(16px);
  box-shadow: 0 16px 36px rgba(0, 0, 0, 0.24), 0 0 0 1px rgba(255, 255, 255, 0.15);
  color: #ffffff;
}
.batch-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.batch-count-pill {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #1a73e8;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 13px;
}
.batch-text-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.batch-title {
  font-size: 13px;
  font-weight: 700;
  color: #ffffff;
}
.batch-sub {
  font-size: 11px;
  color: #94a3b8;
}

.batch-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.batch-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.batch-btn:hover {
  transform: translateY(-1px);
}
.btn-batch-pass {
  background: #16a34a;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(22, 163, 74, 0.35);
}
.btn-batch-pass:hover {
  background: #15803d;
}
.btn-batch-reject {
  background: #dc2626;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.35);
}
.btn-batch-reject:hover {
  background: #b91c1c;
}
.btn-batch-clear {
  background: rgba(255, 255, 255, 0.15);
  color: #e2e8f0;
}
.btn-batch-clear:hover {
  background: rgba(255, 255, 255, 0.25);
  color: #ffffff;
}

/* 模态框 */
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-box {
  width: 90%;
  max-width: 480px;
  background: #ffffff;
  border-radius: 20px;
  padding: 24px;
  box-shadow: 0 20px 48px rgba(0, 0, 0, 0.16);
  border: 1px solid rgba(0, 0, 0, 0.08);
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
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
.modal-subtitle {
  margin: 3px 0 0;
  font-size: 12px;
  color: #94a3b8;
}
.assign-modal-box {
  max-width: 720px;
  max-height: min(88vh, 760px);
  overflow-y: auto;
}
.modal-close-btn {
  background: transparent;
  border: none;
  font-size: 16px;
  color: #94a3b8;
  cursor: pointer;
}
.modal-hint {
  font-size: 13px;
  color: #475569;
  margin-bottom: 16px;
  line-height: 1.5;
}
.highlight-id {
  color: #1a73e8;
  font-weight: 700;
}
.batch-selected-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 80px;
  overflow-y: auto;
  padding: 8px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}
.batch-chip {
  font-size: 11px;
  background: #eff6ff;
  color: #1d4ed8;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid #bfdbfe;
}
.text-pass {
  color: #16a34a;
}
.text-reject {
  color: #dc2626;
}

.form-group {
  margin-bottom: 14px;
}
.form-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 6px;
}
.form-input {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.form-input:focus {
  border-color: #1a73e8;
}
.form-textarea {
  width: 100%;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid #cbd5e1;
  font-size: 13px;
  outline: none;
  resize: vertical;
  box-sizing: border-box;
}
.form-textarea:focus {
  border-color: #1a73e8;
}

.quick-pick-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
}
.quick-label {
  font-size: 12px;
  color: #64748b;
}
.quick-pick-btn {
  padding: 4px 10px;
  border-radius: 6px;
  border: 1px solid #e2e8f0;
  background: #f8fafc;
  font-size: 11px;
  font-weight: 600;
  color: #475569;
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
  padding: 4px 8px;
  border-radius: 6px;
}
.badge-reject {
  background: #fef2f2;
  color: #dc2626;
}
.badge-pass {
  background: #f0fdf4;
  color: #16a34a;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 20px;
}
.modal-btn {
  padding: 8px 18px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
}
.modal-btn.cancel {
  background: #f1f5f9;
  color: #475569;
}
.modal-btn.confirm {
  background: #1a73e8;
  color: #ffffff;
}
.modal-btn.confirm-pass {
  background: #16a34a;
  color: #ffffff;
}
.modal-btn.confirm-reject {
  background: #dc2626;
  color: #ffffff;
}
.modal-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 动效 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}
.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(30px);
}

.custom-checkbox.disabled-checkbox {
  opacity: 0.28;
  cursor: not-allowed;
  background: rgba(148, 163, 184, 0.15);
  border-color: #cbd5e1;
}
.custom-checkbox.disabled-checkbox:hover {
  border-color: #cbd5e1;
  background: rgba(148, 163, 184, 0.15);
}
.disabled-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #94a3b8;
}
.quick-select-btn.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 移动端与窄屏响应式自适应 */
@media (max-width: 767px) {
  .content-wrapper {
    padding: 12px 10px 40px;
  }
  
  /* 顶部导航瘦身：由底部导航承载，顶栏保持精简 */
  .page-header {
    flex-wrap: wrap;
    gap: 10px;
    padding-bottom: 12px;
  }
  .header-left .back-btn,
  .header-right .map-shortcut {
    display: none !important;
  }
  .system-tag {
    font-size: 11px;
  }
  .page-title {
    font-size: 18px;
  }
  .refresh-btn {
    padding: 6px 12px;
    font-size: 12px;
  }

  /* 状态 Tabs 单行水平流畅滑动 */
  .filters-bar {
    padding: 12px 10px;
    border-radius: 14px;
  }
  .status-tabs {
    display: flex;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    white-space: nowrap;
    padding-bottom: 4px;
    scrollbar-width: none;
    gap: 6px;
  }
  .status-tabs::-webkit-scrollbar {
    display: none;
  }
  .status-tab-btn {
    flex-shrink: 0;
    padding: 6px 10px;
    font-size: 12px;
  }
  .tab-count {
    font-size: 10px;
    padding: 1px 5px;
  }

  /* 类别 Chips 水平滑动 */
  .filter-bottom-row {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .category-chips {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    white-space: nowrap;
    scrollbar-width: none;
    padding-bottom: 4px;
  }
  .category-chips::-webkit-scrollbar {
    display: none;
  }
  .chip-btn {
    flex-shrink: 0;
    padding: 4px 10px;
  }
  .admin-quick-select {
    width: 100%;
    flex-wrap: wrap;
  }

  /* 工单卡片在移动端自适应为纵向卡片流 */
  .hazard-card {
    flex-direction: column;
    align-items: stretch;
    padding: 14px;
    gap: 12px;
    border-radius: 14px;
    position: relative;
  }
  .hazard-card .card-select-cell {
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 2;
  }
  .card-thumb-area {
    width: 100%;
    height: 140px;
    border-radius: 10px;
  }
  .card-main-info {
    width: 100%;
  }
  .info-top-row {
    flex-wrap: wrap;
    gap: 6px;
  }
  .hazard-desc-text {
    font-size: 13px;
    -webkit-line-clamp: 3;
  }
  .meta-bottom-row {
    flex-wrap: wrap;
    gap: 8px;
    font-size: 11px;
  }
  .card-action-bar {
    width: 100%;
    justify-content: flex-end;
    padding-top: 8px;
    border-top: 1px solid rgba(0, 0, 0, 0.05);
  }
  .action-flow-btn, .view-detail-btn {
    padding: 6px 14px;
    font-size: 12px;
  }

  /* 批量操作浮动栏位置抬升，避免遮挡底部导航 */
  .batch-bar-container {
    bottom: calc(64px + env(safe-area-inset-bottom, 0px)) !important;
    padding: 0 10px;
  }
  .batch-bar {
    width: 100%;
    padding: 8px 14px;
    flex-direction: column;
    gap: 8px;
  }
  .batch-bar-right {
    width: 100%;
    justify-content: flex-end;
  }
}

/* ========================================================
   普通市民专属：视角切换栏 (我的上报 vs 全城公示)
======================================================== */
.citizen-view-switcher {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.02);
  margin-bottom: 18px;
}

.switcher-pills {
  display: flex;
  align-items: center;
  gap: 10px;
}

.switcher-pill-btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 7px 15px;
  border-radius: 9999px;
  border: 1px solid rgba(0, 0, 0, 0.07);
  background: #f8fafc;
  color: #475569;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
}

.switcher-pill-btn:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.switcher-pill-btn.active {
  background: #1a73e8;
  color: #ffffff;
  border-color: #1a73e8;
  box-shadow: 0 3px 12px rgba(26, 115, 232, 0.25);
}

.switcher-pill-btn .pill-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9999px;
  font-size: 11px;
  font-weight: 700;
  background: rgba(0, 0, 0, 0.08);
  color: inherit;
}

.switcher-pill-btn.active .pill-count {
  background: rgba(255, 255, 255, 0.24);
  color: #ffffff;
}

.switcher-pill-btn .pill-tag {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 9999px;
  background: #dcfce7;
  color: #15803d;
  font-weight: 600;
}

.switcher-pill-btn.active .pill-tag {
  background: rgba(255, 255, 255, 0.25);
  color: #ffffff;
}

.switcher-tip {
  font-size: 12px;
  color: #64748b;
  font-weight: 400;
}

/* ========================================================
   城市安全 · 全民共治服务大厅 (精致引导看板，消灭冷清感)
======================================================== */
.citizen-hall-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 44px 32px 40px;
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(248, 250, 252, 0.92) 100%);
  backdrop-filter: blur(16px);
  border: 1px solid rgba(26, 115, 232, 0.12);
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.03), 0 1px 3px rgba(0, 0, 0, 0.02);
  margin: 12px 0 32px;
  position: relative;
  overflow: hidden;
}

.hall-badge-wrap {
  position: relative;
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 18px;
}

.hall-shield-badge {
  width: 64px;
  height: 64px;
  border-radius: 20px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(26, 115, 232, 0.16);
  position: relative;
  z-index: 2;
}

.hall-pulse-ring {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  border-radius: 24px;
  border: 2px solid rgba(26, 115, 232, 0.35);
  animation: hallPulse 2.8s infinite cubic-bezier(0.25, 0.8, 0.25, 1);
  z-index: 1;
}

@keyframes hallPulse {
  0% { transform: scale(0.9); opacity: 0.8; }
  50% { transform: scale(1.15); opacity: 0.2; }
  100% { transform: scale(0.9); opacity: 0.8; }
}

.hall-header-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
}

.hall-pill-tag {
  font-size: 11px;
  font-weight: 600;
  padding: 3px 12px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  letter-spacing: 0.5px;
}

.hall-title {
  font-size: 24px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
  margin: 0;
}

.hall-subtitle {
  font-size: 14px;
  color: #64748b;
  margin: 0;
}

.hall-intro {
  max-width: 680px;
  font-size: 13px;
  line-height: 1.7;
  color: #475569;
  margin: 0 0 28px;
}

.governance-steps-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  width: 100%;
  max-width: 880px;
  margin-bottom: 32px;
}

.step-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18px 14px;
  background: #ffffff;
  border-radius: 14px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.step-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.04);
}

.step-badge {
  font-size: 10px;
  font-weight: 700;
  color: #1a73e8;
  background: #f1f5f9;
  padding: 2px 8px;
  border-radius: 9999px;
  margin-bottom: 8px;
}

.step-icon {
  font-size: 26px;
  line-height: 1;
  margin-bottom: 8px;
}

.step-name {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 4px;
}

.step-desc {
  font-size: 11px;
  color: #64748b;
  line-height: 1.45;
  text-align: center;
}

.hall-actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  flex-wrap: wrap;
}

.btn-hall-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 11px 24px;
  border-radius: 9999px;
  background: #1a73e8;
  color: #ffffff;
  font-size: 14px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  box-shadow: 0 4px 14px rgba(26, 115, 232, 0.3);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.btn-hall-primary:hover {
  background: #1557b0;
  transform: translateY(-1px);
  box-shadow: 0 6px 18px rgba(26, 115, 232, 0.38);
}

.btn-hall-secondary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 11px 22px;
  border-radius: 9999px;
  background: #ffffff;
  color: #334155;
  font-size: 14px;
  font-weight: 600;
  border: 1px solid rgba(0, 0, 0, 0.1);
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.btn-hall-secondary:hover {
  background: #f8fafc;
  border-color: #1a73e8;
  color: #1a73e8;
  transform: translateY(-1px);
}

/* ========================================================
   顺丰物流式透明全生命周期步进轴 (四节点时间线)
======================================================== */
.logistic-timeline-bar {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed rgba(0, 0, 0, 0.07);
  width: 100%;
}

.timeline-track {
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
  width: 100%;
}

.timeline-node {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
  position: relative;
  z-index: 2;
}

.node-dot {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  background: #f1f5f9;
  border: 1.5px solid #cbd5e1;
  color: #64748b;
  transition: all 0.25s ease;
}

.timeline-node.completed .node-dot {
  background: #ecfdf5;
  border-color: #10b981;
  color: #059669;
}

.timeline-node.current .node-dot {
  background: #eff6ff;
  border-color: #1a73e8;
  color: #1a73e8;
  box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.16);
}

.timeline-node.rejected .node-dot {
  background: #fef2f2;
  border-color: #ef4444;
  color: #dc2626;
  box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.15);
}

.node-text {
  display: flex;
  flex-direction: column;
}

.node-label {
  font-size: 12px;
  font-weight: 600;
  color: #475569;
}

.timeline-node.completed .node-label {
  color: #0f172a;
}

.timeline-node.current .node-label {
  color: #1a73e8;
  font-weight: 700;
}

.timeline-node.rejected .node-label {
  color: #dc2626;
}

.node-sub {
  font-size: 10px;
  color: #94a3b8;
}

.timeline-node.current .node-sub {
  color: #3b82f6;
}

.timeline-line {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 10px;
  transition: background 0.3s ease;
  position: relative;
}

.timeline-line.active {
  background: #10b981;
}


/* 管理员派单/改派人员选择器 */
.assign-context-strip {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 11px 13px;
  margin-bottom: 16px;
  border-radius: 12px;
  background: #f4f8ff;
  border: 1px solid #dbeafe;
  color: #475569;
  font-size: 12px;
  line-height: 1.55;
}
.assign-context-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: #1a73e8;
  box-shadow: 0 0 0 4px rgba(26, 115, 232, 0.1);
}
.handler-search-group {
  margin-bottom: 12px;
}
.handler-search-wrap {
  position: relative;
}
.handler-search-wrap > svg {
  position: absolute;
  left: 13px;
  top: 50%;
  transform: translateY(-50%);
  color: #94a3b8;
  pointer-events: none;
}
.handler-search-wrap .form-input {
  padding: 11px 13px 11px 38px;
  border-radius: 12px;
  background: #ffffff;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}
.handler-search-wrap .form-input:focus {
  border-color: #1a73e8;
  box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.1);
}
.handler-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  max-height: 330px;
  overflow-y: auto;
  padding: 2px;
}
.handler-card {
  position: relative;
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
  padding: 13px 12px;
  text-align: left;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.09);
  border-radius: 15px;
  cursor: pointer;
  transition: transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), border-color 0.18s ease, box-shadow 0.18s ease, background 0.18s ease;
}
.handler-card:hover {
  transform: translateY(-1px);
  border-color: rgba(26, 115, 232, 0.35);
  box-shadow: 0 8px 20px rgba(26, 115, 232, 0.08);
}
.handler-card.selected {
  border-color: #1a73e8;
  background: #f4f8ff;
  box-shadow: 0 0 0 2px rgba(26, 115, 232, 0.1);
}
.handler-avatar {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  display: grid;
  place-items: center;
  border-radius: 13px;
  background: linear-gradient(135deg, #1a73e8, #60a5fa);
  color: #ffffff;
  font-size: 15px;
  font-weight: 700;
  box-shadow: 0 5px 12px rgba(26, 115, 232, 0.2);
}
.handler-copy {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding-right: 16px;
}
.handler-name {
  overflow: hidden;
  color: #0f172a;
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.handler-email {
  overflow: hidden;
  margin-top: 2px;
  color: #64748b;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.handler-id {
  margin-top: 3px;
  color: #94a3b8;
  font-size: 10px;
}
.handler-current {
  position: absolute;
  top: 7px;
  right: 7px;
  padding: 2px 6px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 9px;
  font-weight: 600;
}
.handler-check {
  position: absolute;
  right: 9px;
  bottom: 9px;
  width: 18px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #1a73e8;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
}
.handler-state {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-height: 132px;
  padding: 24px 16px;
  border: 1px dashed #dbe3ef;
  border-radius: 15px;
  background: #fbfdff;
  color: #64748b;
  font-size: 12px;
}
.handler-state-error {
  color: #dc2626;
  border-color: #fecaca;
  background: #fff7f7;
}
.handler-state-spinner {
  width: 15px;
  height: 15px;
  border: 2px solid #dbeafe;
  border-top-color: #1a73e8;
  border-radius: 50%;
  animation: handler-spin 0.8s linear infinite;
}
@keyframes handler-spin {
  to { transform: rotate(360deg); }
}
.handler-retry {
  padding: 3px 9px;
  border: 1px solid #fecaca;
  border-radius: 999px;
  background: #ffffff;
  color: #dc2626;
  font-size: 11px;
  cursor: pointer;
}
.selected-handler-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #edf2f7;
  color: #334155;
  font-size: 12px;
}
.selected-handler-summary .summary-label {
  padding: 2px 7px;
  border-radius: 999px;
  background: #e0f2fe;
  color: #0369a1;
  font-size: 10px;
  font-weight: 600;
}
.selected-handler-summary .num-font {
  margin-left: auto;
  color: #94a3b8;
}


/* 管理员撤回无效工单 */
.btn-admin-withdraw {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fed7aa;
}
.btn-admin-withdraw:hover {
  background: #ffedd5;
  border-color: #fb923c;
  color: #9a3412;
}
.admin-withdraw-modal {
  max-width: 560px;
}
.admin-withdraw-warning {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 12px 13px;
  margin-bottom: 16px;
  border-radius: 12px;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  color: #9a3412;
  font-size: 12px;
  line-height: 1.55;
}
.warning-dot {
  width: 7px;
  height: 7px;
  flex: 0 0 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: #f97316;
  box-shadow: 0 0 0 4px rgba(249, 115, 22, 0.12);
}
.required-mark {
  color: #dc2626;
}
.reason-counter {
  margin-top: 6px;
  text-align: right;
  color: #94a3b8;
  font-size: 10px;
}
.admin-withdraw-error {
  margin: 0;
  color: #dc2626;
  font-size: 12px;
}

/* 手机端响应式适配 */
@media (max-width: 768px) {
  .citizen-view-switcher {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 14px;
  }
  .switcher-pills {
    width: 100%;
  }
  .switcher-pill-btn {
    flex: 1;
    justify-content: center;
    padding: 6px 10px;
    font-size: 12px;
  }
  .switcher-tip {
    font-size: 11px;
  }

  .citizen-hall-card {
    padding: 28px 16px 24px;
  }
  .hall-title {
    font-size: 20px;
  }
  .hall-subtitle {
    font-size: 13px;
  }
  .governance-steps-grid {
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 24px;
  }
  .step-card {
    padding: 12px 8px;
  }
  .step-desc {
    display: none; /* 移动端精简步骤卡片，突出名称与图标 */
  }
  .hall-actions {
    width: 100%;
    flex-direction: column;
    gap: 10px;
  }
  .btn-hall-primary, .btn-hall-secondary {
    width: 100%;
    justify-content: center;
    padding: 10px 16px;
    font-size: 13px;
  }

  /* 移动端物流时间轴紧凑呈现 */
  .timeline-node .node-sub {
    display: none;
  }
  .timeline-node .node-label {
    font-size: 11px;
  }

  .assign-modal-box,
  .admin-withdraw-modal {
    max-height: 90vh;
    padding: 18px;
  }
  .handler-grid {
    grid-template-columns: 1fr;
    max-height: 46vh;
  }
  .timeline-line {
    margin: 0 4px;
  }
}


.status-5, .status-withdrawn { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }
.status-5 .dot, .status-withdrawn .dot { background: #94a3b8; }
.user-flow-status.user-status-5 { background: #f8fafc; color: #64748b; border: 1px solid #e2e8f0; }

.btn-withdraw {
  background: #fff1f2;
  color: #e11d48;
  border: 1px solid #fecdd3;
  box-shadow: 0 1px 3px rgba(225, 29, 72, 0.08);
}
.btn-withdraw:hover {
  background: #ffe4e6;
  color: #be123c;
  border-color: #fda4af;
}
.btn-withdraw:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.tab-withdrawn.active {
  border-color: #cbd5e1;
  background: #f1f5f9;
  color: #475569;
}

.admin-stats-bar {
  display: flex;
  align-items: center;
  justify-content: space-around;
  padding: 12px 20px;
  margin-bottom: 16px;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(226, 232, 240, 0.8);
  border-radius: 14px;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.03);
}
.stat-pill-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  cursor: default;
}
.stat-pill-item.stat-pill-withdrawn {
  cursor: pointer;
  padding: 4px 10px;
  border-radius: 8px;
  transition: all 0.2s ease;
}
.stat-pill-item.stat-pill-withdrawn:hover,
.stat-pill-item.stat-pill-withdrawn.active {
  background: #f1f5f9;
}
.stat-pill-label {
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
}
.stat-pill-val {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
}
.stat-pill-val.text-warning { color: #d97706; }
.stat-pill-val.text-success { color: #16a34a; }
.stat-pill-val.text-primary { color: #1a73e8; }
.stat-pill-val.text-muted { color: #64748b; }
.stat-pill-tip {
  font-size: 10px;
  color: #94a3b8;
}
.stat-pill-divider {
  width: 1px;
  height: 28px;
  background: #e2e8f0;
}

</style>


