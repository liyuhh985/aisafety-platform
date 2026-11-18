package com.safety.web.service;

import com.safety.pojo.entity.VectorSyncOutbox;
import com.safety.service.service.VectorSyncOutboxService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withException;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import org.springframework.http.HttpStatus;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.io.IOException;
import java.util.List;

import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class VectorDeleteOutboxWorkerTest {

    @Mock
    private VectorSyncOutboxService outboxService;
    @Mock
    private AiService aiService;

    private VectorDeleteOutboxWorker worker;

    @BeforeEach
    void setUp() {
        worker = new VectorDeleteOutboxWorker(outboxService, aiService, 50);
    }

    @Test
    void unclaimedTaskIsNotDelivered() {
        VectorSyncOutbox task = task(1L, "tb_hazard_case", 42L, 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(null);

        worker.processPendingDeletes();

        verifyNoInteractions(aiService);
        verify(outboxService, never()).markSucceeded(
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyInt());
    }

    @Test
    void successfulDeliveryMarksTaskSucceeded() {
        VectorSyncOutbox task = task(1L, "tb_hazard_case", 42L, 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);

        worker.processPendingDeletes();

        verify(aiService).deleteVectors("tb_hazard_case", List.of(42L));
        verify(outboxService).markSucceeded(1L, 1);
    }

    @Test
    void permanentFailureMarksTaskFailed() {
        VectorSyncOutbox task = task(1L, "tb_regulation", 7L, 2);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);
        doThrow(new VectorSyncPermanentException("bad token"))
                .when(aiService).deleteVectors("tb_regulation", List.of(7L));

        worker.processPendingDeletes();

        verify(outboxService).markFailed(1L, 1, "bad token");
        verify(outboxService, never()).markRetry(
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyString());
    }

    @Test
    void transientFailureRetriesAndDoesNotBlockNextTask() {
        VectorSyncOutbox failed = task(1L, "tb_hazard_case", 42L, 3);
        VectorSyncOutbox succeeded = task(2L, "tb_hazard_knowledge", 43L, 0);
        when(outboxService.findClaimable(50)).thenReturn(List.of(failed, succeeded));
        when(outboxService.claim(failed)).thenReturn(1);
        when(outboxService.claim(succeeded)).thenReturn(1);
        doThrow(new RestClientException("network down"))
                .when(aiService).deleteVectors("tb_hazard_case", List.of(42L));

        worker.processPendingDeletes();

        verify(outboxService).markRetry(1L, 1, 3, "RestClientException");
        verify(aiService).deleteVectors("tb_hazard_knowledge", List.of(43L));
        verify(outboxService).markSucceeded(2L, 1);
    }

    @Test
    void clientErrorFromPythonMarksTaskFailedInsteadOfRetrying() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        // 用真实的 AiService：覆盖的是 "HTTP 4xx -> 永久失败" 这条映射，
        // 而不只是 worker 对 VectorSyncPermanentException 的反应。
        VectorDeleteOutboxWorker realWorker = new VectorDeleteOutboxWorker(
                outboxService,
                new AiService(restTemplate, "http://python-ai:8000/api/ai", "shared-token"),
                50);
        VectorSyncOutbox task = task(1L, "tb_hazard_case", 42L, 3);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);
        server.expect(requestTo("http://python-ai:8000/api/ai/internal/vectors/delete"))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        realWorker.processPendingDeletes();

        verify(outboxService).markFailed(eq(1L), eq(1), anyString());
        verify(outboxService, never()).markRetry(
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyString());
        server.verify();
    }

    @Test
    void transportFailureRetriesTask() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        VectorDeleteOutboxWorker realWorker = new VectorDeleteOutboxWorker(
                outboxService,
                new AiService(restTemplate, "http://python-ai:8000/api/ai", "shared-token"),
                50);
        VectorSyncOutbox task = task(1L, "tb_regulation", 7L, 4);
        when(outboxService.findClaimable(50)).thenReturn(List.of(task));
        when(outboxService.claim(task)).thenReturn(1);
        server.expect(requestTo("http://python-ai:8000/api/ai/internal/vectors/delete"))
                .andRespond(withException(new IOException("read timed out")));

        realWorker.processPendingDeletes();

        verify(outboxService).markRetry(eq(1L), eq(1), eq(4), anyString());
        verify(outboxService, never()).markFailed(
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyString());
        server.verify();
    }

    private static VectorSyncOutbox task(
            Long id, String sourceTable, Long docId, int retryCount) {
        VectorSyncOutbox task = new VectorSyncOutbox();
        task.setId(id);
        task.setSourceTable(sourceTable);
        task.setDocId(docId);
        task.setClaimVersion(0);
        task.setRetryCount(retryCount);
        return task;
    }
}
