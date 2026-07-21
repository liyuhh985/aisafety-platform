package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_hazard_knowledge")
public class HazardKnowledge {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String category;
    private String title;
    private String content;
    private String source;
    private String region;
    private LocalDateTime createTime;
}
