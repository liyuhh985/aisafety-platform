package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_hazard_report")
public class HazardReport {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long hazardId;
    private String aiAnalysis;
    private String riskLevel;
    private String suggestion;
    private String similarCases;
    private String modelUsed;
    private Integer tokenCost;
    private LocalDateTime createTime;
}
