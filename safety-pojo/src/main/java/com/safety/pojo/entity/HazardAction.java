package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_hazard_action")
public class HazardAction {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long hazardId;
    private Long operatorId;
    private String actionType;
    private String remark;
    private LocalDateTime createTime;
}
