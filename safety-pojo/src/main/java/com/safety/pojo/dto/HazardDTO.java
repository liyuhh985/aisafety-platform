package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.math.BigDecimal;

@Data
public class HazardDTO {
    @NotBlank(message = "图片URL不能为空")
    private String imageUrl;

    @NotBlank(message = "隐患类型不能为空")
    private String hazardType;

    private String description;

    @NotNull(message = "经度不能为空")
    private BigDecimal longitude;

    @NotNull(message = "纬度不能为空")
    private BigDecimal latitude;

    private String address;

    private Integer severity;
}
