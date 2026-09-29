package com.safety.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.safety.pojo.entity.ResourceCleanupOutbox;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 对象清理 outbox 的 claim/退避 SQL。
 * 与 VectorSyncOutboxMapper 同构，但多一条 retry_count < 10：重试到上限后不再领取
 * （避免像向量删除那样无限重试）。
 */
@Mapper
public interface ResourceCleanupOutboxMapper extends BaseMapper<ResourceCleanupOutbox> {

    @Select("""
            SELECT id, target, ref_id, source_table, bucket, object_key, status, claim_version,
                   retry_count, next_retry_time, locked_at, last_error, create_time, update_time
            FROM tb_resource_cleanup_outbox
            WHERE retry_count < 10
              AND ((status IN ('PENDING', 'RETRY') AND next_retry_time <= CURRENT_TIMESTAMP)
                OR (status = 'PROCESSING'
                    AND locked_at < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 5 MINUTE)))
            ORDER BY create_time, id
            LIMIT #{limit}
            """)
    List<ResourceCleanupOutbox> findClaimable(@Param("limit") int limit);

    @Update("""
            UPDATE tb_resource_cleanup_outbox
            SET status = 'PROCESSING', locked_at = CURRENT_TIMESTAMP,
                claim_version = claim_version + 1,
                update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND claim_version = #{claimVersion}
              AND retry_count < 10
              AND ((status IN ('PENDING', 'RETRY')
                    AND next_retry_time <= CURRENT_TIMESTAMP)
                OR (status = 'PROCESSING'
                    AND locked_at < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 5 MINUTE)))
            """)
    int claim(
            @Param("id") Long id,
            @Param("claimVersion") int claimVersion);

    @Update("""
            UPDATE tb_resource_cleanup_outbox
            SET status = 'SUCCEEDED', locked_at = NULL, last_error = NULL,
                update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND status = 'PROCESSING'
              AND claim_version = #{claimVersion}
            """)
    int markSucceeded(
            @Param("id") Long id,
            @Param("claimVersion") int claimVersion);

    @Update("""
            UPDATE tb_resource_cleanup_outbox
            SET status = 'RETRY', retry_count = #{retryCount},
                next_retry_time = #{nextRetryTime}, locked_at = NULL,
                last_error = #{lastError}, update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND status = 'PROCESSING'
              AND claim_version = #{claimVersion}
            """)
    int markRetry(
            @Param("id") Long id,
            @Param("claimVersion") int claimVersion,
            @Param("retryCount") int retryCount,
            @Param("nextRetryTime") LocalDateTime nextRetryTime,
            @Param("lastError") String lastError);

    @Update("""
            UPDATE tb_resource_cleanup_outbox
            SET status = 'FAILED', locked_at = NULL, last_error = #{lastError},
                update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND status = 'PROCESSING'
              AND claim_version = #{claimVersion}
            """)
    int markFailed(
            @Param("id") Long id,
            @Param("claimVersion") int claimVersion,
            @Param("lastError") String lastError);
}
