package com.safety.web.service;

import com.safety.pojo.entity.FileAsset;
import com.safety.service.service.FileAssetService;
import com.safety.service.service.FileUploadService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Slf4j
@Component
public class FileAssetCleanupWorker {

    private final FileAssetService fileAssetService;
    private final FileUploadService fileUploadService;
    private final int batchSize;

    public FileAssetCleanupWorker(
            FileAssetService fileAssetService,
            FileUploadService fileUploadService,
            @Value("${file-asset.cleanup.batch-size:50}") int batchSize) {
        this.fileAssetService = fileAssetService;
        this.fileUploadService = fileUploadService;
        this.batchSize = batchSize;
    }

    @Scheduled(fixedDelayString = "${file-asset.cleanup.poll-delay-ms:600000}")
    public void processExpiredTemps() {
        for (FileAsset asset : fileAssetService.findExpiredTemps(batchSize)) {
            String claimToken = UUID.randomUUID().toString();
            if (!fileAssetService.claimExpiredTemp(asset.getId(), claimToken)) {
                continue;
            }
            try {
                fileUploadService.removeObject(asset.getBucket(), asset.getObjectKey());
                fileAssetService.deleteClaimedTemp(asset.getId(), claimToken);
            } catch (RuntimeException e) {
                log.warn("临时图片清理失败，稍后重试: id={} object={}", asset.getId(), asset.getObjectKey(), e);
                fileAssetService.releaseCleanupFailure(asset.getId(), claimToken);
            }
        }
    }
}

