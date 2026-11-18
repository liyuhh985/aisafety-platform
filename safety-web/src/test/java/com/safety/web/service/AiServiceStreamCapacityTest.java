package com.safety.web.service;

import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestTemplate;

import java.lang.reflect.Field;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

class AiServiceStreamCapacityTest {

    @Test
    void defaultStreamExecutorUsesBoundedQueueAndAbortPolicy() throws Exception {
        AiService service = new AiService();
        try {
            Field field = AiService.class.getDeclaredField("streamExecutor");
            field.setAccessible(true);
            ThreadPoolExecutor executor = assertInstanceOf(
                    ThreadPoolExecutor.class, field.get(service));

            assertEquals(8, executor.getCorePoolSize());
            assertEquals(8, executor.getMaximumPoolSize());
            assertEquals(32, ((ArrayBlockingQueue<?>) executor.getQueue()).remainingCapacity());
            assertInstanceOf(ThreadPoolExecutor.AbortPolicy.class, executor.getRejectedExecutionHandler());
        } finally {
            service.shutdown();
        }
    }

    @Test
    void analyzeStreamReportsBusyWhenWorkerSubmissionIsRejected() {
        ExecutorService executor = mock(ExecutorService.class);
        doThrow(new RejectedExecutionException()).when(executor).submit(org.mockito.ArgumentMatchers.any(Runnable.class));
        AiService service = new AiService(mock(RestTemplate.class), "http://python", "shared-token", executor);

        assertThrows(AiStreamBusyException.class, () -> service.analyzeStream(null, "test", 1L));
    }

}
