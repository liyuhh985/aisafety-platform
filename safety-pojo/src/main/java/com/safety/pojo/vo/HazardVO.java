package com.safety.pojo.vo;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class HazardVO {
    private Long id;
    private Long userId;
    private String imageUrl;
    private String hazardType;
    private String description;
    private BigDecimal longitude;
    private BigDecimal latitude;
    private String address;
    private Integer severity;
    private Integer status;
    private String statusText;
    private LocalDateTime createTime;
}
