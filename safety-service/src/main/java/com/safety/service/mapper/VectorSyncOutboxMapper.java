package com.safety.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.safety.pojo.entity.VectorSyncOutbox;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.time.LocalDateTime;
import java.util.List;

@Mapper
public interface VectorSyncOutboxMapper extends BaseMapper<VectorSyncOutbox> {

    @Select("""
            SELECT id, source_table, doc_id, operation, status, claim_version, retry_count,
                   next_retry_time, locked_at, last_error, create_time, update_time
            FROM tb_vector_sync_outbox
            WHERE ((status IN ('PENDING', 'RETRY') AND next_retry_time <= CURRENT_TIMESTAMP)
               OR (status = 'PROCESSING'
                   AND locked_at < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 5 MINUTE)))
              AND retry_count < 10
            ORDER BY create_time, id
            LIMIT #{limit}
            """)
    List<VectorSyncOutbox> findClaimable(@Param("limit") int limit);

    @Update("""
            UPDATE tb_vector_sync_outbox
            SET status = 'PROCESSING', locked_at = CURRENT_TIMESTAMP,
                claim_version = claim_version + 1,
                update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND claim_version = #{claimVersion}
              AND ((status IN ('PENDING', 'RETRY')
                    AND next_retry_time <= CURRENT_TIMESTAMP)
                OR (status = 'PROCESSING'
                    AND locked_at < DATE_SUB(CURRENT_TIMESTAMP, INTERVAL 5 MINUTE)))
              AND retry_count < 10
            """)
    int claim(
            @Param("id") Long id,
            @Param("claimVersion") int claimVersion);

    @Update("""
            UPDATE tb_vector_sync_outbox
            SET status = 'SUCCEEDED', locked_at = NULL, last_error = NULL,
                update_time = CURRENT_TIMESTAMP
            WHERE id = #{id} AND status = 'PROCESSING'
              AND claim_version = #{claimVersion}
            """)
    int markSucceeded(
            @Param("id") Long id,
            @Param("claimVersion") int claimVersion);

    @Update("""
            UPDATE tb_vector_sync_outbox
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
            UPDATE tb_vector_sync_outbox
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
