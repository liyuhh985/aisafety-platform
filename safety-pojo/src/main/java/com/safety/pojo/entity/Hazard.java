package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

@Data
@TableName("tb_hazard")
public class Hazard {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String imageUrl;
    private String hazardType;
    private String description;
    private BigDecimal longitude;
    private BigDecimal latitude;
    private String address;
    private String district;
    private Integer severity;
    private Integer status;
    private Long handlerId;
    private String report;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
