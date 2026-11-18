<template>
  <section
    class="interactive-showcase-section"
    aria-label="城市安全智能研判实战操作示范"
    :style="{
      '--active-theme': activeRole.themeColor,
      '--active-rgb': activeRole.themeRgb,
      '--active-bg-soft': activeRole.themeColorLight
    }"
  >
    <!-- 顶部业务角色切换 Tab 栏 (Open Study 同款精致微胶囊，带浅透底色与主题色边框) -->
    <nav class="roles-tab-bar" aria-label="研判角色选择">
      <button
        v-for="role in roles"
        :key="role.id"
        class="role-tab-btn"
        :class="{ active: currentRoleId === role.id }"
        @click="selectRole(role.id)"
        type="button"
        :aria-pressed="currentRoleId === role.id"
      >
        <component :is="role.icon" class="role-icon" />
        <span class="role-name">{{ role.name }}</span>
      </button>
    </nav>

    <!-- 主展示区：左侧场景联动步骤 + 右侧实战操作示范窗口 -->
    <div class="showcase-main-grid">
      <!-- 左侧：大标题与场景工作流步骤卡片 -->
      <div class="showcase-left-col">
        <header class="showcase-header-block">
          <h2 class="showcase-main-title">
            看看 <span class="highlight-role-text">{{ activeRole.name }}</span> 能做什么<br />
            用安全智能研判平台
          </h2>
          <p class="showcase-subtitle">{{ activeRole.subtitle }}</p>
        </header>

        <!-- 3 组可切换的场景步骤卡片 (带多层柔光外阴影与水平射入工作台的连接线) -->
        <div class="steps-card-list" ref="stepsContainerRef">
          <div
            v-for="(step, sIdx) in activeRole.steps"
            :key="sIdx"
            class="step-item-card"
            :class="{ active: activeStepIndex === sIdx }"
            @click="selectStep(sIdx)"
          >
            <div class="step-card-inner">
              <span class="step-num-code num-font">0{{ sIdx + 1 }}</span>
              <h3 class="step-card-title">{{ step.title }}</h3>
            </div>

            <!-- 与右侧工作台相连的动态连接光线 (Open Study 同款水平射入实线桥) -->
            <div v-if="activeStepIndex === sIdx" class="connector-beam-line" aria-hidden="true">
              <span class="connector-beam-glow"></span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：高保真模拟工作台视窗 (Live Mockup Workspace) -->
      <div class="showcase-right-col">
        <div class="mockup-workspace-card">
          <!-- 视窗顶部标题栏与 2x12 点阵 (Dot Matrix 脉冲跳动) -->
          <div class="workspace-top-bar">
            <div class="workspace-title-box">
              <span class="dot-indicator"></span>
              <span class="workspace-title-text">{{ activeRole.name }}智能研判工作台</span>
              <span class="workspace-live-badge">LIVE SESSION</span>
            </div>

            <!-- Open Study 同款 2 行 x 12 列 (24 点) 矩阵脉冲点阵 -->
            <div
              class="matrix-dots-pattern"
              :class="{ 'is-running': isTyping || !verdictRevealed }"
              aria-hidden="true"
              title="智能研判模型实时处理状态"
            >
              <div v-for="(row, rIdx) in dotMatrix" :key="rIdx" class="matrix-dots-row">
                <span
                  v-for="(alpha, cIdx) in row"
                  :key="cIdx"
                  class="matrix-dot"
                  :style="{
                    '--dot-alpha': alpha,
                    '--dot-delay': `${-((rIdx * 12 + cIdx) * 0.08).toFixed(2)}s`
                  }"
                ></span>
              </div>
            </div>
          </div>

          <!-- 视窗内容区：打字机流式切片输出、多模态执行链与研判裁决展开 -->
          <div class="workspace-body-content">
            <!-- 1. 模拟触发指令行 (真实打字机流式逐字吐出 + 阶跃闪烁黑色方块光标) -->
            <div class="agent-command-row">
              <span class="prompt-symbol num-font">></span>
              <div class="prompt-text-wrap">
                <span class="command-text">{{ typedCommand }}</span>
                <span
                  class="prompt-cli-cursor"
                  :class="{ 'is-blinking': typingCompleted }"
                  aria-hidden="true"
                ></span>
              </div>
            </div>

            <!-- 2. 模拟多模态智能体执行链与规范比对树 (随打字完成逐级展开) -->
            <div class="agent-execution-tree" :class="{ visible: revealedNodesCount > 0 }">
              <div
                v-for="(node, nIdx) in currentStepData.nodes"
                :key="nIdx"
                class="tree-node-item"
                :class="{ revealed: nIdx < revealedNodesCount }"
              >
                <span class="tree-corner">└</span>
                <div class="node-tag-pill" :class="node.status">
                  <span class="node-icon" aria-hidden="true">
                    <svg v-if="node.status === 'success'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
                    <svg v-else-if="node.status === 'info'" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
                    <svg v-else width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 8 16 12 12 16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                  </span>
                  <span class="node-label">{{ node.label }}</span>
                  <span v-if="node.detail" class="node-detail">{{ node.detail }}</span>
                  <span class="status-sweep-line" aria-hidden="true"></span>
                </div>
              </div>
            </div>

            <!-- 3. 模拟研判裁决输出面板 (平滑渐现与柔和加粗边框) -->
            <transition name="verdict-reveal">
              <div v-if="verdictRevealed" class="verdict-output-panel">
                <div class="verdict-badge-row">
                  <span class="verdict-status-tag">
                    {{ currentStepData.verdict.tag }}
                  </span>
                  <span class="verdict-norm-code num-font">{{ currentStepData.verdict.norm }}</span>
                </div>
                <p class="verdict-summary-text">{{ currentStepData.verdict.summary }}</p>
                <div class="verdict-action-row">
                  <span class="action-label">闭环处置要求：</span>
                  <span class="action-value">{{ currentStepData.verdict.action }}</span>
                </div>
              </div>
            </transition>
          </div>

          <!-- 视窗底部模拟交互输入框 (极度干净克制) -->
          <footer class="workspace-footer-bar">
            <div class="mock-input-box">
              <span class="mock-placeholder">向安全研判智能体提问，或追问闭环规程……</span>
              <span class="mock-send-hint num-font">↵</span>
            </div>
          </footer>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { h, ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

// 业务角色线性图标定义 (遵循现代专业硬朗风格)
const MunicipalIcon = () => h('svg', {
  width: '15', height: '15', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'
}, [
  h('polygon', { points: '1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6' }),
  h('line', { x1: '8', y1: '2', x2: '8', y2: '18' }),
  h('line', { x1: '16', y1: '6', x2: '16', y2: '22' })
])

const ConstructionIcon = () => h('svg', {
  width: '15', height: '15', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'
}, [
  h('path', { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z' }),
  h('polyline', { points: '14 2 14 8 20 8' }),
  h('line', { x1: '9', y1: '15', x2: '15', y2: '15' })
])

const FireIcon = () => h('svg', {
  width: '15', height: '15', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'
}, [
  h('path', { d: 'M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z' })
])

const CommandIcon = () => h('svg', {
  width: '15', height: '15', viewBox: '0 0 24 24', fill: 'none',
  stroke: 'currentColor', 'stroke-width': '2.2', 'stroke-linecap': 'round', 'stroke-linejoin': 'round'
}, [
  h('path', { d: 'M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6' })
])

// Open Study 同款 2 行 x 12 列点阵权重
const dotMatrix = [
  [0.1, 0.16, 0.58, 0.72, 0.44, 0.08, 0.12, 0.36, 0.66, 0.62, 0.26, 0.09],
  [0.34, 0.6, 0.14, 0.5, 0.2, 0.7, 0.3, 0.55, 0.11, 0.42, 0.68, 0.18]
]

// 业务角色与步骤数据矩阵
const roles = [
  {
    id: 'municipal',
    name: '市政网格巡查',
    themeColor: '#2563eb',
    themeRgb: '37, 99, 235',
    themeColorLight: '#eff6ff',
    icon: MunicipalIcon,
    subtitle: '现场拍照一键直传，秒级诊断井盖破损、盲道占用与路面塌陷，自动对标市政建设规范。',
    steps: [
      {
        title: '市政井盖破损与沉降秒级定级',
        command: '研判现场抓拍：三明市列东街雨水检查井盖断裂沉陷，评估对夜间非机动车安全威胁。',
        nodes: [
          { status: 'success', label: '视觉多模态定位完成', detail: '识别出铸铁井盖贯穿性开裂' },
          { status: 'info', icon: '📖', label: '检索国家建设规范', detail: 'GB/T 23858-2009《检查井盖》D400 级' },
          { status: 'active', label: '智能风险研判模型推演中', detail: '高风险隐患 · 存在行人坠井险情' },
          { status: 'done', label: '生成闭环工单', detail: '已派发市政管网抢修中心' }
        ],
        verdict: {
          tag: '中高风险隐患',
          norm: 'GB/T 23858-2009 强制条文 5.2',
          summary: '井盖承载面受损超过 1/3，边缘下沉达 4.2cm，夜间视线不良极易造成车辆倾覆或人员跌落。',
          action: '1 小时内设立反光隔离警示锥，4 小时内完成规格井盖原样更换并实地拍照复核销号。'
        }
      },
      {
        title: '人行道地砖塌陷与无障碍盲道阻断',
        command: '现场隐患核查：第一中学周边人行道路面空洞沉降，盲道遭共享单车堆放阻断 12 米。',
        nodes: [
          { status: 'success', label: '空间坐标解析', detail: '三明市第一中学正门往东 50 米' },
          { status: 'info', icon: '🏛️', label: '索引法律规范', detail: '《无障碍环境建设法》第二十八条' },
          { status: 'done', label: '协同交办完毕', detail: '派单至城管执法二中队' }
        ],
        verdict: {
          tag: '中风险 · 违规占用',
          norm: 'CJJ 1-2008《城镇道路工程施工与质量验收规范》',
          summary: '盲道连续性中断影响视障人士出行安全，下陷处存在雨水渗漏掏空路基风险。',
          action: '责令共享单车运营方 30 分钟内清运归位，市政道桥班组于次日完成沉降基层注浆压实。'
        }
      },
      {
        title: '城市供排水管网跑冒滴漏排查',
        command: '快速研判：沿街雨水箅子被泥沙落叶严重堵塞，遇暴雨路面汇水深度超 15cm。',
        nodes: [
          { status: 'success', label: '水浸险情推演', detail: '识别低洼路段积水倒灌隐患' },
          { status: 'done', label: '联动防汛网格', detail: '指派三元区防汛抢险第三机动组' }
        ],
        verdict: {
          tag: '季节性防汛隐患',
          norm: 'GB 50014-2021《室外排水设计标准》',
          summary: '排水通量受阻超过 70%，易诱发城市局部内涝与沿街商铺进水次生灾害。',
          action: '立即动用高压疏通车实施清淤，确保雨水口过水截面通畅。'
        }
      }
    ]
  },
  {
    id: 'construction',
    name: '施工安全监管',
    themeColor: '#059669',
    themeRgb: '5, 150, 105',
    themeColorLight: '#ecfdf5',
    icon: ConstructionIcon,
    subtitle: '实时比对深基坑防护、脚手架搭设、临边违规及个人防护用品佩戴合规性。',
    steps: [
      {
        title: '高空作业未系安全带与安全帽穿戴',
        command: '现场巡查研判：在建项目 3 号栋外立面作业人员未按规范系挂安全绳，脚手架未设密目网。',
        nodes: [
          { status: 'success', label: '人体骨骼姿态识别', detail: '标定 2 名作业人员处于临边未系绳状态' },
          { status: 'info', icon: '🏗️', label: '对标建设规范', detail: 'JGJ 80-2016《建筑施工高处作业安全技术规范》' },
          { status: 'done', label: '红牌即刻停工单', detail: '已通报项目施工负责人与驻场总监' }
        ],
        verdict: {
          tag: '重大安全隐患 · 立即停工',
          norm: 'JGJ 80-2016 强制性条文 3.0.5',
          summary: '临边高度超过 2 米未设置合格防护栏杆且作业人员无高挂低用防坠措施，极易发生坠落。',
          action: '责令立即撤离临边作业面，组织全员安全交底，重新加挂安全网与生命绳后复工。'
        }
      },
      {
        title: '深基坑临边防护与位移监测预警',
        command: '深基坑巡检：开挖深度 5.4 米基坑周边堆载超标，未设 1.2 米定型化临边防护网。',
        nodes: [
          { status: 'success', label: '土方坡比感知', detail: '坑边 1 米内堆放大型钢筋笼' },
          { status: 'info', icon: '📐', label: '规范比对', detail: 'JGJ 120-2012《建筑基坑支护技术规程》' },
          { status: 'done', label: '生成整改督办单', detail: '限期 2 小时卸载搬离' }
        ],
        verdict: {
          tag: '结构安全中高风险',
          norm: 'JGJ 120-2012 强制性条文',
          summary: '基坑顶缘超负荷堆载会急剧增加主动土压力，存在局部滑坡失稳坍塌风险。',
          action: '严禁基坑周边超额堆重，沿坑周安装刚性防护栏杆并布设红白反光警示带。'
        }
      },
      {
        title: '施工现场临时用电私拉乱接研判',
        command: '用电安全研判：二级配电箱柜门敞开且未接地线，电缆直接穿行泥水洼地。',
        nodes: [
          { status: 'success', label: '电气风险定位', detail: '绝缘层老化破损露铜' },
          { status: 'info', icon: '⚡', label: '用电规范比对', detail: 'JGJ 46-2005《施工现场临时用电安全技术规范》' },
          { status: 'done', label: '电工消缺工单', detail: '派发持证电工班组' }
        ],
        verdict: {
          tag: '触电/火灾中风险',
          norm: 'JGJ 46-2005 三级配电两级保护原则',
          summary: '雨水浸泡电缆易引发接地短路与触电事故，违背现场“一机一闸一漏一箱”安全准则。',
          action: '实施电缆高架空铺设，配电箱上锁并增设防雨遮罩，测试漏电保护器动作电流。'
        }
      }
    ]
  },
  {
    id: 'fire',
    name: '消防监督执法',
    themeColor: '#ea580c',
    themeRgb: '234, 88, 12',
    themeColorLight: '#fff7ed',
    icon: FireIcon,
    subtitle: '智能排查商住综合体、人员密集场所疏散通道堆物堵塞与消防灭火设施故障。',
    steps: [
      {
        title: '安全出口与疏散走道杂物堆占排查',
        command: '现场核查：商住楼 2 楼东侧常闭防火门被木楔卡阻常开，疏散楼梯堆放纸板杂物。',
        nodes: [
          { status: 'success', label: '通道宽度计算', detail: '有效通行净宽由 1.4 米缩减至 0.5 米' },
          { status: 'info', icon: '🚒', label: '法律条文索引', detail: '《中华人民共和国消防法》第二十八条' },
          { status: 'done', label: '下发限期整改通知', detail: '已推送至物业工程消防负责人' }
        ],
        verdict: {
          tag: '消防安全高风险',
          norm: 'GB 50016-2014《建筑设计防火规范》',
          summary: '火灾发生时有毒烟气将迅速沿楼梯间向上蔓延，杂物阻断逃生人员快速疏散通道。',
          action: '即刻清理楼道堆积杂物，拆除卡塞木楔，确保防火门闭门器及顺位器完好复位。'
        }
      },
      {
        title: '室内消火栓箱体被遮挡与器材缺失',
        command: '设施核验：沿街超市室内消火栓被货架完全遮蔽，箱门开启角度受限不足 30 度。',
        nodes: [
          { status: 'success', label: '消火栓标识识别', detail: '箱门被大型促销广告牌遮挡' },
          { status: 'info', icon: '🧯', label: '消火栓规程', detail: 'GB 50974-2014《消防给水及消火栓系统技术规范》' },
          { status: 'done', label: '现场督办整改', detail: '超市安全责任人当场签认' }
        ],
        verdict: {
          tag: '消防设施违规遮挡',
          norm: 'GB 50974-2014 规范 7.4.12',
          summary: '紧急火情下扑救人员无法迅速展开水带水枪，将严重延误初期火灾黄金控制时间。',
          action: '移开遮挡货架，保持箱体前方 1 米范围内无任何障碍，确保箱门开启角度不小于 120°。'
        }
      },
      {
        title: '电动自行车违规进楼入户充电排查',
        command: '架空层排查：居民楼架空层违规停放电动自行车 14 辆，其中 3 辆私拉飞线充电。',
        nodes: [
          { status: 'success', label: '热失控风险预警', detail: '检测到非国标改装电池组接线' },
          { status: 'done', label: '社区网格联合交办', detail: '通知社区民警与网格员联合劝导' }
        ],
        verdict: {
          tag: '重大群死群伤隐患',
          norm: '应急管理部《高层民用建筑消防安全管理规定》',
          summary: '锂电池热失控燃烧蔓延极快并产生剧毒氟化氢气体，严禁在建筑内违规停放充电。',
          action: '切断飞线电源，引导车主移步户外智能集中充电棚，张贴消防安全禁令通告。'
        }
      }
    ]
  },
  {
    id: 'command',
    name: '综合指挥决策',
    themeColor: '#7c3aed',
    themeRgb: '124, 58, 237',
    themeColorLight: '#f5f3ff',
    icon: CommandIcon,
    subtitle: '贯通全域隐患时空分布，识别高频高危薄弱环节，输出多维研判分析与督办考核。',
    steps: [
      {
        title: '全域安全隐患时空热力态势穿透',
        command: '决策中心指令：穿透三元区近 30 天工单数据，分析暴雨周期城市内涝与道路隐患聚类。',
        nodes: [
          { status: 'success', label: '全域时空聚类分析', detail: '三元区共汇聚工单 318 件，市政类占比 46%' },
          { status: 'info', icon: '📊', label: '态势关联挖掘', detail: '富兴堡街道积水隐患高发关联管网老化' },
          { status: 'done', label: '输出指挥调度令', detail: '精准调配防汛抽排力量' }
        ],
        verdict: {
          tag: '态势决策报告已生成',
          norm: '三明市城市运行安全风险监测预警体系工作指引',
          summary: '富兴堡及白沙街道存在 3 处系统性短板，建议纳入下季度城市地下管网韧性改造专项。',
          action: '向市住建局发送专题督办函，启动防汛抢险第三梯队开展拉网式清掏巡检。'
        }
      },
      {
        title: '重大高危隐患闭环超时红黄牌督办',
        command: '督查指令：检索全市超过 48 小时未落实整改的二级以上高危安全隐患。',
        nodes: [
          { status: 'success', label: '超时触发检测', detail: '筛查出 2 件临边深基坑防护未闭环工单' },
          { status: 'done', label: '红牌督办直达分管局长', detail: '触发系统紧急协同流' }
        ],
        verdict: {
          tag: '红牌重点督办',
          norm: '安全生产责任追究与隐患挂牌督办机制',
          summary: '连续两次现场复核未达标，施工责任主体整改进度严重滞后，已启动约谈机制。',
          action: '暂停该项目夜间作业许可，安全生产监督执法支队将于明日开展全专业执法检查。'
        }
      },
      {
        title: '行业治理成效综合评估与数字报告',
        command: '生成报告：一键汇总本季度城市安全隐患闭环率、平均办结时长与部门考核评分。',
        nodes: [
          { status: 'success', label: '治理成效指标聚合', detail: '平均办结时长缩减 38%，综合闭环率 98.4%' },
          { status: 'done', label: '报告归档完成', detail: '生成 PDF/Word 格式安全年报' }
        ],
        verdict: {
          tag: '数字化治理效能提升',
          norm: '数字化改革与韧性城市评价标准',
          summary: '多模态 AI 智能研判助力基层隐患排查准确率提升 65%，有效防范化解重大风险。',
          action: '报告归档至市委市政府综合安全档案库，作为年度安全生产考核加分依据。'
        }
      }
    ]
  }
]

const currentRoleId = ref('municipal')
const activeStepIndex = ref(0)

const activeRole = computed(() => {
  return roles.find(r => r.id === currentRoleId.value) || roles[0]
})

const currentStepData = computed(() => {
  const steps = activeRole.value.steps
  return steps[activeStepIndex.value] || steps[0]
})

// ========================================================
// Open Study 同款高保真打字机与流式时间线状态机 (Typewriter & Timeline)
// ========================================================
const typedCommand = ref('')
const isTyping = ref(false)
const typingCompleted = ref(false)
const revealedNodesCount = ref(0)
const verdictRevealed = ref(false)

let typingTimer = null
let animationTimeouts = []

function clearAllTimelines() {
  if (typingTimer) {
    clearInterval(typingTimer)
    typingTimer = null
  }
  animationTimeouts.forEach(t => clearTimeout(t))
  animationTimeouts = []
}

function startWorkflowAnimation() {
  clearAllTimelines()

  const fullText = currentStepData.value.command || ''
  const nodes = currentStepData.value.nodes || []

  typedCommand.value = ''
  isTyping.value = true
  typingCompleted.value = false
  revealedNodesCount.value = 0
  verdictRevealed.value = false

  // 1. 打字机前置微延迟 120ms
  const startDelay = setTimeout(() => {
    let charIndex = 0
    const charSpeed = 22 // 约 45 字符/秒，极富现代终端流畅感

    typingTimer = setInterval(() => {
      if (charIndex < fullText.length) {
        charIndex += 1
        typedCommand.value = fullText.slice(0, charIndex)
      } else {
        clearInterval(typingTimer)
        typingTimer = null
        isTyping.value = false
        typingCompleted.value = true

        // 2. 打字完毕后，依次平滑阶跃展开节点 (每个节点间隔 90ms)
        nodes.forEach((_, idx) => {
          const nodeDelay = setTimeout(() => {
            revealedNodesCount.value = idx + 1
          }, (idx + 1) * 90)
          animationTimeouts.push(nodeDelay)
        })

        // 3. 所有节点展开后，展开裁决面板
        const verdictDelay = setTimeout(() => {
          verdictRevealed.value = true
        }, (nodes.length + 1) * 90 + 60)
        animationTimeouts.push(verdictDelay)
      }
    }, charSpeed)
  }, 120)

  animationTimeouts.push(startDelay)
}

function selectRole(roleId) {
  if (currentRoleId.value === roleId) return
  currentRoleId.value = roleId
  activeStepIndex.value = 0
  startWorkflowAnimation()
}

function selectStep(sIdx) {
  if (activeStepIndex.value === sIdx) return
  activeStepIndex.value = sIdx
  startWorkflowAnimation()
}

onMounted(() => {
  startWorkflowAnimation()
})

onBeforeUnmount(() => {
  clearAllTimelines()
})
</script>

<style scoped>
/* ========================================================
   整个展示板块：现代科技极简风 (无杂乱几何干扰，聚焦内容自身)
   ======================================================== */
.interactive-showcase-section {
  width: 100%;
  max-width: 1200px;
  margin: 36px auto 60px;
  padding: 0 16px;
  position: relative;
}

/* ========================================================
   顶部业务角色切换 Tab 栏：Open Study 经典全圆角胶囊
   ======================================================== */
.roles-tab-bar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 38px;
}

.role-tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 42px;
  padding: 0 18px;
  border-radius: 999px;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.95);
  color: #475569;
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1);
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.03);
  position: relative;
  overflow: hidden;
  user-select: none;
}

.role-tab-btn:hover {
  color: #0f172a;
  border-color: rgba(203, 213, 225, 1);
  transform: translateY(-1px);
}

.role-tab-btn.active {
  background: var(--active-bg-soft);
  color: var(--active-theme);
  border-color: var(--active-theme);
  font-weight: 600;
  box-shadow: 0 4px 16px -2px rgba(var(--active-rgb), 0.16);
}

.role-icon {
  flex-shrink: 0;
  transition: transform 0.2s ease;
}

.role-tab-btn.active .role-icon {
  transform: scale(1.1);
  color: var(--active-theme);
}

/* ========================================================
   主展示网格：左侧说明卡片 + 右侧工作台视窗
   ======================================================== */
.showcase-main-grid {
  display: grid;
  grid-template-columns: 430px 1fr;
  gap: 40px;
  align-items: flex-start;
}

/* 左侧标题与卡片列表 */
.showcase-left-col {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.showcase-header-block {
  margin-bottom: 6px;
}

.showcase-main-title {
  font-size: clamp(24px, 2.5vw, 32px);
  font-weight: 800;
  color: #0f172a;
  line-height: 1.25;
  letter-spacing: -0.025em;
  margin-bottom: 10px;
}

.highlight-role-text {
  color: var(--active-theme);
  transition: color 0.3s ease;
}

.showcase-subtitle {
  font-size: 13.5px;
  color: #64748b;
  line-height: 1.6;
}

/* 步骤卡片列表 */
.steps-card-list {
  display: flex;
  flex-direction: column;
  gap: 14px;
  position: relative;
}

/* 步骤卡片基本几何与边框 */
.step-item-card {
  position: relative;
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 18px;
  padding: 18px 22px;
  cursor: pointer;
  transition: all 0.28s cubic-bezier(0.22, 1, 0.36, 1);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.02);
  user-select: none;
}

.step-item-card:hover {
  transform: translateY(-2px);
  border-color: rgba(203, 213, 225, 1);
  box-shadow: 0 6px 18px -4px rgba(15, 23, 42, 0.06);
}

/* ========================================================
   Open Study 同款多层柔光发光外阴影 + 内阴影 (Ambient Glow)
   ======================================================== */
.step-item-card.active {
  background: linear-gradient(135deg, rgba(var(--active-rgb), 0.05) 0%, #ffffff 55%);
  border-color: var(--active-theme);
  box-shadow:
    0 0 1px 0 rgba(var(--active-rgb), 0.55),
    0 4px 16px -2px rgba(var(--active-rgb), 0.16),
    0 16px 38px -4px rgba(var(--active-rgb), 0.18),
    inset 0 0 0 1px rgba(var(--active-rgb), 0.15),
    inset 0 1px 18px 0 rgba(var(--active-rgb), 0.06);
}

.step-card-inner {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.step-num-code {
  font-size: 13px;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.5px;
  transition: color 0.25s ease;
}

.step-item-card.active .step-num-code {
  color: var(--active-theme);
}

.step-card-title {
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.35;
  transition: color 0.25s ease;
}

.step-item-card.active .step-card-title {
  color: #0f172a;
}

/* ========================================================
   Open Study 同款水平射入连接线光束 (Connector Beam Bridge)
   精确连接两端无缝鸿沟
   ======================================================== */
.connector-beam-line {
  position: absolute;
  left: 100%;
  top: 50%;
  width: 41px;
  height: 2px;
  transform: translateY(-50%);
  transform-origin: left center;
  background: var(--active-theme);
  z-index: 25;
  pointer-events: none;
  animation: beamExtend 0.24s cubic-bezier(0.22, 1, 0.36, 1) forwards;
  box-shadow: 0 0 8px rgba(var(--active-rgb), 0.55);
}

@keyframes beamExtend {
  0% {
    transform: translateY(-50%) scaleX(0);
    opacity: 0;
  }
  100% {
    transform: translateY(-50%) scaleX(1);
    opacity: 1;
  }
}

.connector-beam-glow {
  position: absolute;
  inset: -1.5px 0;
  background: var(--active-theme);
  filter: blur(2.5px);
  opacity: 0.6;
}

/* ========================================================
   右侧模拟工作台视窗：高阶大圆角白底卡片 (Live Mockup Workspace)
   ======================================================== */
.showcase-right-col {
  width: 100%;
}

.mockup-workspace-card {
  background: #ffffff;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-radius: 22px;
  box-shadow:
    0 1px 3px rgba(15, 23, 42, 0.02),
    0 18px 46px -6px rgba(15, 23, 42, 0.07);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 490px;
  position: relative;
}

/* 顶部标题栏 */
.workspace-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 13px 22px;
  border-bottom: 1px solid rgba(241, 245, 249, 1);
  background: rgba(250, 252, 255, 0.85);
}

.workspace-title-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dot-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--active-theme);
  box-shadow: 0 0 8px rgba(var(--active-rgb), 0.5);
  transition: background-color 0.25s ease, box-shadow 0.25s ease;
}

.workspace-title-text {
  font-size: 13px;
  font-weight: 600;
  color: #334155;
  letter-spacing: -0.2px;
}

.workspace-live-badge {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.6px;
  padding: 2px 7px;
  border-radius: 999px;
  background: rgba(var(--active-rgb), 0.1);
  color: var(--active-theme);
}

/* ========================================================
   Open Study 核心 2x12 点阵 (Dot Matrix Pulse Wave)
   ======================================================== */
.matrix-dots-pattern {
  display: flex;
  flex-direction: column;
  gap: 3.5px;
  padding: 2px 4px;
}

.matrix-dots-row {
  display: flex;
  gap: 3.5px;
}

.matrix-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: #0f172a;
  opacity: var(--dot-alpha);
  transition: opacity 0.2s ease;
}

/* 运行态波浪跳动脉冲动画 */
.matrix-dots-pattern.is-running .matrix-dot {
  animation: dot-matrix-pulse 0.85s linear infinite;
  animation-delay: var(--dot-delay);
}

@keyframes dot-matrix-pulse {
  0%, 100% {
    opacity: 0.08;
    transform: scale(0.9);
  }
  40% {
    opacity: calc(var(--dot-alpha) * 1.35 + 0.25);
    transform: scale(1.15);
  }
  70% {
    opacity: 0.18;
  }
}

/* ========================================================
   视窗内容主体：流式打字与执行节点
   ======================================================== */
.workspace-body-content {
  padding: 22px 24px;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 指令行与打字机 */
.agent-command-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 14px;
  color: #0f172a;
  line-height: 1.55;
  min-height: 24px;
}

.prompt-symbol {
  color: var(--active-theme);
  font-weight: 700;
  user-select: none;
  flex-shrink: 0;
}

.prompt-text-wrap {
  display: inline;
}

.command-text {
  font-weight: 600;
  color: #1e293b;
}

/* Open Study 同款黑色方块打字机光标 */
.prompt-cli-cursor {
  display: inline-block;
  width: 7px;
  height: 1.05em;
  background: var(--active-theme);
  margin-left: 4px;
  vertical-align: -0.15em;
  opacity: 1;
}

.prompt-cli-cursor.is-blinking {
  animation: cli-cursor-blink 1s steps(1, end) infinite;
}

@keyframes cli-cursor-blink {
  0%, 48% { opacity: 1; }
  49%, 100% { opacity: 0; }
}

/* 执行树节点列表 */
.agent-execution-tree {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-left: 2px;
  opacity: 0;
  transition: opacity 0.2s ease;
}

.agent-execution-tree.visible {
  opacity: 1;
}

.tree-node-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12.5px;
  opacity: 0;
  transform: translateY(6px);
  transition: opacity 0.22s cubic-bezier(0.22, 1, 0.36, 1), transform 0.22s cubic-bezier(0.22, 1, 0.36, 1);
}

.tree-node-item.revealed {
  opacity: 1;
  transform: translateY(0);
}

.tree-corner {
  color: #94a3b8;
  font-family: monospace;
  font-size: 14px;
}

.node-tag-pill {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 8px;
  background: #f1f5f9;
  color: #475569;
  font-size: 12px;
  border: 1px solid rgba(226, 232, 240, 0.85);
  overflow: hidden;
}

.node-tag-pill.success {
  background: #f0fdf4;
  color: #166534;
  border-color: #bbf7d0;
}

.node-tag-pill.info {
  background: #eff6ff;
  color: #1e40af;
  border-color: #bfdbfe;
}

.node-tag-pill.active {
  background: var(--active-bg-soft);
  color: var(--active-theme);
  border-color: rgba(var(--active-rgb), 0.3);
  font-weight: 600;
}

.node-tag-pill.done {
  background: #f8fafc;
  color: #0f172a;
  font-weight: 600;
  border-color: #cbd5e1;
}

.node-detail {
  color: #64748b;
  font-weight: 400;
  padding-left: 4px;
  border-left: 1px solid rgba(148, 163, 184, 0.4);
}

/* 节点内微妙的扫描光条 */
.status-sweep-line {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 45px;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.7), transparent);
  mix-blend-mode: overlay;
  pointer-events: none;
  animation: sweepMove 2.2s ease-in-out infinite;
}

@keyframes sweepMove {
  0% { transform: translateX(-50px); }
  100% { transform: translateX(300px); }
}

/* ========================================================
   研判裁决输出面板 (Verdict Panel)
   ======================================================== */
.verdict-output-panel {
  background: #f8fafd;
  border: 1px solid rgba(226, 232, 240, 0.95);
  border-left: 4px solid var(--active-theme);
  border-radius: 14px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  box-shadow: 0 4px 14px -3px rgba(15, 23, 42, 0.03);
}

.verdict-reveal-enter-active {
  animation: verdictIn 0.3s cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes verdictIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.verdict-badge-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.verdict-status-tag {
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  background: var(--active-bg-soft);
  color: var(--active-theme);
  border: 1px solid rgba(var(--active-rgb), 0.2);
}

.verdict-norm-code {
  font-size: 12px;
  color: #64748b;
  font-weight: 600;
}

.verdict-summary-text {
  font-size: 13.5px;
  color: #334155;
  line-height: 1.55;
}

.verdict-action-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12.5px;
  color: #0f172a;
  padding-top: 6px;
  border-top: 1px dashed #e2e8f0;
}

.action-label {
  font-weight: 600;
  color: #475569;
  flex-shrink: 0;
}

.action-value {
  color: #0f172a;
  font-weight: 500;
}

/* ========================================================
   视窗底部模拟打字框 (极度干净克制)
   ======================================================== */
.workspace-footer-bar {
  padding: 13px 20px;
  border-top: 1px solid rgba(241, 245, 249, 1);
  background: #ffffff;
}

.mock-input-box {
  background: #f8fafc;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  padding: 9px 14px;
  font-size: 13px;
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
}

.mock-placeholder {
  color: #94a3b8;
}

.mock-send-hint {
  font-size: 13px;
  color: #cbd5e1;
  font-weight: 700;
}

/* ========================================================
   响应式断点适配：平板与小屏优雅垂直堆叠
   ======================================================== */
@media (max-width: 960px) {
  .showcase-main-grid {
    grid-template-columns: 1fr;
    gap: 28px;
  }
  .connector-beam-line {
    display: none !important;
  }
}
</style>
