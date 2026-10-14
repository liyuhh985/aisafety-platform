package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.math.BigDecimal;
import java.util.List;

@Data
public class HazardDTO {
    @NotBlank(message = "图片URL不能为空")
    private String imageUrl;

    @NotBlank(message = "隐患类型不能为空")
    private String hazardType;

    /** 多类别上报（最多 3 条，第一条为主类别） */
    private List<String> categoryList;

    private String description;

    @NotNull(message = "经度不能为空")
    private BigDecimal longitude;

    @NotNull(message = "纬度不能为空")
    private BigDecimal latitude;

    private String address;

    private Integer severity;
}
