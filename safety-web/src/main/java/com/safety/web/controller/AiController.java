package com.safety.web.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.safety.common.result.R;
import com.safety.web.service.AiService;
import com.safety.web.service.AiStreamBusyException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import org.springframework.security.core.context.SecurityContextHolder;

import jakarta.servlet.http.HttpServletRequest;
import java.io.IOException;
import java.util.Map;
import java.util.stream.Collectors;

@Slf4j
@RestController
@RequestMapping("/api/ai")
public class AiController {

    @Autowired(required = false)
    private AiService aiService;

    @GetMapping("/health")
    public R<String> health() {
        if (aiService == null || !aiService.isHealthy()) {
            return R.fail("AI service unavailable");
        }
        return R.ok("ok");
    }

    @PostMapping(value = "/analyze", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public R<Map<String, Object>> analyze(
            @RequestParam(required = false) MultipartFile file,
            @RequestParam(defaultValue = "请分析这张图片中的安全隐患，并生成报告") String text) {
        if (aiService == null) return R.fail("AI 服务未就绪");
        try {
            Long userId = (Long) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
            return R.ok(aiService.analyze(file, text, userId));
        } catch (Exception e) {
            log.error("AI 分析失败", e);
            return R.fail("AI 分析失败: " + e.getMessage());
        }
    }

    @PostMapping(value = "/analyze/stream", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public SseEmitter analyzeStream(
            @RequestParam(required = false) MultipartFile file,
            @RequestParam(defaultValue = "请分析这张图片中的安全隐患，并生成报告") String text) {
        if (aiService == null) {
            SseEmitter e = new SseEmitter();
            e.completeWithError(new RuntimeException("AI 服务未就绪"));
            return e;
        }
        try {
            Long userId = (Long) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
            return aiService.analyzeStream(file, text, userId);
        } catch (AiStreamBusyException e) {
            throw e;
        } catch (Exception e) {
            SseEmitter emitter = new SseEmitter();
            emitter.completeWithError(e);
            return emitter;
        }
    }

    @PostMapping(value = "/assistant/stream")
    public SseEmitter assistantStream(
            HttpServletRequest request,
            @RequestParam(value = "message", required = false) String messageParam,
            @RequestParam(value = "session_id", required = false) String sessionIdParam,
            @RequestParam(value = "selected_major_code", required = false) String selectedMajorCodeParam,
            @RequestParam(value = "file", required = false) MultipartFile file) throws IOException {
        if (aiService == null) {
            SseEmitter e = new SseEmitter();
            e.completeWithError(new RuntimeException("AI 服务未就绪"));
            return e;
        }
        String message = messageParam;
        String sessionId = sessionIdParam;
        String selectedMajorCode = selectedMajorCodeParam;

        String ct = request.getContentType();
        if (ct != null && ct.contains("application/json")) {
            try {
                String body = request.getReader().lines().collect(Collectors.joining(System.lineSeparator()));
                if (body != null && !body.isBlank()) {
                    ObjectMapper mapper = new ObjectMapper();
                    Map map = mapper.readValue(body, Map.class);
                    Object m = map.get("message");
                    Object s = map.get("session_id");
                    if (s == null) s = map.get("sessionId");
                    Object major = map.get("selected_major_code");
                    if (major == null) major = map.get("selectedMajorCode");
                    if (m != null) message = String.valueOf(m);
                    if (s != null) sessionId = String.valueOf(s);
                    if (major != null) selectedMajorCode = String.valueOf(major);
                }
            } catch (Exception ignored) {}
        }

        if (message == null) message = "";
        if (sessionId == null) sessionId = "";

        Long userId = (Long) SecurityContextHolder.getContext().getAuthentication().getPrincipal();
        if (file != null && !file.isEmpty()) {
            return aiService.assistantStream(message, sessionId, userId, selectedMajorCode, file);
        } else {
            return aiService.assistantStream(message, sessionId, userId, selectedMajorCode);
        }
    }

    @GetMapping("/history")
    public R<Map<String, Object>> history(@RequestParam String sessionId) {
        if (aiService == null) return R.fail("AI 服务未就绪");
        return R.ok(aiService.getHistory(sessionId));
    }

    @DeleteMapping("/session")
    public R<Void> clearSession(@RequestParam String sessionId) {
        if (aiService == null) return R.fail("AI 服务未就绪");
        aiService.clearSession(sessionId);
        return R.ok();
    }
}
