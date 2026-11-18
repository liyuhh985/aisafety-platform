package com.safety.web.service;

import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.web.client.RestTemplate;

import java.lang.reflect.Field;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.function.Consumer;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;

class AiServiceStreamCancellationTest {

    @Test
    void registersAllEmitterCallbacksAndCancelsStreamFuture() throws Exception {
        RestTemplate rest = mock(RestTemplate.class);
        ExecutorService executor = mock(ExecutorService.class);
        Future<?> analyzeFuture = mock(Future.class);
        doReturn(analyzeFuture)
                .when(executor).submit(any(Runnable.class));

        AiService service = new AiService(rest, "http://python", "shared-token", executor);
        SseEmitter analyze = service.analyzeStream(null, "test", 1L);

        assertCallbacksRegistered(analyze);

        invokeCallbacks(analyze, "timeoutCallback", null);

        verify(analyzeFuture).cancel(true);
    }

    private static void assertCallbacksRegistered(SseEmitter emitter) throws Exception {
        assertFalse(callback(emitter, "completionCallback") == null);
        assertFalse(callback(emitter, "timeoutCallback") == null);
        assertFalse(callback(emitter, "errorCallback") == null);
    }

    @SuppressWarnings("unchecked")
    private static void invokeCallbacks(SseEmitter emitter, String fieldName, Throwable error)
            throws Exception {
        Object callback = callback(emitter, fieldName);
        if (callback instanceof Runnable runnable) {
            runnable.run();
        } else {
            ((Consumer<Throwable>) callback).accept(error);
        }
    }

    private static Object callback(SseEmitter emitter, String fieldName) throws Exception {
        Field field = ResponseBodyEmitter.class.getDeclaredField(fieldName);
        field.setAccessible(true);
        return field.get(emitter);
    }
}