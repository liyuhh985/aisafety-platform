package com.safety.pojo.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

@Data
public class UpdateUserRoleDTO {
    /** 0 普通 / 1 管理员 / 2 处理人员 */
    @NotNull(message = "角色不能为空")
    private Integer role;
}
