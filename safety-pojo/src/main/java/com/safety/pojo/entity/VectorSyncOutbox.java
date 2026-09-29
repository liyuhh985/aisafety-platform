package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@TableName("tb_vector_sync_outbox")
public class VectorSyncOutbox {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String sourceTable;
    private Long docId;
    private String operation;
    private String status;
    private Integer claimVersion;
    private Integer retryCount;
    private LocalDateTime nextRetryTime;
    private LocalDateTime lockedAt;
    private String lastError;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
