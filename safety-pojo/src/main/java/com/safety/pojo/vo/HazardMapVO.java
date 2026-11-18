package com.safety.pojo.vo;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * 匿名地图点位白名单投影。禁止加入用户、地址、描述、图片、报告等敏感字段。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class HazardMapVO {
    private Long id;
    private BigDecimal longitude;
    private BigDecimal latitude;
    private String hazardTypes;
    private Integer status;
    private String district;
}