<template>
  <div class="hazard-detail-view">
    <div class="content-wrapper">
      <!-- 头部返回与标题条 -->
      <header class="page-header">
        <div class="header-left">
          <router-link to="/hazard" class="back-btn" title="返回工单列表">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            <span class="desktop-text">返回工单列表</span>
            <span class="mobile-text">返回</span>
          </router-link>
          <div class="header-titles">
            <span class="system-tag">三明市城市安全综合治理工单系统</span>
            <h1 class="page-title">隐患处置工单档案与全生命周期流转</h1>
          </div>
        </div>

        <div class="header-right" v-if="hazard">
          <button
            v-if="canWithdraw"
            type="button"
            class="header-withdraw-btn"
            :disabled="actionLoading"
            @click="handleWithdraw"
            title="撤回后该上报记录只对管理员可见"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
              <path d="M3 10h10a5 5 0 0 1 5 5v2"/>
              <polyline points="7 6 3 10 7 14"/>
            </svg>
            <span>{{ actionLoading ? '撤回中...' : '撤回上报' }}</span>
          </button>
        </div>
      </header>

      <!-- 主体内容 -->
      <main class="main-content">
        <!-- 加载状态 -->
        <div v-if="loading" class="state-card glass-card">
          <div class="spinner"></div>
          <p>正在载入隐患工单全要素档案与流转动态...</p>
        </div>

        <!-- 错误提示 -->
        <div v-else-if="errorMessage" class="state-card glass-card error-card">
          <p class="error-msg">{{ errorMessage }}</p>
          <button class="btn-pill btn-pill-primary" @click="goBack">返回工单列表</button>
        </div>

        <!-- 详情核心看板 -->
        <article v-else-if="hazard" class="detail-container">
          <!-- 撤回特别提示栏 (若工单处于已撤回状态) -->
          <div v-if="hazard.status === 5" class="withdrawn-alert-card">
            <div class="alert-icon">ℹ️</div>
            <div class="alert-content">
              <h4 class="alert-title">
                {{ hazard.withdrawnBy && hazard.userId && Number(hazard.withdrawnBy) !== Number(hazard.userId) ? '本隐患工单已被管理员撤回' : '本隐患工单已被上报人主动撤回' }}
              </h4>
              <p class="alert-desc">
                该工单已终止处置流转，当前仅对系统管理员可见。撤回状态：{{ hazard.statusText || '已撤回' }}。
              </p>
              <p v-if="hazard.withdrawnReason" class="withdrawn-reason-text">
                撤回原因：{{ hazard.withdrawnReason }}
              </p>
            </div>
          </div>

          <!-- 驳回特别警示栏 (若工单处于已驳回状态) -->
          <div v-else-if="hazard.status === 4" class="rejection-alert-card">
            <div class="alert-icon">⚠️</div>
            <div class="alert-content">
              <h4 class="alert-title">本隐患工单已被指挥中心审查驳回 / 要求返工</h4>
              <p class="alert-desc">
                审查判定意见：{{ hazard.reviewRemark || '经指挥调度中心现场勘查核准，现场整改未达标或存在不符合立案规范的情况，请专员及时排险返工。' }}
              </p>
            </div>
          </div>

          <!-- 待验收特别提示栏 (若工单处于待验收状态) -->
          <div v-else-if="isPendingReview" class="pending-alert-card">
            <div class="alert-icon">⏳</div>
            <div class="alert-content">
              <h4 class="alert-title">现场整改已申报完毕，当前处于【待终审验收】阶段</h4>
              <p class="alert-desc">
                责任专员已完成现场处置，工单已进入质量验收卡口，需由调度指挥中心进行实地或影像复核并核准终审办结。
              </p>
            </div>
          </div>

          <!-- 顶部生命周期流转步进条 Stepper (精准五态流转节点) -->
          <section class="lifecycle-stepper-card glass-card">
            <div class="stepper-title">工单全生命周期流转节点</div>
            <div class="stepper-track">
              <!-- 节点 1: 发现建单 -->
              <div class="step-node" :class="{ done: hazard.status >= 0, active: hazard.status === 0 || hazard.status === 5, 'step-withdrawn': hazard.status === 5 }">
                <div class="node-circle num-font">{{ hazard.status === 5 ? '↩' : '1' }}</div>
                <div class="node-text">
                  <div class="main-txt">现场发现上报</div>
                  <div class="sub-txt">{{ hazard.status === 5 ? '已主动撤回' : '系统建单立案' }}</div>
                </div>
              </div>

              <div class="step-link-line" :class="{ active: hazard.status >= 1 && hazard.status !== 4 && hazard.status !== 5 }"></div>

              <!-- 节点 2: 专员接单/派单 -->
              <div class="step-node" :class="{ done: (hazard.status >= 1 && hazard.status !== 4), active: hazard.status === 1 }">
                <div class="node-circle num-font">2</div>
                <div class="node-text">
                  <div class="main-txt">责任专员派发</div>
                  <div class="sub-txt">{{ hazard.handlerId ? '已指派责任专员' : '待调度派发' }}</div>
                </div>
              </div>

              <div class="step-link-line" :class="{ active: hazard.status >= 2 && hazard.status !== 4 }"></div>

              <!-- 节点 3: 施工整改 -->
              <div class="step-node" :class="{ done: (hazard.status >= 2 && hazard.status !== 4), active: hazard.status === 2 }">
                <div class="node-circle num-font">3</div>
                <div class="node-text">
                  <div class="main-txt">现场施工整改</div>
                  <div class="sub-txt">{{ hazard.status >= 2 && hazard.status !== 4 ? '现场作业完成' : '待施工' }}</div>
                </div>
              </div>

              <div class="step-link-line" :class="{ active: hazard.status === 3 || hazard.status === 4 }"></div>

              <!-- 节点 4: 终审验收卡口 -->
              <div
                class="step-node"
                :class="{
                  done: (hazard.status === 3 && hazard.reviewed == 1),
                  active: isPendingReview,
                  'step-warning': isPendingReview
                }"
              >
                <div class="node-circle num-font">4</div>
                <div class="node-text">
                  <div class="main-txt">指挥长终审验收</div>
                  <div class="sub-txt">{{ isPendingReview ? '等待质量复核' : ((hazard.status === 3 && hazard.reviewed == 1) ? '终审已核准' : '待提交验收') }}</div>
                </div>
              </div>

              <div class="step-link-line" :class="{ active: (hazard.status === 3 && hazard.reviewed == 1) || hazard.status === 4 }"></div>

              <!-- 节点 5: 办结归档或驳回 -->
              <div
                class="step-node"
                :class="{
                  done: (hazard.status === 3 && hazard.reviewed == 1) || hazard.status === 4,
                  active: (hazard.status === 3 && hazard.reviewed == 1) || hazard.status === 4,
                  'step-rejected': hazard.status === 4
                }"
              >
                <div class="node-circle num-font">{{ hazard.status === 4 ? '✕' : '5' }}</div>
                <div class="node-text">
                  <div class="main-txt">{{ hazard.status === 4 ? '审查驳回' : '办结归档' }}</div>
                  <div class="sub-txt">{{ hazard.status === 4 ? '退回返工' : ((hazard.status === 3 && hazard.reviewed == 1) ? '已彻底闭环' : '未完结') }}</div>
                </div>
              </div>
            </div>
          </section>

          <!-- 双栏展示网格 -->
          <div class="detail-grid">
            <!-- 左栏：现场影像与空间地理坐标 -->
            <div class="left-col">
              <!-- 现场影像原件 -->
              <section class="section-card image-section-card glass-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/>
                    <circle cx="12" cy="13" r="4"/>
                  </svg>
                  <span>现场取证影像</span>
                </div>
                <div class="image-stage" :class="{ 'no-image-stage': !hazard.imageUrl }">
                  <SecureImage v-if="hazard.imageUrl" :src="hazard.imageUrl" alt="隐患现场取证" class="stage-img" />
                  <div v-else class="no-img-text">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.8">
                      <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
                      <circle cx="9" cy="9" r="2"/>
                      <path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/>
                    </svg>
                    <span>未附加现场留存影像</span>
                  </div>
                </div>
              </section>

              <!-- 空间地理信息 -->
              <section class="section-card geo-section-card glass-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/>
                    <circle cx="12" cy="10" r="3"/>
                  </svg>
                  <span>地理位置与片区标定</span>
                </div>
                <div class="geo-info-box">
                  <div class="geo-row">
                    <span class="geo-label">详细地址：</span>
                    <span class="geo-val">{{ hazard.address || '三明市辖区' }}</span>
                  </div>
                  <div class="geo-row" v-if="hazard.district">
                    <span class="geo-label">所属片区：</span>
                    <span class="geo-val">{{ hazard.district }}</span>
                  </div>
                  <div class="geo-row" v-if="hazard.longitude && hazard.latitude">
                    <span class="geo-label">经纬度标定：</span>
                    <span class="geo-val num-font">{{ hazard.longitude }}, {{ hazard.latitude }}</span>
                  </div>
                  <router-link to="/map" class="map-link-btn">
                    <span>在地图中查看点位态势 →</span>
                  </router-link>
                </div>
              </section>
            </div>

            <!-- 右栏：工单属性、描述与动作流转控制器 -->
            <div class="right-col">
              <!-- 工单核心属性与描述 -->
              <section class="section-card prop-section-card glass-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                    <polyline points="14 2 14 8 20 8"/>
                  </svg>
                  <span>工单属性与问题描述</span>
                </div>

                <div class="tags-bar">
                  <span class="status-pill" :class="statusBadgeClass">
                    <span class="dot"></span>
                    <span>{{ statusDisplayLabel }}</span>
                  </span>
                  <span
                    v-for="cat in resolveHazardList(hazard.hazardTypes)"
                    :key="`${cat.majorCode}/${cat.subcategoryCode}`"
                    class="category-pill"
                  >{{ cat.displayText }}</span>
                </div>

                <div class="desc-box">
                  <span class="desc-label">现场特征简述：</span>
                  <p class="desc-content">{{ hazard.description || '暂无详细描述记录。' }}</p>
                </div>

                <div class="person-track-box">
                  <div class="track-row">
                    <span class="track-label">上报来源：</span>
                    <span class="track-val">市民上报</span>
                  </div>
                  <div class="track-row">
                    <span class="track-label">处理责任专员：</span>
                    <span class="track-val" :class="hazard.handlerId ? 'highlight-val' : 'text-muted'">
                      {{ hazard.handlerId ? '已指派责任专员' : '暂无专员认领' }}
                    </span>
                  </div>
                  <div class="track-row">
                    <span class="track-label">建单记录时间：</span>
                    <span class="track-val num-font">{{ formatDate(hazard.createTime) }}</span>
                  </div>
                  <div class="track-row" v-if="hazard.reviewRemark">
                    <span class="track-label">指挥审核意见：</span>
                    <span class="track-val highlight-remark">{{ hazard.reviewRemark }}</span>
                  </div>
                </div>
              </section>

              <!-- 动作流转协同控制台 (严格依据职责分离与终审把关机制) -->
              <section class="section-card glass-card action-console-card">
                <div class="card-head">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1a73e8" stroke-width="2">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                  </svg>
                  <span>工单调度流转协同控制台</span>
                </div>

                <!-- 创建人本人且未被接单 (status === 0) 时的撤回操作卡片 -->
                <div v-if="canWithdraw" class="withdraw-console-card">
                  <div class="withdraw-tip">
                    <span class="tip-badge">本人上报</span>
                    <span class="tip-text">该隐患为本人发现并上报，且尚未被专员接单受理。如属误报或现场隐患已消除，可在此主动撤回。</span>
                  </div>
                  <button
                    type="button"
                    class="flow-btn btn-withdraw"
                    :disabled="actionLoading"
                    @click="handleWithdraw"
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2">
                      <path d="M3 10h10a5 5 0 0 1 5 5v2"/>
                      <polyline points="7 6 3 10 7 14"/>
                    </svg>
                    <span>{{ actionLoading ? '撤回中...' : '撤回此工单上报' }}</span>
                  </button>
                </div>

                <!-- 已撤回终止状态 -->
                <div v-if="hazard.status === 5" class="withdrawn-status-box">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#64748b" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="12" y1="8" x2="12" y2="12"/>
                    <line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  <span>本工单已由上报人主动撤回，流转已终止并归档隔离</span>
                </div>

                <!-- 管理员操作面板 -->
                <div v-if="userRole === '1'" class="flow-actions-wrapper">
                  <div class="flow-tip-text">
                    {{ adminActionHint }}
                  </div>

                  <div class="actions-grid">
                    <!-- 待处理 (0): 派发责任人 + 审查驳回 -->
                    <template v-if="hazard.status === 0">
                      <button class="flow-btn btn-accept" :disabled="actionLoading" @click="openAssignModal">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                        <span>调度派发责任专员</span>
                      </button>
                      <button class="flow-btn btn-admin-withdraw" :disabled="actionLoading" @click="openAdminWithdrawModal">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M3 10h10a5 5 0 0 1 5 5v2"/><polyline points="7 6 3 10 7 14"/></svg>
                        <span>撤回无效工单</span>
                      </button>
                    </template>

                    <!-- 已接单 (1): 重新派单 + 审查驳回 -->
                    <template v-else-if="hazard.status === 1">
                      <div class="sub-actions-row">
                        <button class="flow-btn-sm btn-sub-assign" :disabled="actionLoading" @click="openAssignModal">
                          重新指定责任人
                        </button>
                        <button class="flow-btn-sm btn-admin-withdraw" :disabled="actionLoading" @click="openAdminWithdrawModal">
                          终止并撤回
                        </button>
                      </div>
                    </template>

                    <!-- 整改中 (2): 监督整改进度 + 审查驳回 -->
                    <template v-else-if="hazard.status === 2">
                      <div class="inprogress-banner">
                        <span class="badge-dot"></span>
                        <span>责任专员正在现场整改施工中，等待现场标记完工后终审验收。</span>
                      </div>
                      <button class="flow-btn btn-admin-withdraw mt-2" :disabled="actionLoading" @click="openAdminWithdrawModal">
                        终止并撤回
                      </button>
                    </template>

                    <!-- 待验收 (3 且 reviewed = 0): 调度管理员终审质量复核把关 -->
                    <template v-else-if="isPendingReview">
                      <div class="pending-review-action-box">
                        <h4 class="box-title">调度指挥长现场复核与终审评定：</h4>
                        <div class="button-dual-row">
                          <button class="flow-btn btn-complete-pass" :disabled="actionLoading" @click="submitDirectReview(true)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                              <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            <span>核准通过并办结归档</span>
                          </button>
                          <button class="flow-btn btn-reject-urgent" :disabled="actionLoading" @click="openReviewModal(false)">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                            </svg>
                            <span>整改未达标，驳回返工</span>
                          </button>
                        </div>
                      </div>
                    </template>

                    <!-- 已办结 (3 且 reviewed = 1) -->
                    <div v-else-if="hazard.status === 3 && hazard.reviewed == 1" class="finished-box">
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2">
                        <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
                        <polyline points="22 4 12 14.01 9 11.01"/>
                      </svg>
                      <span>本隐患治理任务已通过指挥中心终审验收，已全流程完结归档</span>
                    </div>

                    <!-- 已驳回 (4): 管理员可重新激活/派单返工 -->
                    <div v-else-if="hazard.status === 4" class="rejected-box">
                      <p>该工单当前已被驳回。点击下方按钮重新指定责任人，即可下达返工整改任务：</p>
                      <button class="flow-btn btn-accept mt-2" :disabled="actionLoading" @click="openAssignModal">
                        重新指派专员返工
                      </button>
                    </div>
                  </div>
                </div>

                <!-- 处置专员操作面板 -->
                <div v-else-if="userRole === '2'" class="flow-actions-wrapper">
                  <!-- 待认领工单 -->
                  <div v-if="hazard.status === 0" class="actions-grid">
                    <div class="flow-tip-text">本工单尚未指定专员，您可以主动认领负责。</div>
                    <button class="flow-btn btn-accept" :disabled="actionLoading" @click="executeFlow('accept')">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
                      <span>认领此工单</span>
                    </button>
                  </div>

                  <!-- 专员自己的任务 -->
                  <div v-else-if="isAssignedToMe" class="actions-grid">
                    <div class="flow-tip-text">{{ handlerActionHint }}</div>

                    <!-- 1: 已接单 -> 开始整改 -->
                    <button
                      v-if="hazard.status === 1"
                      class="flow-btn btn-start"
                      :disabled="actionLoading"
                      @click="executeFlow('start')"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                      <span>开始进场施工整改</span>
                    </button>

                    <!-- 2: 整改中 -> 提交验收 -->
                    <button
                      v-else-if="hazard.status === 2"
                      class="flow-btn btn-complete"
                      :disabled="actionLoading"
                      @click="executeFlow('complete')"
                    >
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                      <span>整改完毕，提交终审验收</span>
                    </button>

                    <!-- 待验收状态 (3 且 reviewed=0): 专员等待终审把关 -->
                    <div v-else-if="isPendingReview" class="pending-wait-box">
                      <div class="wait-icon-large">⏳</div>
                      <div class="wait-text">
                        <h4>现场整改已申报，等待调度长终审验收</h4>
                        <p>您的整改完成报告已提交系统，指挥调度长正在进行质量复核，核准后将自动办结归档。</p>
                      </div>
                    </div>

                    <!-- 3 且 reviewed=1: 已办结 -->
                    <div v-else-if="hazard.status === 3 && hazard.reviewed == 1" class="finished-box">
                      <span>您负责的治理任务已顺利通过终审验收并归档 ✓</span>
                    </div>

                    <!-- 4: 已驳回 -->
                    <div v-else-if="hazard.status === 4" class="rejected-box">
                      <span>整改未达标或工单已被驳回，请等待指挥中心重新下发任务安排</span>
                    </div>
                  </div>

                  <!-- 其他专员的任务 -->
                  <div v-else class="other-handler-box">
                    <p v-if="hazard.handlerId">本工单已指定责任专员全程推进，您当前以同道专员身份查阅。</p>
                    <p v-else>该工单尚未指派责任专员。</p>
                  </div>
                </div>

                <!-- 普通市民巡查视角 -->
                <div v-else class="citizen-view-hint">
                  <p>您当前以市民/巡查员身份查看此工单。处理专员正在接单推进中，整改并通过终审验收后系统将在此同步闭环状态。</p>
                </div>
              </section>
            </div>
          </div>
        </article>
      </main>
    </div>

    <!-- 管理员派单模态框 -->
    <div v-if="assignModalVisible" class="modal-mask" @click.self="assignModalVisible = false">
      <div class="modal-box glass-card">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">📋</span>
            <h3 class="modal-title">工单调度指派</h3>
          </div>
          <button class="modal-close-btn" @click="assignModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <p class="modal-hint">
            正在为工单“{{ hazardTitle(hazard) }}”调度责任专员：
          </p>
          <div class="form-group">
            <label class="form-label">选择责任专员：</label>
            <select v-model="targetHandlerId" class="form-input handler-select" :disabled="handlerLoading">
              <option value="" disabled>请选择处理人员</option>
              <option v-for="handler in handlerOptions" :key="handler.id" :value="handler.id">
                {{ handler.nickname || handler.email || '未命名处理人员' }}{{ handler.email ? ' · ' + handler.email : '' }}
              </option>
            </select>
            <p v-if="handlerLoading" class="handler-select-hint">正在加载处理人员...</p>
            <p v-else-if="handlerError" class="handler-select-hint error">{{ handlerError }}</p>
            <p v-else-if="!handlerOptions.length" class="handler-select-hint">暂无可用处理人员</p>
          </div>
        </div>
        <div class="modal-footer">
          <button class="modal-btn cancel" @click="assignModalVisible = false">取消</button>
          <button
            class="modal-btn confirm"
            :disabled="!targetHandlerId || modalLoading"
            @click="submitAssign"
          >
            {{ modalLoading ? '指派中...' : '确认指派' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 管理员撤回无效工单模态框 -->
    <div v-if="adminWithdrawModalVisible" class="modal-mask" @click.self="closeAdminWithdrawModal">
      <div class="modal-box admin-withdraw-modal glass-card" data-testid="admin-withdraw-dialog">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">↩️</span>
            <div>
              <h3 class="modal-title">{{ hazard?.status === 0 ? '撤回无效工单' : '终止并撤回工单' }}</h3>
              <p class="modal-subtitle">工单：{{ hazardTitle(hazard) }}</p>
            </div>
          </div>
          <button class="modal-close-btn" @click="closeAdminWithdrawModal">✕</button>
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
          <button class="modal-btn cancel" @click="closeAdminWithdrawModal">取消</button>
          <button class="modal-btn confirm-reject" :disabled="!adminWithdrawReason.trim() || adminWithdrawLoading" @click="submitAdminWithdraw">
            {{ adminWithdrawLoading ? '撤回中...' : '确认撤回' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 管理员审查/驳回模态框 -->
    <div v-if="reviewModalVisible" class="modal-mask" @click.self="reviewModalVisible = false">
      <div class="modal-box glass-card">
        <div class="modal-header">
          <div class="modal-title-row">
            <span class="modal-icon">⚖️</span>
            <h3 class="modal-title">{{ reviewPass ? '工单终审核准办结' : '工单审查驳回 / 退回返工' }}</h3>
          </div>
          <button class="modal-close-btn" @click="reviewModalVisible = false">✕</button>
        </div>
        <div class="modal-body">
          <p class="modal-hint">
            工单“{{ hazardTitle(hazard) }}”终审意见批注：
          </p>
          <div class="form-group">
            <label class="form-label">判定说明 / 理由批注：</label>
            <textarea
              v-model="reviewRemark"
              rows="3"
              class="form-textarea"
              :placeholder="reviewPass ? '请输入核准办结意见，如：经现场复查合格，准予闭环归档。' : '请输入驳回理由，如：现场防护设施未完全清除，要求重新排险施工。'"
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
            {{ modalLoading ? '提交中...' : (reviewPass ? '确认核准办结' : '确认驳回返工') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import SecureImage from '../components/SecureImage.vue'
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { resolveHazardList } from '../constants/hazardTaxonomy.js'

const route = useRoute()
const router = useRouter()

const userRole = ref(localStorage.getItem('role') || '0')
const currentUserId = ref(Number(localStorage.getItem('userId')) || null)

const loading = ref(true)
const errorMessage = ref('')
const hazard = ref(null)
const actionLoading = ref(false)

// 派单弹窗
const assignModalVisible = ref(false)
const targetHandlerId = ref('')
const handlerOptions = ref([])
const handlerLoading = ref(false)
const handlerError = ref('')
const modalLoading = ref(false)

// 审查弹窗
const reviewModalVisible = ref(false)
const reviewPass = ref(false)
const reviewRemark = ref('')
const adminWithdrawModalVisible = ref(false)
const adminWithdrawReason = ref('')
const adminWithdrawError = ref('')
const adminWithdrawLoading = ref(false)

const isAssignedToMe = computed(() => {
  if (!hazard.value || !hazard.value.handlerId) return false
  return Number(hazard.value.handlerId) === currentUserId.value
})

const isPendingReview = computed(() => {
  if (!hazard.value) return false
  return hazard.value.status === 3 && (hazard.value.reviewed === 0 || !hazard.value.reviewed)
})

// 隐患「撤回」判断：显示条件为 status === 0 && item.userId === 当前登录 userId
const canWithdraw = computed(() => {
  if (!hazard.value || hazard.value.status !== 0) return false
  if (currentUserId.value == null) return false
  return Number(hazard.value.userId) === Number(currentUserId.value)
})

const statusDisplayLabel = computed(() => {
  if (!hazard.value) return '未知'
  if (hazard.value.status === 3) {
    return isPendingReview.value ? '待验收' : '已办结'
  }
  const map = { 0: '待处理', 1: '已接单', 2: '整改中', 4: '已驳回', 5: '已撤回' }
  return map[hazard.value.status] || hazard.value.statusText || '未知'
})

const statusBadgeClass = computed(() => {
  if (!hazard.value) return 'status-0'
  if (hazard.value.status === 3) {
    return isPendingReview.value ? 'status-pending-review' : 'status-3'
  }
  if (hazard.value.status === 5) {
    return 'status-5 status-withdrawn'
  }
  return 'status-' + hazard.value.status
})

const adminActionHint = computed(() => {
  if (!hazard.value) return ''
  if (hazard.value.status === 0) return '当前工单尚未指派责任人，请调度分配处置专员：'
  if (hazard.value.status === 1) return '工单已派发，专员已就位接单。如有需要可改派专员或终止撤回：'
  if (hazard.value.status === 2) return '责任专员正在现场整改作业中：'
  if (isPendingReview.value) return '现场整改已完成申报！请指挥调度官终审复核并把关：'
  if (hazard.value.status === 3 && hazard.value.reviewed == 1) return '该工单已全流程办结并完成质量归档。'
  if (hazard.value.status === 4) return '该工单处于驳回状态，可重新指派专员返工。'
  return ''
})

const handlerActionHint = computed(() => {
  if (!hazard.value) return ''
  if (hazard.value.status === 1) return '您已接单该隐患，准备就绪后请点击“开始整改”：'
  if (hazard.value.status === 2) return '现场作业施工中。整改完成并排险后，请点击“整改完毕，提交终审验收”：'
  if (isPendingReview.value) return '您已提交整改成果，当前正等待指挥中心终审验收 ⏳'
  if (hazard.value.status === 3 && hazard.value.reviewed == 1) return '指挥中心已验收通过，恭喜完成本次治理任务！'
  return ''
})

function formatDate(val) {
  if (!val) return ''
  return String(val).replace('T', ' ').slice(0, 16)
}

function goBack() {
  router.push('/hazard')
}


// 隐患「撤回」操作：POST /api/hazard/{id}/withdraw (带 Bearer token，无 body)
async function handleWithdraw() {
  if (!hazard.value) return
  const token = localStorage.getItem('token')
  if (!token) {
    router.push('/login')
    return
  }

  // 需求建议确认文案：撤回后该上报记录只对管理员可见，确定撤回吗？
  if (!confirm('撤回后该上报记录只对管理员可见，确定撤回吗？')) {
    return
  }

  actionLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${hazard.value.id}/withdraw`, {
      method: 'POST',
      headers: {
        Authorization: 'Bearer ' + token,
      },
    })
    const json = await res.json().catch(() => ({}))
    if (json.code === 200) {
      alert('上报记录已成功撤回！')
      if (userRole.value === '1') {
        if (json.data) {
          hazard.value = json.data
        } else {
          hazard.value.status = 5
          hazard.value.statusText = '已撤回'
        }
      } else {
        // 普通用户撤回后工单仅管理员可见，再次读取该工单会 404，因此平滑返回列表
        router.replace('/hazard')
      }
    } else {
      // 需求3: 错误码语义化分支 (必须读 json.code，HTTP 仍为 200)
      if (json.code === 401) {
        alert('登录凭证已失效，请重新登录')
        localStorage.removeItem('token')
        router.push('/login')
      } else if (json.code === 409) {
        alert(json.message || '该任务已被受理，无法撤回')
        fetchHazardDetail()
      } else if (json.code === 404) {
        alert(json.message || '任务不存在或无权限')
        router.replace('/hazard')
      } else if (json.code === 403) {
        alert(json.message || '无权限执行此撤回操作')
      } else if (json.code === 400) {
        alert(json.message || '请求参数错误')
      } else if (json.code === 429) {
        alert(json.message || '操作过于频繁，请稍后再试')
      } else {
        alert(json.message || '撤回处理未成功，请稍后重试')
      }
    }
  } catch (err) {
    console.error('撤回请求失败', err)
    alert('网络请求异常，请稍后重试')
  } finally {
    actionLoading.value = false
  }
}

async function fetchHazardDetail() {
  const id = route.params.id
  if (!id) {
    errorMessage.value = '缺少工单参数'
    loading.value = false
    return
  }

  const token = localStorage.getItem('token')
  if (!token) {
    router.replace('/login?redirect=' + encodeURIComponent(route.fullPath))
    return
  }

  loading.value = true
  errorMessage.value = ''
  try {
    const res = await fetch(`/api/hazard/${id}`, {
      headers: { Authorization: 'Bearer ' + token },
    })
    const json = await res.json().catch(() => ({}))
    if (res.status === 401 || json.code === 401) {
      localStorage.removeItem('token')
      router.replace('/login?redirect=' + encodeURIComponent(route.fullPath))
      return
    }
    if (json.code === 404) {
      errorMessage.value = json.message || '该工单不存在或已撤回（对普通用户不可见）'
      return
    }
    if (json.code === 403) {
      errorMessage.value = json.message || '无权限查阅该工单'
      return
    }
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || `获取详情失败 (${res.status})`)
    }
    hazard.value = json.data
  } catch (err) {
    console.error('获取隐患详情失败', err)
    errorMessage.value = err.message || '获取隐患详情失败'
  } finally {
    loading.value = false
  }
}

// 基础流转操作 (接单、开始整改、完成申报)
async function executeFlow(action) {
  if (!hazard.value) return
  const token = localStorage.getItem('token')
  if (!token) {
    alert('请先登录')
    router.push('/login')
    return
  }

  actionLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${hazard.value.id}/${action}`, {
      method: 'POST',
      headers: { Authorization: 'Bearer ' + token },
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || `操作失败 (${res.status})`)
    }

    if (action === 'accept') {
      hazard.value.status = 1
      hazard.value.statusText = '已接单'
      hazard.value.handlerId = currentUserId.value || 1
      alert('已成功认领此工单！')
    } else if (action === 'start') {
      hazard.value.status = 2
      hazard.value.statusText = '整改中'
      alert('已进入现场整改施工阶段！')
    } else if (action === 'complete') {
      // 专员标记整改完成 -> 待验收
      hazard.value.status = 3
      hazard.value.reviewed = 0
      hazard.value.statusText = '待验收'
      alert('整改完成报告已提交！工单已进入【待终审验收】状态，等待指挥长复核。')
    }
  } catch (err) {
    console.error(`执行 ${action} 失败`, err)
    alert(err.message || '操作未成功，请稍后重试')
  } finally {
    actionLoading.value = false
  }
}

// 调度员直接终审核准
async function submitDirectReview(pass) {
  if (!hazard.value) return
  const token = localStorage.getItem('token')
  if (!token) return

  const defaultRemark = pass ? '调度指挥中心现场终审通过，核准办结归档。' : '现场整改未达标，驳回重新施工。'
  const remark = prompt(`请确认对工单“${hazardTitle(hazard.value)}”进行【${pass ? '核准办结' : '驳回返工'}】：`, defaultRemark)
  if (remark === null) return

  actionLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${hazard.value.id}/review`, {
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
      throw new Error(json.message || '终审操作失败')
    }

    if (pass) {
      hazard.value.status = 3
      hazard.value.reviewed = 1
      hazard.value.statusText = '已办结'
    } else {
      hazard.value.status = 4
      hazard.value.reviewed = 1
      hazard.value.statusText = '已驳回'
    }
    hazard.value.reviewRemark = remark || defaultRemark
    alert(`工单终审评定已生效：【${pass ? '已办结归档' : '已驳回返工'}】`)
  } catch (err) {
    alert(err.message || '操作失败')
  } finally {
    actionLoading.value = false
  }
}

function hazardTitle(item) {
  const text = (item?.description || item?.address || '隐患工单').trim()
  return text.length > 28 ? text.slice(0, 28) + '…' : text
}

async function fetchHandlers() {
  const token = localStorage.getItem('token')
  if (!token) return
  handlerLoading.value = true
  handlerError.value = ''
  try {
    const res = await fetch('/api/users/handlers', {
      headers: { Authorization: 'Bearer ' + token }
    })
    const json = await res.json().catch(() => ({}))
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

// 派单模态框
async function openAssignModal() {
  targetHandlerId.value = hazard.value.handlerId || ''
  assignModalVisible.value = true
  await fetchHandlers()
}

async function submitAssign() {
  const token = localStorage.getItem('token')
  if (!token || !hazard.value || !targetHandlerId.value) return

  modalLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${hazard.value.id}/assign`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ handlerId: Number(targetHandlerId.value) }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '派单失败')
    }

    hazard.value.handlerId = Number(targetHandlerId.value)
    hazard.value.status = 1
    hazard.value.reviewed = 0
    hazard.value.statusText = '已接单'
    assignModalVisible.value = false
    const selectedName = handlerOptions.value.find((h) => Number(h.id) === Number(targetHandlerId.value))
    alert(`工单“${hazardTitle(hazard.value)}”已成功指派给${selectedName?.nickname || selectedName?.email || '所选责任专员'}`)
  } catch (err) {
    alert(err.message || '指派失败，请选择有效处理人员')
  } finally {
    modalLoading.value = false
  }
}

function openAdminWithdrawModal() {
  adminWithdrawReason.value = ''
  adminWithdrawError.value = ''
  adminWithdrawModalVisible.value = true
}

function closeAdminWithdrawModal() {
  if (adminWithdrawLoading.value) return
  adminWithdrawModalVisible.value = false
  adminWithdrawError.value = ''
}

async function submitAdminWithdraw() {
  const reason = adminWithdrawReason.value.trim()
  if (!reason || !hazard.value) {
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
    const res = await fetch(`/api/hazard/${hazard.value.id}/admin-withdraw`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + token,
      },
      body: JSON.stringify({ reason }),
    })
    const json = await res.json().catch(() => ({}))
    if (!res.ok || json.code !== 200) {
      throw new Error(json.message || '撤回失败')
    }
    hazard.value = json.data
    adminWithdrawModalVisible.value = false
    alert('工单已成功撤回，并进入管理员已撤回列表')
  } catch (err) {
    adminWithdrawError.value = err.message || '撤回失败，请稍后重试'
  } finally {
    adminWithdrawLoading.value = false
  }
}

// 审查驳回模态框
function openReviewModal(pass = false) {
  reviewPass.value = pass
  reviewRemark.value = pass ? '现场复核合格，准予办结。' : ''
  reviewModalVisible.value = true
}

async function submitReview() {
  const token = localStorage.getItem('token')
  if (!token || !hazard.value) return

  modalLoading.value = true
  try {
    const res = await fetch(`/api/hazard/${hazard.value.id}/review`, {
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
      hazard.value.status = 3
      hazard.value.reviewed = 1
      hazard.value.statusText = '已办结'
    } else {
      hazard.value.status = 4
      hazard.value.reviewed = 1
      hazard.value.statusText = '已驳回'
    }
    hazard.value.reviewRemark = reviewRemark.value
    reviewModalVisible.value = false
    alert(reviewPass.value ? '终审核准通过，工单已办结！' : '该工单已驳回返工！')
  } catch (err) {
    alert(err.message || '审查提交失败')
  } finally {
    modalLoading.value = false
  }
}

onMounted(fetchHazardDetail)
</script>

<style scoped>
.hazard-detail-view {
  width: 100%;
  max-width: 100vw;
  min-height: 100vh;
  overflow-x: hidden;
}

.content-wrapper {
  width: 100%;
  max-width: 1280px;
  margin: 0 auto;
  padding: 20px 24px 60px;
}

/* 头部样式 */
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
.header-titles {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.system-tag {
  font-size: 12px;
  color: #64748b;
  font-weight: 500;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
  margin: 0;
}

.task-code-badge {
  padding: 6px 14px;
  border-radius: 9999px;
  background: #eff6ff;
  color: #1a73e8;
  font-size: 13px;
  font-weight: 700;
  border: 1px solid #bfdbfe;
}

/* 警示条 */
.rejection-alert-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 16px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  margin-bottom: 20px;
}
.pending-alert-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 16px;
  background: #fffbeb;
  border: 1px solid #fde68a;
  margin-bottom: 20px;
}
.alert-icon {
  font-size: 28px;
}
.alert-title {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 4px;
  color: #991b1b;
}
.pending-alert-card .alert-title {
  color: #92400e;
}
.alert-desc {
  font-size: 13px;
  color: #b91c1c;
  margin: 0;
  line-height: 1.5;
}
.pending-alert-card .alert-desc {
  color: #b45309;
}

/* 步进条 Stepper */
.lifecycle-stepper-card {
  background: #ffffff;
  border-radius: 18px;
  padding: 20px 24px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.04);
  margin-bottom: 24px;
}
.stepper-title {
  font-size: 13px;
  font-weight: 700;
  color: #475569;
  margin-bottom: 16px;
}
.stepper-track {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.step-node {
  display: flex;
  align-items: center;
  gap: 10px;
}
.node-circle {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #f1f5f9;
  color: #64748b;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  transition: all 0.2s;
}
.step-node.done .node-circle {
  background: #eff6ff;
  color: #1a73e8;
  border: 2px solid #1a73e8;
}
.step-node.active .node-circle {
  background: #1a73e8;
  color: #ffffff;
  box-shadow: 0 0 0 4px rgba(26, 115, 232, 0.2);
}
.step-node.step-warning.active .node-circle {
  background: #d97706;
  color: #ffffff;
  box-shadow: 0 0 0 4px rgba(217, 119, 6, 0.2);
}
.step-node.step-rejected .node-circle {
  background: #dc2626;
  color: #ffffff;
}

.node-text .main-txt {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}
.node-text .sub-txt {
  font-size: 11px;
  color: #94a3b8;
}
.step-link-line {
  flex: 1;
  height: 2px;
  background: #e2e8f0;
  margin: 0 12px;
}
.step-link-line.active {
  background: #1a73e8;
}

/* 网格布局 */
.detail-grid {
  display: grid;
  grid-template-columns: 1.1fr 1fr;
  gap: 24px;
}
.left-col, .right-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-card {
  background: #ffffff;
  border-radius: 18px;
  padding: 20px 24px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  box-shadow: 0 4px 16px -2px rgba(0, 0, 0, 0.04);
}
.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.image-stage {
  width: 100%;
  height: 280px;
  border-radius: 14px;
  overflow: hidden;
  background: #f8fafc;
  display: flex;
  align-items: center;
  justify-content: center;
}
.stage-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.no-img-text {
  color: #94a3b8;
  font-size: 13px;
}

.geo-info-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.geo-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
}
.geo-label {
  color: #64748b;
  font-weight: 500;
  min-width: 72px;
}
.geo-val {
  color: #1e293b;
  font-weight: 600;
}
.map-link-btn {
  display: inline-block;
  margin-top: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #1a73e8;
  text-decoration: none;
}
.map-link-btn:hover {
  text-decoration: underline;
}

/* 工单属性 */
.tags-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 700;
}
.status-pill .dot {
  width: 6px;
  height: 6px;
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
  font-size: 12px;
  font-weight: 700;
  padding: 3px 10px;
  border-radius: 6px;
  background: #f8fafc;
  color: #334155;
  border: 1px solid #e2e8f0;
}

.desc-box {
  background: #f8fafc;
  padding: 14px;
  border-radius: 12px;
  margin-bottom: 16px;
}
.desc-label {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}
.desc-content {
  font-size: 13px;
  color: #1e293b;
  margin: 6px 0 0;
  line-height: 1.6;
}

.person-track-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.track-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
}
.track-label {
  color: #64748b;
}
.track-val {
  font-weight: 600;
  color: #1e293b;
}
.highlight-val {
  color: #1a73e8;
}
.highlight-remark {
  color: #dc2626;
}

/* 操作控制台 */
.flow-actions-wrapper {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.flow-tip-text {
  font-size: 13px;
  color: #475569;
  line-height: 1.5;
}
.actions-grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.flow-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 20px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}
.flow-btn:hover {
  transform: translateY(-1px);
}
.btn-accept {
  background: #1a73e8;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(26, 115, 232, 0.25);
}
.btn-reject-outline {
  background: #ffffff;
  border: 1px solid #cbd5e1;
  color: #475569;
}
.btn-start {
  background: #ea580c;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(234, 88, 12, 0.25);
}
.btn-complete {
  background: #16a34a;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(22, 163, 74, 0.25);
}

.sub-actions-row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.flow-btn-sm {
  flex: 1;
  padding: 8px 14px;
  border-radius: 9999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  color: #334155;
  transition: all 0.15s;
}
.btn-sub-assign:hover {
  background: #eff6ff;
  border-color: #1a73e8;
  color: #1a73e8;
}
.btn-sub-reject:hover {
  background: #fef2f2;
  border-color: #dc2626;
  color: #dc2626;
}

.inprogress-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #fff7ed;
  color: #c2410c;
  font-size: 12px;
  font-weight: 600;
}
.badge-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ea580c;
}

/* 待验收控制台 */
.pending-review-action-box {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 14px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.box-title {
  font-size: 13px;
  font-weight: 700;
  color: #92400e;
  margin: 0;
}
.button-dual-row {
  display: flex;
  gap: 10px;
}
.btn-complete-pass {
  flex: 1.2;
  background: #16a34a;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(22, 163, 74, 0.25);
}
.btn-reject-urgent {
  flex: 1;
  background: #dc2626;
  color: #ffffff;
  box-shadow: 0 4px 12px rgba(220, 38, 38, 0.25);
}

.pending-wait-box {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  border-radius: 14px;
  background: #fffbeb;
  border: 1px solid #fde68a;
}
.wait-icon-large {
  font-size: 28px;
}
.wait-text h4 {
  font-size: 14px;
  font-weight: 700;
  color: #92400e;
  margin: 0 0 4px;
}
.wait-text p {
  font-size: 12px;
  color: #b45309;
  margin: 0;
  line-height: 1.5;
}

.finished-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px;
  border-radius: 12px;
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  color: #15803d;
  font-size: 13px;
  font-weight: 600;
}
.rejected-box {
  padding: 14px;
  border-radius: 12px;
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  font-size: 13px;
}

.other-handler-box, .citizen-view-hint {
  padding: 14px;
  border-radius: 12px;
  background: #f8fafc;
  color: #64748b;
  font-size: 13px;
  line-height: 1.5;
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
  max-width: 440px;
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
}
.highlight-id {
  color: #1a73e8;
  font-weight: 700;
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

.mobile-text {
  display: none;
}
.desktop-text {
  display: inline;
}

/* ========================================================
   移动端响应式优化 (iPhone / Android 设备深度适配)
   解决工单双栏挤压为竖排字、步进条溢出、底部遮挡等问题
   ======================================================== */
@media (max-width: 768px) {
  .desktop-text {
    display: none !important;
  }
  .mobile-text {
    display: inline !important;
  }

  .content-wrapper {
    padding: 12px 14px calc(80px + env(safe-area-inset-bottom, 0px));
  }

  /* 顶部返回与标题 */
  .page-header {
    flex-wrap: wrap;
    gap: 8px;
    margin-bottom: 14px;
  }
  .header-left {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .back-btn {
    padding: 6px 12px;
    font-size: 12px;
    flex-shrink: 0;
  }
  .header-titles {
    flex: 1;
    min-width: 0;
  }
  .system-tag {
    font-size: 11px;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .page-title {
    font-size: 15px;
    line-height: 1.35;
    letter-spacing: -0.01em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .header-right {
    margin-left: auto;
  }
  .task-code-badge {
    font-size: 11px;
    padding: 3px 9px;
  }

  /* 警示条微胶囊 */
  .rejection-alert-card,
  .pending-alert-card {
    padding: 12px 14px;
    border-radius: 12px;
    gap: 10px;
    margin-bottom: 14px;
  }
  .alert-icon {
    font-size: 20px;
  }
  .alert-title {
    font-size: 12.5px;
    margin-bottom: 2px;
  }
  .alert-desc {
    font-size: 11.5px;
    line-height: 1.45;
  }

  /* 步进条卡片：横向可平滑滚动，节点不挤压 */
  .lifecycle-stepper-card {
    padding: 12px 14px;
    border-radius: 14px;
    margin-bottom: 14px;
  }
  .stepper-title {
    font-size: 12px;
    margin-bottom: 10px;
  }
  .stepper-track {
    display: flex;
    align-items: center;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 4px;
    scrollbar-width: none;
  }
  .stepper-track::-webkit-scrollbar {
    display: none;
  }
  .step-node {
    flex-shrink: 0;
    gap: 6px;
  }
  .node-circle {
    width: 24px;
    height: 24px;
    font-size: 11px;
    flex-shrink: 0;
  }
  .node-text {
    flex-shrink: 0;
  }
  .node-text .main-txt {
    font-size: 11.5px;
    white-space: nowrap;
  }
  .node-text .sub-txt {
    font-size: 10px;
    white-space: nowrap;
  }
  .step-link-line {
    flex-shrink: 0;
    width: 20px;
    min-width: 16px;
    margin: 0 4px;
  }

  /* 核心看板网格由双栏彻底切为全宽单栏，按业务优先级智能重排，告别单字竖排 */
  .detail-grid {
    display: flex !important;
    flex-direction: column !important;
    gap: 14px !important;
  }
  .left-col,
  .right-col {
    display: contents !important;
  }
  .image-section-card {
    order: 1 !important;
  }
  .prop-section-card {
    order: 2 !important;
  }
  .action-console-card {
    order: 3 !important;
  }
  .geo-section-card {
    order: 4 !important;
  }

  .section-card {
    padding: 14px 16px;
    border-radius: 14px;
    width: 100%;
    box-sizing: border-box;
  }
  .card-head {
    font-size: 13px;
    margin-bottom: 12px;
    padding-bottom: 8px;
  }

  /* 现场照片适应移动端视野 */
  .image-stage {
    height: 200px;
    border-radius: 10px;
  }
  .image-stage.no-image-stage {
    height: 64px;
    background: #f8fafc;
  }
  .no-img-text {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: #94a3b8;
  }

  /* 属性与问题描述 */
  .tags-bar {
    gap: 8px;
    margin-bottom: 12px;
  }
  .status-pill,
  .category-pill {
    font-size: 11.5px;
    padding: 2px 8px;
  }
  .desc-box {
    padding: 10px 12px;
    margin-bottom: 12px;
  }
  .desc-label {
    font-size: 11.5px;
  }
  .desc-content {
    font-size: 12.5px;
    line-height: 1.55;
    margin-top: 4px;
  }

  /* 人员流转追踪项 */
  .person-track-box {
    gap: 6px;
  }
  .track-row {
    font-size: 11.5px;
  }

  /* 地理位置 */
  .geo-info-box {
    gap: 8px;
  }
  .geo-row {
    font-size: 12px;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
  }
  .geo-label {
    min-width: unset;
    font-size: 11px;
  }
  .map-link-btn {
    font-size: 12px;
    margin-top: 6px;
  }

  /* 协同控制台按钮自适应铺满触控 */
  .flow-tip-text {
    font-size: 12px;
  }
  .flow-btn {
    width: 100%;
    padding: 10px 16px;
    font-size: 12.5px;
    box-sizing: border-box;
  }
  .sub-actions-row {
    flex-direction: column;
    gap: 8px;
  }
  .flow-btn-sm {
    width: 100%;
    padding: 9px 12px;
    font-size: 12px;
    box-sizing: border-box;
  }
  .button-dual-row {
    flex-direction: column;
    gap: 8px;
  }
  .pending-wait-box {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    padding: 12px;
  }

  /* 模态框居中与宽度适配 */
  .modal-box {
    width: calc(100% - 32px);
    max-width: 380px;
    padding: 18px 16px;
    border-radius: 16px;
  }
  .modal-title {
    font-size: 15px;
  }
  .modal-hint {
    font-size: 12px;
    margin-bottom: 12px;
  }
  .form-label {
    font-size: 11.5px;
  }
  .form-input,
  .form-textarea {
    font-size: 13px;
    padding: 7px 10px;
  }
  .modal-footer {
    gap: 8px;
    margin-top: 16px;
  }
  .modal-btn {
    padding: 7px 14px;
    font-size: 12px;
  }
}

/* 撤回特别警示条与相关样式 */
.withdrawn-alert-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border-radius: 16px;
  background: #f8fafc;
  border: 1px solid #cbd5e1;
  margin-bottom: 20px;
}
.withdrawn-alert-card .alert-icon {
  font-size: 28px;
}
.withdrawn-alert-card .alert-title {
  font-size: 14px;
  font-weight: 700;
  margin: 0 0 4px;
  color: #475569;
}
.withdrawn-alert-card .alert-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0;
  line-height: 1.5;
}

.status-5, .status-withdrawn { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }
.status-5 .dot, .status-withdrawn .dot { background: #94a3b8; }
.step-node.step-withdrawn .node-circle {
  background: #f1f5f9 !important;
  color: #64748b !important;
  border-color: #cbd5e1 !important;
}

.header-withdraw-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 9999px;
  background: #fff1f2;
  border: 1px solid #fecdd3;
  color: #e11d48;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.header-withdraw-btn:hover {
  background: #ffe4e6;
  color: #be123c;
}
.header-withdraw-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.withdraw-console-card {
  padding: 16px;
  border-radius: 12px;
  background: #fff1f2;
  border: 1px solid #fecdd3;
  margin-bottom: 16px;
}
.withdraw-tip {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 12px;
}
.withdraw-tip .tip-badge {
  font-size: 11px;
  font-weight: 700;
  background: #ffe4e6;
  color: #be123c;
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.withdraw-tip .tip-text {
  font-size: 12px;
  color: #9f1239;
  line-height: 1.5;
}
.btn-withdraw {
  background: #fff1f2;
  color: #e11d48;
  border: 1px solid #fecdd3;
  box-shadow: 0 4px 12px rgba(225, 29, 72, 0.15);
}
.btn-withdraw:hover {
  background: #ffe4e6;
  color: #be123c;
}
.btn-withdraw:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.withdrawn-status-box {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 16px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 13px;
  font-weight: 600;
}


.withdrawn-reason-text {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  color: #475569;
  font-size: 12px;
}

.btn-admin-withdraw {
  background: #fff7ed !important;
  color: #c2410c !important;
  border: 1px solid #fed7aa !important;
}
.btn-admin-withdraw:hover {
  background: #ffedd5 !important;
  color: #9a3412 !important;
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

.handler-select {
  cursor: pointer;
}
.handler-select-hint {
  margin: 7px 0 0;
  color: #64748b;
  font-size: 11px;
}
.handler-select-hint.error {
  color: #dc2626;
}
</style>


