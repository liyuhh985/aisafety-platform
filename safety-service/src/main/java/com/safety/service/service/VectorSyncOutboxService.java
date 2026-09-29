package com.safety.service.service;

import com.safety.pojo.entity.VectorSyncOutbox;
import com.safety.service.mapper.VectorSyncOutboxMapper;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;

@Service
@RequiredArgsConstructor
public class VectorSyncOutboxService {

    private static final Set<String> SUPPORTED_TABLES = Set.of(
            "tb_hazard_case",
            "tb_hazard_knowledge",
            "tb_regulation");
    private static final int MAX_ERROR_LENGTH = 1000;
    private static final long MAX_RETRY_DELAY_SECONDS = 3600;

    private final VectorSyncOutboxMapper mapper;

    public void enqueueDelete(String sourceTable, Long docId) {
        if (!SUPPORTED_TABLES.contains(sourceTable)) {
            throw new IllegalArgumentException("Unsupported vector source table");
        }
        VectorSyncOutbox event = new VectorSyncOutbox();
        event.setSourceTable(sourceTable);
        event.setDocId(docId);
        event.setOperation("DELETE");
        event.setStatus("PENDING");
        event.setClaimVersion(0);
        event.setRetryCount(0);
        event.setNextRetryTime(LocalDateTime.now());
        mapper.insert(event);
    }

    public List<VectorSyncOutbox> findClaimable(int limit) {
        return mapper.findClaimable(limit);
    }

    public Integer claim(VectorSyncOutbox task) {
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
