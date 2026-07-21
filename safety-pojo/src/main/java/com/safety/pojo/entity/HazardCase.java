package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_hazard_case")
public class HazardCase {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String title;
    private String category;
    private String severity;
    private String city;
    private String district;
    private String occurrenceDate;
    private LocalDateTime createTime;
}
