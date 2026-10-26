package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.dto.ReportSaveDTO;
import com.safety.pojo.entity.FileAsset;
import com.safety.pojo.entity.HazardReport;
import com.safety.service.mapper.HazardReportMapper;
import io.minio.MinioClient;
import io.minio.RemoveObjectArgs;
import io.minio.errors.ErrorResponseException;
import io.minio.messages.ErrorResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.SimpleTransactionStatus;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * 删除报告 = 删 MinIO 对象 + 删数据库行（spec §3.1 / §3.4）。
 * 顺序：查行 -> 删对象 -> （失败则入队清理任务 + 删行，同一事务） -> 删行。
 * 查不到（不存在或越权）时对象与行都不动。
 */
@ExtendWith(MockitoExtension.class)
class ReportDeleteWithImageTest {

    private static final Long ME = 7L;
    private static final String BUCKET = "safety-images";
    private static final String OBJECT_KEY = "abc123.png";
    private static final String IMAGE_URL =
            "http://106.53.219.214:9100/safety-images/abc123.png";

    @Mock
    private HazardReportMapper mapper;
    @Mock
    private FileUploadService fileUploadService;
    @Mock
    private ResourceCleanupOutboxService cleanupOutboxService;
    @Mock
    private FileAssetService fileAssetService;
    @Mock
    private PlatformTransactionManager transactionManager;

    private ReportService service;

    @BeforeEach
    void setUp() {
        service = new ReportService(
                mapper, fileUploadService, cleanupOutboxService, fileAssetService, transactionManager);
    }

    @Test
    void deletesMinioObjectBeforeDeletingRow() {
        when(mapper.selectOne(any())).thenReturn(report(1L, ME, OBJECT_KEY, IMAGE_URL));

        service.delete(1L, ME);

        InOrder order = inOrder(fileUploadService, mapper);
        order.verify(fileUploadService).removeObject(OBJECT_KEY);
        order.verify(mapper).deleteById(1L);
        verifyNoInteractions(cleanupOutboxService);
    }

    /** spec §3.4-2：对象已经不存在（FileUploadService 把 NoSuchKey 当成功）时行照删、不产生清理任务。 */
    @Test
    void objectAlreadyGoneIsIdempotentSuccess() throws Exception {
        MinioClient minioClient = mock(MinioClient.class);
        doThrow(clientError("NoSuchKey"))
                .when(minioClient).removeObject(any(RemoveObjectArgs.class));
        FileUploadService realUploadService = new FileUploadService(minioClient, BUCKET);
        ReportService realService = new ReportService(
                mapper, realUploadService, cleanupOutboxService, fileAssetService, transactionManager);
        when(mapper.selectOne(any())).thenReturn(report(1L, ME, OBJECT_KEY, IMAGE_URL));

        realService.delete(1L, ME);

        verify(mapper).deleteById(1L);
        verifyNoInteractions(cleanupOutboxService);
    }

    @Test
    void failedObjectRemovalEnqueuesCleanupTaskAndStillDeletesRow() {
        when(mapper.selectOne(any())).thenReturn(report(1L, ME, OBJECT_KEY, IMAGE_URL));
        when(fileUploadService.bucketName()).thenReturn(BUCKET);
        when(transactionManager.getTransaction(any())).thenReturn(new SimpleTransactionStatus());
        doThrow(new BusinessException(500, "图片删除失败，请重试"))
                .when(fileUploadService).removeObject(OBJECT_KEY);

        service.delete(1L, ME);

        InOrder order = inOrder(cleanupOutboxService, mapper);
        order.verify(cleanupOutboxService)
                .enqueueObjectDelete(BUCKET, OBJECT_KEY, "tb_hazard_report", 1L);
        order.verify(mapper).deleteById(1L);
        verify(transactionManager).commit(any());
    }

    /** 入队失败必须整体回滚：绝不能删行，否则 image_key 丢失、对象永远没人能删。 */
    @Test
    void cleanupEnqueueFailureAbortsRowDeletion() {
        when(mapper.selectOne(any())).thenReturn(report(1L, ME, OBJECT_KEY, IMAGE_URL));
        when(fileUploadService.bucketName()).thenReturn(BUCKET);
        TransactionStatus status = new SimpleTransactionStatus();
        when(transactionManager.getTransaction(any())).thenReturn(status);
        doThrow(new BusinessException(500, "图片删除失败，请重试"))
                .when(fileUploadService).removeObject(OBJECT_KEY);
        doThrow(new IllegalStateException("outbox insert failed"))
                .when(cleanupOutboxService)
                .enqueueObjectDelete(any(), any(), any(), any());

        assertThrows(IllegalStateException.class, () -> service.delete(1L, ME));

        verify(mapper, never()).deleteById(anyLong());
        verify(transactionManager).rollback(status);
    }

    @Test
    void deletingSomeoneElsesReportTouchesNeitherObjectNorRow() {
        when(mapper.selectOne(any())).thenReturn(null);

        service.delete(1L, ME);

        verifyNoInteractions(fileUploadService, cleanupOutboxService);
        verify(mapper, never()).deleteById(anyLong());
    }

    @Test
    void legacyRowWithoutImageKeyResolvesObjectNameFromUrl() {
        when(mapper.selectOne(any())).thenReturn(report(1L, ME, null, IMAGE_URL));

        service.delete(1L, ME);

        verify(fileUploadService).removeObject(OBJECT_KEY);
        verify(mapper).deleteById(1L);
    }

    @Test
    void unresolvableImageUrlStillDeletesRowWithoutCleanupTask() {
        when(mapper.selectOne(any())).thenReturn(report(1L, ME, null, null));

        service.delete(1L, ME);

        verifyNoInteractions(fileUploadService, cleanupOutboxService);
        verify(mapper).deleteById(1L);
    }

    @Test
    void saveStoresOwnedFileAssetAndMarksItAttached() {
        ReportSaveDTO dto = new ReportSaveDTO();
        dto.setFileId(99L);
        dto.setHazardCategory("消防通道占用");
        dto.setRectification(List.of("清理通道"));
        FileAsset asset = new FileAsset();
        asset.setId(99L);
        asset.setUserId(ME);
        asset.setBucket(BUCKET);
        asset.setObjectKey(OBJECT_KEY);
        asset.setStatus(FileAssetService.STATUS_TEMP);
        when(fileAssetService.requireOwned(99L, ME)).thenReturn(asset);
        when(fileAssetService.accessPath(asset)).thenReturn(IMAGE_URL);

        service.save(ME, dto);

        ArgumentCaptor<HazardReport> saved = ArgumentCaptor.forClass(HazardReport.class);
        verify(mapper).insert(saved.capture());
        assertEquals(OBJECT_KEY, saved.getValue().getImageKey());
        assertEquals(IMAGE_URL, saved.getValue().getImageUrl());
        assertEquals(ME, saved.getValue().getUserId());
        verify(fileAssetService).markAttached(99L, ME, FileAssetService.VISIBILITY_PRIVATE);
    }

    @Test
    void saveRejectsLegacyBlobOrArbitraryImageUrl() {
        ReportSaveDTO dto = new ReportSaveDTO();
        dto.setImageUrl("blob:http://localhost/123");

        assertThrows(BusinessException.class, () -> service.save(ME, dto));
        verify(mapper, never()).insert(any(HazardReport.class));
    }

    @Test
    void objectKeyParsingHandlesEdgeCases() {
        assertEquals("abc.png", ReportService.objectKeyOf("http://host:9100/safety-images/abc.png"));
        assertEquals("abc.png", ReportService.objectKeyOf("http://host:9100/safety-images/abc.png?x=1"));
        assertEquals("abc.png", ReportService.objectKeyOf("  http://host/abc.png  "));
        assertNull(ReportService.objectKeyOf(null));
        assertNull(ReportService.objectKeyOf(""));
        assertNull(ReportService.objectKeyOf("http://host:9100/safety-images/"));
        assertNull(ReportService.objectKeyOf("not-a-url"));
        assertNull(ReportService.objectKeyOf("http://host/x/" + "k".repeat(129)));
    }

    private static HazardReport report(Long id, Long userId, String imageKey, String imageUrl) {
        HazardReport row = new HazardReport();
        row.setId(id);
        row.setUserId(userId);
        row.setImageKey(imageKey);
        row.setImageUrl(imageUrl);
        return row;
    }

    private static ErrorResponseException clientError(String code) {
        ErrorResponse errorResponse = mock(ErrorResponse.class);
        when(errorResponse.code()).thenReturn(code);
        ErrorResponseException exception = mock(ErrorResponseException.class);
        when(exception.errorResponse()).thenReturn(errorResponse);
        return exception;
    }
}


