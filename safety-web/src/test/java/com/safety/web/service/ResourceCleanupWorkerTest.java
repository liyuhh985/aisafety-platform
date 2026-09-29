package com.safety.web.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.ResourceCleanupOutbox;
import com.safety.service.service.FileUploadService;
import com.safety.service.service.ResourceCleanupOutboxService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * 对象清理 worker（spec §3.4-7）：
 *   · 删成功 -> SUCCEEDED
 *   · 删失败 -> retry_count 递增（markRetry）
 *   · 已经到上限（第 10 次） -> FAILED，不再重试
 */
@ExtendWith(MockitoExtension.class)
class ResourceCleanupWorkerTest {

    @Mock
    private ResourceCleanupOutboxService outboxService;
    @Mock
    private FileUploadService fileUploadService;

    private ResourceCleanupWorker worker;

    @BeforeEach
    void setUp() {
        worker = new ResourceCleanupWorker(outboxService, fileUploadService, 50);
    }

    @Test
    void unclaimedTaskIsNotDelivered() {
        ResourceCleanupOutbox task = task(1L, "safety-images", "a.png", 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(null);

        worker.processPendingCleanups();

        verifyNoInteractions(fileUploadService);
        verify(outboxService, never()).markSucceeded(anyLong(), anyInt());
    }

    @Test
    void successfulRemovalMarksTaskSucceeded() {
        ResourceCleanupOutbox task = task(1L, "safety-images", "a.png", 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);

        worker.processPendingCleanups();

        verify(fileUploadService).removeObject("safety-images", "a.png");
        verify(outboxService).markSucceeded(1L, 1);
    }

    @Test
    void transientFailureRetriesAndDoesNotBlockNextTask() {
        ResourceCleanupOutbox failed = task(1L, "safety-images", "a.png", 3);
        ResourceCleanupOutbox succeeded = task(2L, "safety-images", "b.png", 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(failed, succeeded));
        when(outboxService.claim(failed)).thenReturn(1);
        when(outboxService.claim(succeeded)).thenReturn(2);
        doThrow(new BusinessException(500, "图片删除失败，请重试"))
                .when(fileUploadService).removeObject("safety-images", "a.png");

        worker.processPendingCleanups();

        verify(outboxService).markRetry(1L, 1, 3, "图片删除失败，请重试");
        verify(outboxService, never()).markFailed(anyLong(), anyInt(), anyString());
        verify(fileUploadService).removeObject("safety-images", "b.png");
        verify(outboxService).markSucceeded(2L, 2);
    }

    @Test
    void failureOnLastAttemptMarksTaskFailed() {
        ResourceCleanupOutbox task =
                task(1L, "safety-images", "a.png", ResourceCleanupOutboxService.MAX_ATTEMPTS - 1);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);
        doThrow(new BusinessException(500, "图片删除失败，请重试"))
                .when(fileUploadService).removeObject("safety-images", "a.png");

        worker.processPendingCleanups();

        verify(outboxService).markFailed(1L, 1, "图片删除失败，请重试");
        verify(outboxService, never()).markRetry(anyLong(), anyInt(), anyInt(), anyString());
    }

    @Test
    void taskWithoutObjectKeyIsFailedWithoutTouchingMinio() {
        ResourceCleanupOutbox task = task(1L, "safety-images", null, 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);

        worker.processPendingCleanups();

        verifyNoInteractions(fileUploadService);
        verify(outboxService).markFailed(1L, 1, "missing objectKey");
    }

    private static ResourceCleanupOutbox task(
            Long id, String bucket, String objectKey, int retryCount) {
        ResourceCleanupOutbox task = new ResourceCleanupOutbox();
        task.setId(id);
        task.setBucket(bucket);
        task.setObjectKey(objectKey);
        task.setClaimVersion(0);
        task.setRetryCount(retryCount);
        return task;
    }
}
