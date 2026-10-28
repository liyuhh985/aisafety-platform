package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Data;

/** 管理员撤回无效工单：必须说明原因，便于审计追溯。 */
@Data
public class AdminWithdrawDTO {
    @NotBlank(message = "撤回原因不能为空")
    @Size(max = 500, message = "撤回原因不能超过500字")
    private String reason;
}
