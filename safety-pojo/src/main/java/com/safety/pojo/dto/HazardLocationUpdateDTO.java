package com.safety.pojo.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import lombok.Data;

import java.math.BigDecimal;

/**
 * 隐患定位与地址修改请求 DTO
 */
@Data
public class HazardLocationUpdateDTO {

    @NotNull(message = "经度不能为空")
    private BigDecimal longitude;

    @NotNull(message = "纬度不能为空")
    private BigDecimal latitude;

    @NotBlank(message = "详细地址不能为空")
    private String address;

    /**
     * 所属片区（例如：福建省三明市三元区）
     */
    private String district;
}
