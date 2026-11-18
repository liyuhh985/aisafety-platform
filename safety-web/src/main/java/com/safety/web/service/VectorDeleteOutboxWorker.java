package com.safety.web.service;

import com.safety.pojo.entity.VectorSyncOutbox;
import com.safety.service.service.VectorSyncOutboxService;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.List;

@Component
public class VectorDeleteOutboxWorker {

    private final VectorSyncOutboxService outboxService;
    private final AiService aiService;
    private final int batchSize;

    public VectorDeleteOutboxWorker(
            VectorSyncOutboxService outboxService,
            AiService aiService,
            @Value("${vector-sync.delete.batch-size:50}") int batchSize) {
        this.outboxService = outboxService;
        this.aiService = aiService;
        this.batchSize = batchSize;
    }

    @Scheduled(fixedDelayString = "${vector-sync.delete.poll-delay-ms:30000}")
    public void processPendingDeletes() {
        for (VectorSyncOutbox task : outboxService.findClaimable(batchSize)) {
            Integer claimVersion = outboxService.claim(task);
            if (claimVersion == null) {
                continue;
            }
            try {
                aiService.deleteVectors(
                        task.getSourceTable(), List.of(task.getDocId()));
                outboxService.markSucceeded(task.getId(), claimVersion);
            } catch (VectorSyncPermanentException e) {
                outboxService.markFailed(
                        task.getId(), claimVersion, e.getMessage());
            } catch (RuntimeException e) {
                outboxService.markRetry(
                        task.getId(),
                        claimVersion,
                        task.getRetryCount(),
                        e.getClass().getSimpleName());
            }
        }
    }
}
