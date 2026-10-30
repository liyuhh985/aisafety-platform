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
    /** 全部隐患类别，中文路径、英文逗号分隔、最多 3 条，无主次。 */
    private String hazardTypes;
    private String description;
    private BigDecimal longitude;
    private BigDecimal latitude;
    private String address;
    private String district;
    private Integer severity;
    private Integer status;
    private Long handlerId;
    private Integer reviewed;
    private String report;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
    /** 撤回时间（status=5 时非空） */
    private LocalDateTime withdrawnAt;
    /** 撤回人 userId */
    private Long withdrawnBy;
    /** 管理员撤回原因 */
    private String withdrawnReason;
    /** AI 建单请求 id（幂等键，唯一索引） */
    private String requestId;
}
