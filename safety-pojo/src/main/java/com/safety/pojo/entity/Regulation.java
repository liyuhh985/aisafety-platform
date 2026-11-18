package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_regulation")
public class Regulation {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String category;
    private String lawName;
    private String article;
    private String content;
    private String keywords;
    private String penalty;
    private String sourceUrl;
    private LocalDateTime createTime;
}
