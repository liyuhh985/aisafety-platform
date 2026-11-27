package com.safety.service.service.support;

import com.safety.common.exception.BusinessException;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HazardTypeNormalizerTest {

    @Test
    void normalizesEnglishChineseLabelsAndDeduplicatesPreservingOrder() {
        String result = HazardTypeNormalizer.normalizeForStorage(List.of(
                "fire/fire_lane_blocked",
                "市政设施/井盖缺失/破损",
                "消防通道占用",
                "消防安全/消防通道占用"
        ), null);

        assertEquals("消防安全/消防通道占用,市政设施/井盖缺失/破损", result);
    }

    @Test
    void usesLegacyCategoryAsFallbackAndConvertsItToChinesePath() {
        assertEquals("市政设施/井盖缺失/破损",
                HazardTypeNormalizer.normalizeForStorage(List.of(), "municipal/manhole_damage"));
    }

    @Test
    void rejectsBlankUnknownAndMoreThanThreeTypes() {
        assertEquals(400, assertThrows(BusinessException.class,
                () -> HazardTypeNormalizer.normalizeForStorage(List.of(" "), null)).getCode());
        assertEquals(400, assertThrows(BusinessException.class,
                () -> HazardTypeNormalizer.normalizeForStorage(
                        List.of("消防安全/消防通道占用", ""), null)).getCode());
        assertEquals(400, assertThrows(BusinessException.class,
                () -> HazardTypeNormalizer.normalizeForStorage(List.of("fire/not_real"), null)).getCode());
        assertEquals(400, assertThrows(BusinessException.class,
                () -> HazardTypeNormalizer.normalizeForStorage(List.of(
                        "消防安全/消防通道占用",
                        "消防安全/消防设施故障",
                        "建筑安全/危房",
                        "市政设施/井盖缺失/破损"
                ), null)).getCode());
    }

    @Test
    void rejectsBroadLegacyLabelsThatCannotIdentifyOneSubcategory() {
        for (String value : List.of(
                "占道", "井盖/道路", "电气", "施工",
                "交通安全", "建筑施工", "电气安全", "燃气安全", "电梯安全", "环境安全")) {
            assertEquals(400, assertThrows(BusinessException.class,
                    () -> HazardTypeNormalizer.normalizeOne(value)).getCode(), value);
        }
    }

    @Test
    void rejectsNineRetiredSubcategoryTokensWithExplicitUpgradeMessage() {
        for (String value : List.of(
                "building/wall_crack_lean", "建筑安全/墙体开裂/倾斜", "墙体开裂/倾斜",
                "building/facade_fall", "建筑安全/外立面脱落", "外立面脱落",
                "fire/fire_water_abnormal", "消防安全/消防水源异常", "消防水源异常")) {
            BusinessException exc = assertThrows(BusinessException.class,
                    () -> HazardTypeNormalizer.normalizeOne(value), value);
            assertEquals(400, exc.getCode(), value);
            assertEquals("隐患类别已升级，请刷新页面", exc.getMessage(), value);
        }
    }

    @Test
    void exposesExactlyTwentyNineCanonicalChinesePaths() {
        assertEquals(29, HazardTypeNormalizer.canonicalTypes().size());
        assertTrue(HazardTypeNormalizer.canonicalTypes().contains("市政设施/排水/积水"));
        assertTrue(HazardTypeNormalizer.canonicalTypes().contains("电气与燃气/燃气管道老化"));
        assertTrue(HazardTypeNormalizer.canonicalTypes().contains("建筑安全/危房"));
        assertTrue(HazardTypeNormalizer.canonicalTypes().contains("建筑安全/高空坠物"));
        assertTrue(HazardTypeNormalizer.canonicalTypes().contains("消防安全/消防设施故障"));
        assertTrue(!HazardTypeNormalizer.canonicalTypes().contains("建筑安全/墙体开裂/倾斜"));
        assertTrue(!HazardTypeNormalizer.canonicalTypes().contains("建筑安全/外立面脱落"));
        assertTrue(!HazardTypeNormalizer.canonicalTypes().contains("消防安全/消防水源异常"));
    }
}
