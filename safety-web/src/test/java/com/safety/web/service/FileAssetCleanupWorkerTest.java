package com.safety.web.service;

import com.safety.pojo.entity.FileAsset;
import com.safety.service.service.FileAssetService;
import com.safety.service.service.FileUploadService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class FileAssetCleanupWorkerTest {

    @Mock
    private FileAssetService fileAssetService;
    @Mock
    private FileUploadService fileUploadService;

    private FileAssetCleanupWorker worker;

    @BeforeEach
    void setUp() {
        worker = new FileAssetCleanupWorker(fileAssetService, fileUploadService, 50);
    }

    @Test
    void expiredTempIsRemovedAndMetadataDeleted() {
        FileAsset asset = asset(9L);
        when(fileAssetService.findExpiredTemps(50)).thenReturn(List.of(asset));
        when(fileAssetService.claimExpiredTemp(eq(9L), anyString())).thenReturn(true);

        worker.processExpiredTemps();

        verify(fileUploadService).removeObject(asset.getBucket(), asset.getObjectKey());
        verify(fileAssetService).deleteClaimedTemp(eq(9L), anyString());
    }

    @Test
    void failedRemovalIsReleasedForRetry() {
        FileAsset asset = asset(10L);
        when(fileAssetService.findExpiredTemps(50)).thenReturn(List.of(asset));
        when(fileAssetService.claimExpiredTemp(eq(10L), anyString())).thenReturn(true);
        doThrow(new RuntimeException("minio down"))
                .when(fileUploadService).removeObject(asset.getBucket(), asset.getObjectKey());

        worker.processExpiredTemps();

        verify(fileAssetService).releaseCleanupFailure(eq(10L), anyString());
        verify(fileAssetService, never()).deleteClaimedTemp(eq(10L), anyString());
    }

    private static FileAsset asset(Long id) {
        FileAsset asset = new FileAsset();
        asset.setId(id);
        asset.setBucket("safety-images");
        asset.setObjectKey("tmp-" + id + ".png");
        return asset;
    }
}

