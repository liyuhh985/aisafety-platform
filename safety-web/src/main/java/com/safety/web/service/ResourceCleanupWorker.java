package com.safety.web.service;

import com.safety.pojo.entity.ResourceCleanupOutbox;
import com.safety.service.service.FileUploadService;
import com.safety.service.service.ResourceCleanupOutboxService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * 消费对象清理 outbox：删报告时 MinIO 删除失败的对象在这里被重试。
 * 与 VectorDeleteOutboxWorker 同模式（claim CAS + 退避），区别是重试到
 * {@link ResourceCleanupOutboxService#MAX_ATTEMPTS} 次后终结为 FAILED，不再无限重试。
 */
@Slf4j
@Component
public class ResourceCleanupWorker {

    private final ResourceCleanupOutboxService outboxService;
    private final FileUploadService fileUploadService;
    private final int batchSize;

    public ResourceCleanupWorker(
            ResourceCleanupOutboxService outboxService,
            FileUploadService fileUploadService,
            @Value("${resource-cleanup.batch-size:50}") int batchSize) {
        this.outboxService = outboxService;
        this.fileUploadService = fileUploadService;
        this.batchSize = batchSize;
    }

    @Scheduled(fixedDelayString = "${resource-cleanup.poll-delay-ms:60000}")
    public void processPendingCleanups() {
        for (ResourceCleanupOutbox task : outboxService.findClaimable(batchSize)) {
            Integer claimVersion = outboxService.claim(task);
            if (claimVersion == null) {
                continue;
            }
            if (task.getObjectKey() == null || task.getObjectKey().isBlank()) {
                log.error("对象清理任务缺少 objectKey，标记失败: id={}", task.getId());
                outboxService.markFailed(task.getId(), claimVersion, "missing objectKey");
                continue;
            }
            try {
                fileUploadService.removeObject(task.getBucket(), task.getObjectKey());
                outboxService.markSucceeded(task.getId(), claimVersion);
            } catch (RuntimeException e) {
                reportFailure(task, claimVersion, e);
            }
        }
    }

    private void reportFailure(
            ResourceCleanupOutbox task, int claimVersion, RuntimeException failure) {
        String error = failure.getMessage() != null && !failure.getMessage().isBlank()
                ? failure.getMessage()
                : failure.getClass().getSimpleName();
        if (task.getRetryCount() + 1 >= ResourceCleanupOutboxService.MAX_ATTEMPTS) {
            log.error("对象清理任务重试 {} 次仍失败，标记 FAILED: id={} object={}",
                    task.getRetryCount() + 1, task.getId(), task.getObjectKey(), failure);
            outboxService.markFailed(task.getId(), claimVersion, error);
            return;
        }
        log.warn("对象清理任务失败，稍后重试: id={} attempt={} object={}",
                task.getId(), task.getRetryCount() + 1, task.getObjectKey(), failure);
        outboxService.markRetry(
                task.getId(), claimVersion, task.getRetryCount(), error);
    }
}
