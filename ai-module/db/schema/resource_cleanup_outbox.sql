-- Durable outbox for eventual MySQL-to-Milvus delete synchronization.
CREATE TABLE IF NOT EXISTS tb_vector_sync_outbox (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_table    VARCHAR(64)   NOT NULL,
    doc_id          BIGINT        NOT NULL,
    operation       VARCHAR(16)   NOT NULL,
    status          VARCHAR(20)   NOT NULL,
    claim_version   INT           NOT NULL DEFAULT 0,
    retry_count     INT           NOT NULL DEFAULT 0,
    next_retry_time DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    locked_at       DATETIME      NULL,
    last_error      VARCHAR(1000) NULL,
    create_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_vector_sync_due (status, next_retry_time),
    INDEX idx_vector_sync_stale (status, locked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

SET @claim_version_exists = (
    SELECT COUNT(*)
    FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'tb_vector_sync_outbox'
      AND column_name = 'claim_version'
);
SET @claim_version_ddl = IF(
    @claim_version_exists = 0,
    'ALTER TABLE tb_vector_sync_outbox ADD COLUMN claim_version INT NOT NULL DEFAULT 0 AFTER status',
    'SELECT 1'
);
PREPARE claim_version_statement FROM @claim_version_ddl;
EXECUTE claim_version_statement;
DEALLOCATE PREPARE claim_version_statement;

-- 对象（MinIO）清理 outbox：与向量删除 outbox 同一套 claim/退避语义，见
-- 设计依据见私有历史归档
CREATE TABLE IF NOT EXISTS tb_resource_cleanup_outbox (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    target VARCHAR(16) NOT NULL, ref_id BIGINT NULL, source_table VARCHAR(64) NULL,
    bucket VARCHAR(64) NULL, object_key VARCHAR(255) NULL, status VARCHAR(20) NOT NULL,
    claim_version INT NOT NULL DEFAULT 0, retry_count INT NOT NULL DEFAULT 0,
    next_retry_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, locked_at DATETIME NULL,
    last_error VARCHAR(1000) NULL,
    create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_resource_cleanup_due (status, next_retry_time),
    INDEX idx_resource_cleanup_stale (status, locked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

