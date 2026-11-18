package com.safety.service.service;

import com.safety.pojo.entity.ResourceCleanupOutbox;
import com.safety.service.mapper.ResourceCleanupOutboxMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 对象清理任务的入队与认领。语义对齐 VectorSyncOutboxService：
 * PENDING -> (claim) PROCESSING -> SUCCEEDED / RETRY(退避) / FAILED。
 * 重试上限 {@link #MAX_ATTEMPTS}，到顶后由调用方终结为 FAILED。
 */
@Service
@RequiredArgsConstructor
public class ResourceCleanupOutboxService {

    /** 包含首次尝试在内的最大尝试次数；达到后不再重试。 */
    public static final int MAX_ATTEMPTS = 10;

    private static final String TARGET_MINIO = "MINIO";
    private static final int MAX_ERROR_LENGTH = 1000;
    private static final long MAX_RETRY_DELAY_SECONDS = 3600;

    private final ResourceCleanupOutboxMapper mapper;

    /** 记录一条"删除某个对象"的任务，立即可领取。 */
    public void enqueueObjectDelete(
            String bucket, String objectKey, String sourceTable, Long refId) {
        if (objectKey == null || objectKey.isBlank()) {
            throw new IllegalArgumentException("objectKey is required");
        }
        ResourceCleanupOutbox task = new ResourceCleanupOutbox();
        task.setTarget(TARGET_MINIO);
        task.setBucket(bucket);
        task.setObjectKey(objectKey);
        task.setSourceTable(sourceTable);
        task.setRefId(refId);
        task.setStatus("PENDING");
        task.setClaimVersion(0);
        task.setRetryCount(0);
        task.setNextRetryTime(LocalDateTime.now());
        mapper.insert(task);
    }

    public List<ResourceCleanupOutbox> findClaimable(int limit) {
        return mapper.findClaimable(limit);
    }

    public Integer claim(ResourceCleanupOutbox task) {
        int currentVersion = task.getClaimVersion();
        return mapper.claim(task.getId(), currentVersion) == 1
                ? currentVersion + 1
                : null;
    }

    public boolean markSucceeded(Long id, int claimVersion) {
        return mapper.markSucceeded(id, claimVersion) == 1;
    }

    public boolean markRetry(
            Long id,
            int claimVersion,
            int previousRetryCount,
            String error) {
        int retryCount = previousRetryCount + 1;
        long delaySeconds = retryDelaySeconds(previousRetryCount);
        return mapper.markRetry(
                id,
                claimVersion,
                retryCount,
                LocalDateTime.now().plusSeconds(delaySeconds),
                sanitizeError(error)) == 1;
    }

    public boolean markFailed(Long id, int claimVersion, String error) {
        return mapper.markFailed(id, claimVersion, sanitizeError(error)) == 1;
    }

    private static long retryDelaySeconds(int previousRetryCount) {
        int exponent = Math.max(0, Math.min(previousRetryCount, 30));
        long delay = 30L * (1L << exponent);
        return Math.min(delay, MAX_RETRY_DELAY_SECONDS);
    }

    private static String sanitizeError(String error) {
        if (error == null) {
            return "";
        }
        return error.length() <= MAX_ERROR_LENGTH
                ? error
                : error.substring(0, MAX_ERROR_LENGTH);
    }
}
