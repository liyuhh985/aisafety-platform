package com.safety.service.service.support;

import com.safety.common.exception.BusinessException;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 工单分类归一化：对外统一为“大类/小类”中文路径。 */
public final class HazardTypeNormalizer {

    public static final int MAX_TYPES = 3;
    public static final String UPGRADE_MESSAGE = "隐患类别已升级，请刷新页面";

    private static final Map<String, String> CODE_TO_PATH = new LinkedHashMap<>();
    private static final Map<String, String> TOKEN_TO_PATH = new LinkedHashMap<>();
    private static final Set<String> RETIRED_TOKENS = Set.of(
            "building/wall_crack_lean", "建筑安全/墙体开裂/倾斜", "墙体开裂/倾斜",
            "building/facade_fall", "建筑安全/外立面脱落", "外立面脱落",
            "fire/fire_water_abnormal", "消防安全/消防水源异常", "消防水源异常"
    );

    static {
        add("traffic", "交通与通行",
                "road_occupancy", "占道经营/乱堆乱放",
                "vehicle_occupancy", "车辆占道",
                "blind_path_occupied", "盲道占用",
                "traffic_facility_damage", "交通设施损坏");
        add("municipal", "市政设施",
                "manhole_damage", "井盖缺失/破损",
                "road_surface_collapse", "路面塌陷",
                "drainage_flood", "排水/积水",
                "street_light_pole", "路灯/线杆损坏",
                "tree_fall_hazard", "树木倒伏/断枝风险");
        add("fire", "消防安全",
                "fire_lane_blocked", "消防通道占用",
                "fire_equipment_fault", "消防设施故障",
                "ebike_hazard", "电动自行车违规停放/充电");
        add("building", "建筑安全",
                "dangerous_building", "危房",
                "falling_object", "高空坠物",
                "illegal_structure", "违规搭建");
        add("utility", "电气与燃气",
                "exposed_wire", "裸露/老化电线",
                "distribution_box_fault", "配电设施故障",
                "illegal_wiring", "私拉乱接",
                "gas_leak", "燃气泄漏",
                "gas_pipe_aging", "燃气管道老化");
        add("construction", "施工安全",
                "no_barrier", "未设置围挡",
                "no_warning", "无安全警示",
                "scaffold_guard", "脚手架/临边防护",
                "deep_pit", "深基坑风险",
                "temporary_power", "施工临时用电",
                "confined_space", "有限空间作业风险");
        add("elevator_special", "电梯与特种设备",
                "elevator_trapped", "电梯困人",
                "elevator_stopped", "停运/异响",
                "elevator_inspection", "超期未检");
        add("environment_other", "环境与其他",
                "garbage_pile", "垃圾堆积",
                "sewage_odor", "污水/异味",
                "hazmat_storage", "危化品/易燃易爆违规存运",
                "other", "其他");

        alias("消防通道", "fire/fire_lane_blocked");
        alias("消防设施", "fire/fire_equipment_fault");
        alias("危房", "building/dangerous_building");
        alias("高空坠物", "building/falling_object");
    }

    private HazardTypeNormalizer() {
    }

    /** 将前端、历史客户端或 AI 消息中的分类整理为唯一中文路径串。 */
    public static String normalizeForStorage(List<String> categoryList, String fallback) {
        LinkedHashSet<String> normalized = new LinkedHashSet<>();
        if (categoryList != null) {
            for (String item : categoryList) {
                if (item == null || item.isBlank()) {
                    throw new BusinessException(400, "隐患类别不能为空");
                }
                normalized.add(normalizeOne(item));
            }
        }
        if (normalized.isEmpty() && fallback != null && !fallback.isBlank()) {
            normalized.add(normalizeOne(fallback));
        }
        if (normalized.isEmpty()) {
            throw new BusinessException(400, "隐患类别不能为空");
        }
        if (normalized.size() > MAX_TYPES) {
            throw new BusinessException(400, "隐患类别最多 3 个");
        }
        return String.join(",", normalized);
    }

    public static String normalizeOne(String raw) {
        String key = raw == null ? "" : raw.trim();
        if (RETIRED_TOKENS.contains(key) || RETIRED_TOKENS.contains(key.toLowerCase())) {
            throw new BusinessException(400, UPGRADE_MESSAGE);
        }
        String path = TOKEN_TO_PATH.get(key);
        if (path == null) {
            path = TOKEN_TO_PATH.get(key.toLowerCase());
        }
        if (path == null) {
            throw new BusinessException(400, "隐患类别不合法: " + key);
        }
        return path;
    }

    public static List<String> canonicalTypes() {
        return List.copyOf(CODE_TO_PATH.values());
    }

    private static void add(String majorCode, String majorLabel, String... entries) {
        for (int i = 0; i < entries.length; i += 2) {
            String subCode = entries[i];
            String subLabel = entries[i + 1];
            String path = majorLabel + "/" + subLabel;
            CODE_TO_PATH.put(majorCode + "/" + subCode, path);
            TOKEN_TO_PATH.put(majorCode + "/" + subCode, path);
            TOKEN_TO_PATH.put(path, path);
            TOKEN_TO_PATH.put(subLabel, path);
        }
    }

    private static void alias(String token, String englishPath) {
        TOKEN_TO_PATH.put(token, CODE_TO_PATH.get(englishPath));
    }
}
