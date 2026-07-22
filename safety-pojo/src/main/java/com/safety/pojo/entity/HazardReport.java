package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import com.fasterxml.jackson.annotation.JsonProperty;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_hazard_report")
public class HazardReport {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String imageUrl;
    private String hazardCategory;
    private String severity;
    private String description;
    private String rectification;
    private String reportText;

    @JsonProperty("createdAt")
    private LocalDateTime createTime;
}
