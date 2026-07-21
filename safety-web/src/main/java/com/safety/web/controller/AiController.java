package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.service.service.AiService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;

@Slf4j
@RestController
@RequestMapping("/api/ai")
@RequiredArgsConstructor
public class AiController {

    private final AiService aiService;

    /** 完整分析（非流式 JSON） */
    @PostMapping(value = "/analyze", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public R<Map<String, Object>> analyze(
            @RequestParam(required = false) MultipartFile file,
            @RequestParam(defaultValue = "请分析这张图片中的安全隐患，并生成报告") String text) {
        try {
            Map<String, Object> result = aiService.analyze(file, text);
            return R.ok(result);
        } catch (Exception e) {
            log.error("AI 分析失败", e);
            return R.fail("AI 分析失败: " + e.getMessage());
        }
    }

    /** SSE 流式分析报告 */
    @PostMapping(value = "/analyze/stream", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public SseEmitter analyzeStream(
            @RequestParam(required = false) MultipartFile file,
            @RequestParam(defaultValue = "请分析这张图片中的安全隐患，并生成报告") String text) {
        try {
            return aiService.analyzeStream(file, text);
        } catch (Exception e) {
            log.error("AI 流式分析失败", e);
            SseEmitter emitter = new SseEmitter();
            emitter.completeWithError(e);
            return emitter;
        }
    }

    /** 多轮对话 */
    @PostMapping("/chat")
    public R<Map<String, Object>> chat(
            @RequestParam String message,
            @RequestParam String sessionId) {
        try {
            return R.ok(aiService.chat(message, sessionId));
        } catch (Exception e) {
            return R.fail(e.getMessage());
        }
    }

    /** 多轮对话（流式） */
    @PostMapping("/chat/stream")
    public SseEmitter chatStream(
            @RequestParam String message,
            @RequestParam String sessionId) {
        try {
            return aiService.chatStream(message, sessionId);
        } catch (Exception e) {
            SseEmitter emitter = new SseEmitter();
            emitter.completeWithError(e);
            return emitter;
        }
    }

    /** 会话历史 */
    @GetMapping("/history")
    public R<Map<String, Object>> history(@RequestParam String sessionId) {
        return R.ok(aiService.getHistory(sessionId));
    }

    /** 清除会话 */
    @DeleteMapping("/session")
    public R<Void> clearSession(@RequestParam String sessionId) {
        aiService.clearSession(sessionId);
        return R.ok();
    }
}
