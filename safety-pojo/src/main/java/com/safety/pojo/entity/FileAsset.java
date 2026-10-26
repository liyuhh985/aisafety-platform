package com.safety.pojo.entity;

import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.Data;

import java.time.LocalDateTime;

/** MinIO 对象元数据。文件本体只在 MinIO，MySQL 不存 blob。 */
@Data
@TableName("tb_file_asset")
public class FileAsset {
    @TableId(type = IdType.AUTO)
    private Long id;
    private Long userId;
    private String bucket;
    private String objectKey;
    private String originalName;
    private String contentType;
    private Long sizeBytes;
    /** TEMP / ATTACHED */
    private String status;
    /** AUTHENTICATED / PRIVATE */
    private String visibility;
    /** 清理任务租约所有权，避免旧 worker 改写新 claim。 */
    private String claimToken;
    private LocalDateTime expiresAt;
    private LocalDateTime createTime;
    private LocalDateTime updateTime;
}

