package com.safety.web.service;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.client.HttpClientErrorException;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import jakarta.annotation.PreDestroy;
import java.io.IOException;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import lombok.extern.slf4j.Slf4j;

/**
 * 调用 Python AI 模块的 HTTP 客户端。
 * Python 服务启动: cd ai-module && python server.py (端口 8000)
 */
@Slf4j
@Service
public class AiService {

    private static final String DEFAULT_AI_BASE = "http://127.0.0.1:8000/api/ai";

    private final RestTemplate rest;
    @Value("${ai.base-url:" + DEFAULT_AI_BASE + "}")
    private String aiBase;
    @Value("${ai.internal-token:}")
    private String internalToken;
    private final ExecutorService streamExecutor;

    public AiService() {
        this(createRestTemplate(), DEFAULT_AI_BASE, "", createStreamExecutor());
    }

    AiService(RestTemplate rest, String aiBase, String internalToken) {
        this(rest, aiBase, internalToken, createStreamExecutor());
    }

    AiService(RestTemplate rest, String aiBase, String internalToken,
              ExecutorService streamExecutor) {
        this.rest = rest;
        this.aiBase = aiBase;
        this.internalToken = internalToken;
        this.streamExecutor = streamExecutor;
    }

    private static ThreadPoolExecutor createStreamExecutor() {
        return new ThreadPoolExecutor(
                8,
                8,
                0L,
                TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(32),
                new ThreadPoolExecutor.AbortPolicy());
    }

    private Future<?> submitStreamTask(Runnable task) {
        try {
            return streamExecutor.submit(task);
        } catch (RejectedExecutionException e) {
            throw new AiStreamBusyException(e);
        }
    }

    private static RestTemplate createRestTemplate() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(10_000);
        factory.setReadTimeout(180_000);
        return new RestTemplate(factory);
    }

    @PreDestroy
    void shutdown() {
        streamExecutor.shutdown();
    }

    /**
     * 完整分析（非流式），返回 JSON。
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> analyze(MultipartFile file, String text, Long userId) throws IOException {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("text", text != null ? text : "请分析这张图片中的安全隐患，并生成报告");
        if (userId != null) {
            body.add("user_id", String.valueOf(userId));
        }
        if (file != null && !file.isEmpty()) {
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() { return file.getOriginalFilename(); }
            });
        }
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);
        HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);

        ResponseEntity<Map> response = rest.postForEntity(
                aiBase + "/analyze", request, Map.class);
        return response.getBody();
    }

    /**
     * SSE 流式分析，返回 SseEmitter 供 Controller 直接推给前端。
     */
    public SseEmitter analyzeStream(MultipartFile file, String text, Long userId) throws IOException {
        SseEmitter emitter = new SseEmitter(300_000L);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("text", text != null ? text : "请分析这张图片中的安全隐患，并生成报告");
        if (userId != null) {
            body.add("user_id", String.valueOf(userId));
        }
        if (file != null && !file.isEmpty()) {
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() { return file.getOriginalFilename(); }
            });
        }

        final MultiValueMap<String, Object> finalBody = body;
        StreamCancellation cancellation = new StreamCancellation();
        emitter.onCompletion(cancellation::cancel);
        emitter.onTimeout(cancellation::cancel);
        emitter.onError(error -> cancellation.cancel());

        Future<?> future = submitStreamTask(() -> {
            try {
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.MULTIPART_FORM_DATA);
                HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(finalBody, headers);

                rest.execute(
                        aiBase + "/analyze/stream",
                        HttpMethod.POST,
                        req -> {
                            req.getHeaders().setContentType(MediaType.MULTIPART_FORM_DATA);
                            new org.springframework.http.converter.FormHttpMessageConverter()
                                    .write(finalBody, MediaType.MULTIPART_FORM_DATA, req);
                        },
                        resp -> {
                            cancellation.setUpstreamCloser(resp::close);
                            try (var reader = new java.io.BufferedReader(
                                    new java.io.InputStreamReader(resp.getBody()))) {
                                String line;
                                while ((line = reader.readLine()) != null) {
                                    if (cancellation.isCancelled()) {
                                        return null;
                                    }
                                    if (line.startsWith("data: ")) {
                                        emitter.send(SseEmitter.event().data(line.substring(6)));
                                    }
                                }
                            }
                            cancellation.clearUpstreamCloser();
                            if (!cancellation.isCancelled()) {
                                cancellation.finish();
                                emitter.complete();
                            }
                            return null;
                        }
                );
            } catch (Exception e) {
                if (!cancellation.isCancelled()) {
                    cancellation.finish();
                    try { emitter.completeWithError(e); } catch (Exception ignored) {}
                }
            }
        });
        cancellation.setFuture(future);

        return emitter;
    }

    /**
     * AI 助手 ReAct SSE 流式多轮问答（JSON body）。
     */
    public SseEmitter assistantStream(String message, String sessionId, Long userId) {
        return assistantStream(message, sessionId, userId, "", "");
    }

    /**
     * AI 助手 ReAct SSE 流式多轮问答（JSON body），带前端大类提示。
     */
    public SseEmitter assistantStream(String message, String sessionId, Long userId,
                                      String selectedMajorCode, String interruptReply) {
        SseEmitter emitter = new SseEmitter(300_000L);

        String body = String.format(
                "{\"message\":\"%s\",\"session_id\":\"%s\",\"user_id\":%s,\"selected_major_code\":\"%s\",\"interrupt_reply\":\"%s\"}",
                message == null ? "" : message.replace("\"", "\\\""),
                sessionId == null ? "" : sessionId,
                userId == null ? "null" : userId.toString(),
                selectedMajorCode == null ? "" : selectedMajorCode.replace("\"", "\\\""),
                interruptReply == null ? "" : interruptReply.replace("\"", "\\\""));

        final String finalBody = body;
        StreamCancellation cancellation = new StreamCancellation();
        emitter.onCompletion(cancellation::cancel);
        emitter.onTimeout(cancellation::cancel);
        emitter.onError(error -> cancellation.cancel());

        Future<?> future = submitStreamTask(() -> {
            try {
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.APPLICATION_JSON);
                if (internalToken != null && !internalToken.isEmpty()) {
                    headers.set("X-Internal-Token", internalToken);
                }
                HttpEntity<String> request = new HttpEntity<>(finalBody, headers);

                rest.execute(
                        aiBase + "/assistant/stream",
                        HttpMethod.POST,
                        req -> {
                            req.getHeaders().setContentType(MediaType.APPLICATION_JSON);
                            req.getHeaders().setAccept(java.util.Collections.singletonList(MediaType.TEXT_EVENT_STREAM));

                            var bytes = finalBody.getBytes(java.nio.charset.StandardCharsets.UTF_8);
                            req.getBody().write(bytes);
                        },
                        resp -> {
                            cancellation.setUpstreamCloser(resp::close);
                            try (var reader = new java.io.BufferedReader(
                                    new java.io.InputStreamReader(resp.getBody()))) {
                                String line;
                                while ((line = reader.readLine()) != null) {
                                    if (cancellation.isCancelled()) {
                                        return null;
                                    }
                                    if (line.startsWith("data: ")) {
                                        emitter.send(SseEmitter.event().data(line.substring(6)));
                                    }
                                }
                            }
                            cancellation.clearUpstreamCloser();
                            if (!cancellation.isCancelled()) {
                                cancellation.finish();
                                emitter.complete();
                            }
                            return null;
                        }
                );
            } catch (Exception e) {
                if (!cancellation.isCancelled()) {
                    cancellation.finish();
                    try { emitter.completeWithError(e); } catch (Exception ignored) {}
                }
            }
        });
        cancellation.setFuture(future);

        return emitter;
    }
        /**
     * AI 助手 ReAct SSE 流式多轮问答（multipart，有图时用）。
     */
    public SseEmitter assistantStream(String message, String sessionId, Long userId, MultipartFile file) throws IOException {
        return assistantStream(message, sessionId, userId, "", file);
    }

    /**
     * AI 助手 ReAct SSE 流式多轮问答（multipart，有图时用），带前端大类提示。
     */
    public SseEmitter assistantStream(String message, String sessionId, Long userId,
                                      String selectedMajorCode, MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            return assistantStream(message, sessionId, userId, selectedMajorCode, "");
        }
        SseEmitter emitter = new SseEmitter(300_000L);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("message", message == null ? "" : message);
        body.add("session_id", sessionId == null ? "" : sessionId);
        body.add("user_id", userId);
        body.add("selected_major_code", selectedMajorCode == null ? "" : selectedMajorCode);
        body.add("file", new ByteArrayResource(file.getBytes()) {
            @Override public String getFilename() { return file.getOriginalFilename(); }
        });

        final MultiValueMap<String, Object> finalBody = body;
        StreamCancellation cancellation = new StreamCancellation();
        emitter.onCompletion(cancellation::cancel);
        emitter.onTimeout(cancellation::cancel);
        emitter.onError(error -> cancellation.cancel());

        Future<?> future = submitStreamTask(() -> {
            try {
                rest.execute(
                        aiBase + "/assistant/stream",
                        HttpMethod.POST,
                        req -> {
                            req.getHeaders().setContentType(MediaType.MULTIPART_FORM_DATA);
                            new org.springframework.http.converter.FormHttpMessageConverter()
                                    .write(finalBody, MediaType.MULTIPART_FORM_DATA, req);
                        },
                        resp -> {
                            cancellation.setUpstreamCloser(resp::close);
                            try (var reader = new java.io.BufferedReader(
                                    new java.io.InputStreamReader(resp.getBody()))) {
                                String line;
                                while ((line = reader.readLine()) != null) {
                                    if (cancellation.isCancelled()) {
                                        return null;
                                    }
                                    if (line.startsWith("data: ")) {
                                        emitter.send(SseEmitter.event().data(line.substring(6)));
                                    }
                                }
                            }
                            cancellation.clearUpstreamCloser();
                            if (!cancellation.isCancelled()) {
                                cancellation.finish();
                                emitter.complete();
                            }
                            return null;
                        }
                );
            } catch (Exception e) {
                if (!cancellation.isCancelled()) {
                    cancellation.finish();
                    try { emitter.completeWithError(e); } catch (Exception ignored) {}
                }
            }
        });
        cancellation.setFuture(future);

        return emitter;
    }

/** 获取会话历史 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getHistory(String sessionId) {
        return rest.getForObject(
                aiBase + "/history?session_id=" + sessionId, Map.class);
    }

    /** 清除会话 */
    public void clearSession(String sessionId) {
        rest.delete(aiBase + "/session?session_id=" + sessionId);
    }

    private static final class StreamCancellation {
        private final AtomicBoolean cancelled = new AtomicBoolean();
        private final AtomicBoolean finished = new AtomicBoolean();
        private final AtomicReference<Future<?>> future = new AtomicReference<>();
        private final AtomicReference<Runnable> upstreamCloser = new AtomicReference<>();

        void cancel() {
            if (!cancelled.compareAndSet(false, true) || finished.get()) {
                return;
            }
            Runnable closer = upstreamCloser.getAndSet(null);
            if (closer != null) {
                try {
                    closer.run();
                } catch (Exception ignored) {
                }
            }
            Future<?> task = future.get();
            if (task != null) {
                task.cancel(true);
            }
        }

        void setFuture(Future<?> task) {
            future.set(task);
            if (cancelled.get()) {
                task.cancel(true);
            }
        }

        void setUpstreamCloser(Runnable closer) {
            upstreamCloser.set(closer);
            if (cancelled.get()) {
                Runnable active = upstreamCloser.getAndSet(null);
                if (active != null) {
                    try {
                        active.run();
                    } catch (Exception ignored) {
                    }
                }
            }
        }

        void clearUpstreamCloser() {
            upstreamCloser.set(null);
        }

        boolean isCancelled() {
            return cancelled.get();
        }

        void finish() {
            finished.set(true);
            upstreamCloser.set(null);
        }
    }

    public void deleteVectors(String sourceTable, List<Long> ids) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);
        headers.set("X-Internal-Token", internalToken);
        HttpEntity<Map<String, Object>> request = new HttpEntity<>(
                Map.of("table", sourceTable, "ids", ids), headers);
        try {
            rest.postForEntity(
                    aiBase + "/internal/vectors/delete", request, Map.class);
        } catch (HttpClientErrorException e) {
            int status = e.getStatusCode().value();
            // 请求本身没救的 4xx（表名非法 / 路径不存在 / 方法不对 / 参数错 / 冲突）→ 永久失败，重试无意义
            if (status == 400 || status == 404 || status == 405 || status == 409 || status == 422) {
                throw new VectorSyncPermanentException(
                        "Python AI rejected vector delete request: HTTP " + status);
            }
            // 401/403：内部 token 或权限问题 —— 运维修好配置后**同一个请求就能通**，所以必须可重试；
            // 同时打 ALERT 级别的日志（当前没有告警基础设施，先用 error 日志 + 重试到上限后转 FAILED 兜住）。
            if (status == 401 || status == 403) {
                log.error("[ALERT] vector delete unauthorized, HTTP {} — 需人工介入（内部 token/权限）；"
                        + "任务会按退避重试，达上限（10 次）后转为 FAILED", status);
            }
            // 429 限流 + 401/403 + 其他 4xx → 交回 worker 按可重试处理
            throw e;
        }
    }

    /** 健康检查 */
    public boolean isHealthy() {
        try {
            ResponseEntity<Map> resp = rest.getForEntity(aiBase + "/health", Map.class);
            return resp.getStatusCode().is2xxSuccessful();
        } catch (RestClientException e) {
            return false;
        }
    }
}



