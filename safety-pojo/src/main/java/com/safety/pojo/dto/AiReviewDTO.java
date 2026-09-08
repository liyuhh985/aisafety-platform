package com.safety.pojo.dto;

import lombok.Data;

/** 管理员人工审核：通过(pass=true) / 驳回(pass=false) */
@Data
public class AiReviewDTO {
    private Boolean pass;
    private String remark;
}
