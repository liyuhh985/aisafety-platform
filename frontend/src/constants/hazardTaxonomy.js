/**
 * 城市安全隐患两级标准分类体系 (Canonical Hazard Taxonomy)
 * 遵循 与后端分类规范保持一致
 * 前端统一维护与解析核心模块
 */

// 1. 标准两级分类定义 (8 大一级类别 + 29 个标准二级子类)
export const HAZARD_TAXONOMY = [
  {
    code: "traffic",
    label: "交通与通行",
    subcategories: [
      { code: "road_occupancy", label: "占道经营/乱堆乱放" },
      { code: "vehicle_occupancy", label: "车辆占道" },
      { code: "blind_path_occupied", label: "盲道占用" },
      { code: "traffic_facility_damage", label: "交通设施损坏" },
    ],
  },
  {
    code: "municipal",
    label: "市政设施",
    subcategories: [
      { code: "manhole_damage", label: "井盖缺失/破损" },
      { code: "road_surface_collapse", label: "路面塌陷" },
      { code: "drainage_flood", label: "排水/积水" },
      { code: "street_light_pole", label: "路灯/线杆损坏" },
    ],
  },
  {
    code: "fire",
    label: "消防安全",
    subcategories: [
      { code: "fire_lane_blocked", label: "消防通道占用" },
      { code: "fire_equipment_fault", label: "消防设施故障" },
      { code: "fire_water_abnormal", label: "消防水源异常" },
    ],
  },
  {
    code: "building",
    label: "建筑安全",
    subcategories: [
      { code: "dangerous_building", label: "危房" },
      { code: "wall_crack_lean", label: "墙体开裂/倾斜" },
      { code: "facade_fall", label: "外立面脱落" },
      { code: "falling_object", label: "高空坠物" },
      { code: "illegal_structure", label: "违规搭建" },
    ],
  },
  {
    code: "utility",
    label: "电气与燃气",
    subcategories: [
      { code: "exposed_wire", label: "裸露/老化电线" },
      { code: "distribution_box_fault", label: "配电设施故障" },
      { code: "illegal_wiring", label: "私拉乱接" },
      { code: "gas_leak", label: "燃气泄漏" },
      { code: "gas_pipe_aging", label: "燃气管道老化" },
    ],
  },
  {
    code: "construction",
    label: "施工安全",
    subcategories: [
      { code: "no_barrier", label: "未设置围挡" },
      { code: "no_warning", label: "无安全警示" },
      { code: "scaffold_guard", label: "脚手架/临边防护" },
      { code: "deep_pit", label: "深基坑风险" },
      { code: "temporary_power", label: "施工临时用电" },
    ],
  },
  {
    code: "elevator_special",
    label: "电梯与特种设备",
    subcategories: [
      { code: "elevator_trapped", label: "电梯困人" },
      { code: "elevator_stopped", label: "停运/异响" },
      { code: "elevator_inspection", label: "超期未检" },
    ],
  },
  {
    code: "environment_other",
    label: "环境与其他",
    subcategories: [
      { code: "garbage_pile", label: "垃圾堆积" },
      { code: "sewage_odor", label: "污水/异味" },
      { code: "other", label: "其他" },
    ],
  },
];

// 2. 历史遗留字符串平滑兼容映射表 (Legacy Mapping)
export const LEGACY_HAZARD_MAP = {
  "占道": { majorCode: "traffic", subcategoryCode: "road_occupancy" },
  "井盖/道路": { majorCode: "municipal", subcategoryCode: "manhole_damage" },
  "消防通道": { majorCode: "fire", subcategoryCode: "fire_lane_blocked" },
  "消防设施": { majorCode: "fire", subcategoryCode: "fire_equipment_fault" },
  "危房": { majorCode: "building", subcategoryCode: "dangerous_building" },
  "高空坠物": { majorCode: "building", subcategoryCode: "falling_object" },
  "电气": { majorCode: "utility", subcategoryCode: "exposed_wire" },
  "施工": { majorCode: "construction", subcategoryCode: "no_barrier" },
  "其他": { majorCode: "environment_other", subcategoryCode: "other" },
};

// 预构建索引表以获得 O(1) 的检索效率
const majorMap = new Map();
const majorLabelMap = new Map();
const subcategoryMap = new Map();
const subcategoryPathMap = new Map();
const subcategoryLabelMap = new Map();

for (const major of HAZARD_TAXONOMY) {
  majorMap.set(major.code, major);
  majorLabelMap.set(major.label, major);
  for (const sub of major.subcategories) {
    const resolved = {
      majorCode: major.code,
      majorLabel: major.label,
      subcategoryCode: sub.code,
      subcategoryLabel: sub.label,
    };
    subcategoryMap.set(`${major.code}/${sub.code}`, resolved);
    subcategoryPathMap.set(`${major.label}/${sub.label}`, resolved);
    subcategoryLabelMap.set(sub.label, resolved);
  }
}

/**
 * 3. 核心隐患类型解析函数 (带 4 级容错降级)
 * @param {string} rawType 原始类型字符串，如 'fire/fire_equipment_fault' 或 '占道'
 * @returns {object} 解析结果对象
 */
export function resolveHazard(rawType) {
  const emptyResult = {
    majorCode: "",
    majorLabel: "未分类",
    subcategoryCode: "",
    subcategoryLabel: "",
    displayText: "未定类别",
    isLegacy: false,
    isUnknown: true,
  };

  if (!rawType || typeof rawType !== "string") {
    return emptyResult;
  }

  const trimmed = rawType.trim();
  if (!trimmed) return emptyResult;

  // 步骤 1: 优先匹配数据库中的中文路径，如“消防安全/消防通道占用”
  const exactPath = subcategoryPathMap.get(trimmed);
  if (exactPath) {
    return {
      ...exactPath,
      displayText: `${exactPath.majorLabel} · ${exactPath.subcategoryLabel}`,
      isLegacy: false,
      isUnknown: false,
    };
  }

  // 步骤 2: 兼容英文 <major_code>/<subcategory_code>
  if (trimmed.includes("/")) {
    const [mCode, sCode] = trimmed.split("/");
    const exact = subcategoryMap.get(`${mCode}/${sCode}`);
    if (exact) {
      return {
        ...exact,
        displayText: `${exact.majorLabel} · ${exact.subcategoryLabel}`,
        isLegacy: false,
        isUnknown: false,
      };
    }

    // 若 subcategory 未在字典中但 majorCode 存在，做大类降级匹配
    const majorOnly = majorMap.get(mCode);
    if (majorOnly) {
      return {
        majorCode: majorOnly.code,
        majorLabel: majorOnly.label,
        subcategoryCode: sCode || "",
        subcategoryLabel: sCode || "",
        displayText: sCode ? `${majorOnly.label} · ${sCode}` : majorOnly.label,
        isLegacy: false,
        isUnknown: false,
      };
    }
  }

  // 步骤 3: 尝试直接匹配一级类别代码 (如单独传 'fire')
  const majorByCode = majorMap.get(trimmed);
  if (majorByCode) {
    return {
      majorCode: majorByCode.code,
      majorLabel: majorByCode.label,
      subcategoryCode: "",
      subcategoryLabel: "",
      displayText: majorByCode.label,
      isLegacy: false,
      isUnknown: false,
    };
  }

  // 步骤 4: 支持中文一级类别名或小类名
  const majorByLabel = majorLabelMap.get(trimmed);
  if (majorByLabel) {
    return {
      majorCode: majorByLabel.code,
      majorLabel: majorByLabel.label,
      subcategoryCode: "",
      subcategoryLabel: "",
      displayText: majorByLabel.label,
      isLegacy: false,
      isUnknown: false,
    };
  }
  const subByLabel = subcategoryLabelMap.get(trimmed);
  if (subByLabel) {
    return {
      ...subByLabel,
      displayText: `${subByLabel.majorLabel} · ${subByLabel.subcategoryLabel}`,
      isLegacy: false,
      isUnknown: false,
    };
  }

  // 步骤 5: 走历史遗留映射表 (Legacy Mapping)
  const legacy = LEGACY_HAZARD_MAP[trimmed];
  if (legacy) {
    const matched = subcategoryMap.get(`${legacy.majorCode}/${legacy.subcategoryCode}`);
    if (matched) {
      return {
        ...matched,
        displayText: `${matched.majorLabel} · ${matched.subcategoryLabel}`,
        isLegacy: true,
        isUnknown: false,
      };
    }
  }

  // 步骤 6: 兜底降级，安全原样输出，绝不抛出异常导致页面崩溃
  return {
    majorCode: "unknown",
    majorLabel: trimmed,
    subcategoryCode: "",
    subcategoryLabel: "",
    displayText: trimmed,
    isLegacy: false,
    isUnknown: true,
  };
}

/**
 * 4. 解析包含多个逗号分隔类别的列表 (多隐患类别支持)
 * @param {string} rawTypes 逗号分隔的中文路径，如 '市政设施/井盖缺失/破损,消防安全/消防设施故障'
 * @returns {Array<object>} 解析后的类别对象数组（已去重、去空）
 */
export function resolveHazardList(rawTypes) {
  const raw = String(rawTypes || '').trim()
  if (!raw) return []
  const parts = raw.split(',').map(s => s.trim()).filter(Boolean)
  const list = []
  const seen = new Set()
  for (const p of parts) {
    const r = resolveHazard(p)
    if (r && (!r.isUnknown || r.displayText)) {
      const key = `${r.majorCode}/${r.subcategoryCode || ''}`
      if (!seen.has(key)) {
        seen.add(key)
        list.push(r)
      }
    }
  }
  if (list.length === 0 && raw) {
    list.push(resolveHazard(raw))
  }
  return list
}

/**
 * 5. 一级大类筛选匹配器（支持多类别逗号分隔：任一命中即算命中）
 * 遵循 docs/current/hazard-multi-category-frontend-patch.md
 * 仅按一级大类过滤，不进行二级子类精准匹配。
 * @param {string} taskType 工单中的 hazardTypes
 * @param {string} filterMajor 一级筛选 code（'all' 表示不过滤）
 * @returns {boolean} 是否命中筛选
 */
export function matchHazardFilter(taskType, filterMajor) {
  if (!filterMajor || filterMajor === 'all' || filterMajor === '全部') return true
  // 支持逗号分隔的多类别：任一类别的 majorCode 命中即算命中
  const raw = String(taskType || '')
  const parts = raw.includes(',') ? raw.split(',') : [raw]
  return parts.some((one) => {
    const r = resolveHazard(one.trim())
    return r.majorCode === filterMajor
  })
}

/**
 * 获取指定一级分类下的二级子项列表
 * @param {string} majorCode 一级分类 code
 * @returns {Array} 二级子项列表
 */
export function getSubcategoriesByMajor(majorCode) {
  if (!majorCode || majorCode === "all") return [];
  const major = majorMap.get(majorCode);
  return major ? major.subcategories : [];
}
