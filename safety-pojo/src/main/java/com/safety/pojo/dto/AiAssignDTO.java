package com.safety.pojo.dto;

import jakarta.validation.constraints.NotNull;
import lombok.Data;

/** 管理员派单：给隐患任务指定处理人员 */
@Data
public class AiAssignDTO {
    @NotNull(message = "处理人员不能为空")
    private Long handlerId;
}
