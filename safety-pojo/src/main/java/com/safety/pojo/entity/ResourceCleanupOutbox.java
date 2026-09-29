package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 对象（MinIO）清理 outbox。
 * 与 tb_vector_sync_outbox 同一套 claim/退避/重试语义，见
 * docs/superpowers/specs/2026-09-29-retract-and-image-hard-delete-design.md §3.3
 */
@Data
@TableName("tb_resource_cleanup_outbox")
public class ResourceCleanupOutbox {
    @TableId(type = IdType.AUTO)
    private Long id;
    private String target;
    private Long refId;
    private String sourceTable;
    private String bucket;
    private String objectKey;
    private String status;
    private Integer claimVersion;
    private Integer retryCount;
    private LocalDateTime nextRetryTime;
    private LocalDateTime lockedAt;
    private String lastError;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}
