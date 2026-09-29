package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import io.minio.MinioClient;
import io.minio.RemoveObjectArgs;
import io.minio.errors.ErrorResponseException;
import io.minio.messages.ErrorResponse;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.io.IOException;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

/**
 * removeObject 的对象不存在语义（spec §3.2-1 / §3.4-2）：
 *   · NoSuchKey / NoSuchBucket -> 静默成功（幂等，重复删不报错）
 *   · 其他 S3 错误 / IO 异常   -> 抛 BusinessException(500)，由调用方转清理任务
 */
@ExtendWith(MockitoExtension.class)
class FileUploadServiceRemoveObjectTest {

    private static final String BUCKET = "safety-images";

    @Mock
    private MinioClient minioClient;

    private FileUploadService service;

    @BeforeEach
    void setUp() {
        service = new FileUploadService(minioClient, BUCKET);
    }

    @Test
    void deletesObjectFromConfiguredBucket() throws Exception {
        service.removeObject("abc123.png");

        ArgumentCaptor<RemoveObjectArgs> args = ArgumentCaptor.forClass(RemoveObjectArgs.class);
        verify(minioClient).removeObject(args.capture());
        assertEquals(BUCKET, args.getValue().bucket());
        assertEquals("abc123.png", args.getValue().object());
    }

    @Test
    void explicitBucketWinsOverConfiguredOne() throws Exception {
        service.removeObject("other-bucket", "abc123.png");

        ArgumentCaptor<RemoveObjectArgs> args = ArgumentCaptor.forClass(RemoveObjectArgs.class);
        verify(minioClient).removeObject(args.capture());
        assertEquals("other-bucket", args.getValue().bucket());
    }

    @Test
    void objectAlreadyGoneIsSilentSuccess() throws Exception {
        doThrow(clientError("NoSuchKey"))
                .when(minioClient).removeObject(any(RemoveObjectArgs.class));

        assertDoesNotThrow(() -> service.removeObject("gone.png"));
    }

    @Test
    void missingBucketIsAlsoSilentSuccess() throws Exception {
        doThrow(clientError("NoSuchBucket"))
                .when(minioClient).removeObject(any(RemoveObjectArgs.class));

        assertDoesNotThrow(() -> service.removeObject("abc123.png"));
    }

    @Test
    void accessDeniedBecomesBusinessFailure() throws Exception {
        doThrow(clientError("AccessDenied"))
                .when(minioClient).removeObject(any(RemoveObjectArgs.class));

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.removeObject("abc123.png"));

        assertEquals(500, e.getCode());
    }

    @Test
    void ioFailureBecomesBusinessFailure() throws Exception {
        doThrow(new IOException("connection reset"))
                .when(minioClient).removeObject(any(RemoveObjectArgs.class));

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.removeObject("abc123.png"));

        assertEquals(500, e.getCode());
    }

    @Test
    void blankObjectNameIsRejectedBeforeCallingMinio() {
        BusinessException e = assertThrows(BusinessException.class,
                () -> service.removeObject("   "));

        assertEquals(500, e.getCode());
        verifyNoInteractions(minioClient);
    }

    private static ErrorResponseException clientError(String code) {
        ErrorResponse errorResponse = mock(ErrorResponse.class);
        when(errorResponse.code()).thenReturn(code);
        ErrorResponseException exception = mock(ErrorResponseException.class);
        when(exception.errorResponse()).thenReturn(errorResponse);
        return exception;
    }
}
