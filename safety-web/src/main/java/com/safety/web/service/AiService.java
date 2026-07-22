package com.safety.web.service;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.Map;

/**
 * 调用 Python AI 模块的 HTTP 客户端。
 * Python 服务启动: cd ai-module && python server.py (端口 8000)
 */
@Service
public class AiService {

    private static final String AI_BASE = "http://127.0.0.1:8000/api/ai";

    private final RestTemplate rest = new RestTemplate();

    /**
     * 完整分析（非流式），返回 JSON。
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> analyze(MultipartFile file, String text) throws IOException {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("text", text != null ? text : "请分析这张图片中的安全隐患，并生成报告");
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
                AI_BASE + "/analyze", request, Map.class);
        return response.getBody();
    }

    /**
     * SSE 流式分析，返回 SseEmitter 供 Controller 直接推给前端。
     */
    public SseEmitter analyzeStream(MultipartFile file, String text) throws IOException {
        SseEmitter emitter = new SseEmitter(300_000L);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("text", text != null ? text : "请分析这张图片中的安全隐患，并生成报告");
        if (file != null && !file.isEmpty()) {
            body.add("file", new ByteArrayResource(file.getBytes()) {
                @Override
                public String getFilename() { return file.getOriginalFilename(); }
            });
        }

        final MultiValueMap<String, Object> finalBody = body;

        new Thread(() -> {
            try {
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.MULTIPART_FORM_DATA);
                HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(finalBody, headers);

                rest.execute(
                        AI_BASE + "/analyze/stream",
                        HttpMethod.POST,
                        req -> {
                            // 用 FormHttpMessageConverter 写 multipart body
                            new org.springframework.http.converter.FormHttpMessageConverter()
                                    .write(finalBody, MediaType.MULTIPART_FORM_DATA, req);
                        },
                        resp -> {
                            try (var reader = new java.io.BufferedReader(
                                    new java.io.InputStreamReader(resp.getBody()))) {
                                String line;
                                while ((line = reader.readLine()) != null) {
                                    if (!line.isEmpty()) {
                                        emitter.send(SseEmitter.event().data(line));
                                    }
                                }
                            }
                            emitter.complete();
                            return null;
                        }
                );
            } catch (Exception e) {
                try { emitter.completeWithError(e); } catch (Exception ignored) {}
            }
        }).start();

        return emitter;
    }

    /**
     * 多轮对话（非流式）。
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> chat(String message, String sessionId) {
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("message", message);
        body.add("session_id", sessionId);
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
        HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);

        ResponseEntity<Map> response = rest.postForEntity(
                AI_BASE + "/chat", request, Map.class);
        return response.getBody();
    }

    /**
     * 多轮对话（SSE 流式）。
     */
    public SseEmitter chatStream(String message, String sessionId) {
        SseEmitter emitter = new SseEmitter(300_000L);

        new Thread(() -> {
            try {
                MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
                body.add("message", message);
                body.add("session_id", sessionId);
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.APPLICATION_FORM_URLENCODED);
                HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);

                rest.execute(
                        AI_BASE + "/chat/stream", HttpMethod.POST,
                        req -> headers.forEach((k, v) -> req.getHeaders().addAll(k, v)),
                        response -> {
                            try (var reader = new java.io.BufferedReader(
                                    new java.io.InputStreamReader(response.getBody()))) {
                                String line;
                                while ((line = reader.readLine()) != null) {
                                    if (!line.isEmpty()) {
                                        emitter.send(SseEmitter.event().data(line));
                                    }
                                }
                            }
                            emitter.complete();
                            return null;
                        });
            } catch (Exception e) {
                try { emitter.completeWithError(e); } catch (Exception ignored) {}
            }
        }).start();

        return emitter;
    }

    /** 获取会话历史 */
    @SuppressWarnings("unchecked")
    public Map<String, Object> getHistory(String sessionId) {
        return rest.getForObject(
                AI_BASE + "/history?session_id=" + sessionId, Map.class);
    }

    /** 清除会话 */
    public void clearSession(String sessionId) {
        rest.delete(AI_BASE + "/session?session_id=" + sessionId);
    }

    /** 健康检查 */
    public boolean isHealthy() {
        try {
            ResponseEntity<Map> resp = rest.getForEntity(AI_BASE + "/health", Map.class);
            return resp.getStatusCode().is2xxSuccessful();
        } catch (RestClientException e) {
            return false;
        }
    }
}
