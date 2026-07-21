package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.web.service.AiService;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/ai")
public class AiController {

    @Autowired(required = false)
    private AiService aiService;

    @GetMapping("/health")
    public R<String> health() {
        return R.ok("ok");
    }

    @PostMapping(value = "/analyze", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public R<Map<String, Object>> analyze(
            @RequestParam(required = false) MultipartFile file,
            @RequestParam(defaultValue = "请分析这张图片中的安全隐患，并生成报告") String text) {
        if (aiService == null) return R.fail("AI 服务未就绪");
        try {
            return R.ok(aiService.analyze(file, text));
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
            return aiService.analyzeStream(file, text);
        } catch (Exception e) {
            SseEmitter emitter = new SseEmitter();
            emitter.completeWithError(e);
            return emitter;
        }
    }

    @PostMapping("/chat")
    public R<Map<String, Object>> chat(
            @RequestParam String message,
            @RequestParam String sessionId) {
        if (aiService == null) return R.fail("AI 服务未就绪");
        try {
            return R.ok(aiService.chat(message, sessionId));
        } catch (Exception e) {
            return R.fail(e.getMessage());
        }
    }

    @PostMapping("/chat/stream")
    public SseEmitter chatStream(
            @RequestParam String message,
            @RequestParam String sessionId) {
        if (aiService == null) {
            SseEmitter e = new SseEmitter();
            e.completeWithError(new RuntimeException("AI 服务未就绪"));
            return e;
        }
        try {
            return aiService.chatStream(message, sessionId);
        } catch (Exception e) {
            SseEmitter emitter = new SseEmitter();
            emitter.completeWithError(e);
            return emitter;
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
