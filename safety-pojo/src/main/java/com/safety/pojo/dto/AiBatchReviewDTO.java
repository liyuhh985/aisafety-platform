package com.safety.pojo.dto;

import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.util.List;

@Data
public class AiBatchReviewDTO {

    @NotEmpty(message = "待审批工单ID列表不能为空")
    private List<Long> ids;

    @NotNull(message = "审批结果不能为空")
    private Boolean pass;

    private String remark;
}
