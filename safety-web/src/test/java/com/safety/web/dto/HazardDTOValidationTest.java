package com.safety.web.dto;

import com.safety.pojo.dto.HazardDTO;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertTrue;

class HazardDTOValidationTest {

    private final Validator validator = Validation.buildDefaultValidatorFactory().getValidator();

    @Test
    void categoryListIsRequiredAndBoundedToThree() {
        HazardDTO missing = validDto();
        missing.setCategoryList(null);
        assertCategoryViolation(missing, "不能为空");

        HazardDTO empty = validDto();
        empty.setCategoryList(List.of());
        assertCategoryViolation(empty, "不能为空");

        HazardDTO tooMany = validDto();
        tooMany.setCategoryList(List.of(
                "消防安全/消防通道占用",
                "消防安全/消防设施故障",
                "建筑安全/危房",
                "市政设施/井盖缺失/破损"));
        assertCategoryViolation(tooMany, "最多 3 个");
    }

    @Test
    void blankCategoryItemIsRejected() {
        HazardDTO dto = validDto();
        dto.setCategoryList(List.of(" "));
        assertCategoryViolation(dto, "不能为空");
    }

    private HazardDTO validDto() {
        HazardDTO dto = new HazardDTO();
        dto.setLongitude(new BigDecimal("117.635"));
        dto.setLatitude(new BigDecimal("26.265"));
        dto.setCategoryList(List.of("消防安全/消防通道占用"));
        return dto;
    }

    private void assertCategoryViolation(HazardDTO dto, String messagePart) {
        Set<ConstraintViolation<HazardDTO>> violations = validator.validate(dto);
        assertTrue(violations.stream().anyMatch(v ->
                        v.getPropertyPath().toString().startsWith("categoryList")
                                && v.getMessage().contains(messagePart)),
                () -> "actual violations: " + violations);
    }
}
