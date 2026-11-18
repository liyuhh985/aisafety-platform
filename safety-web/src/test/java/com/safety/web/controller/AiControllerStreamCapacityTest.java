package com.safety.web.controller;

import com.safety.web.service.AiService;
import com.safety.web.service.AiStreamBusyException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.lang.reflect.Field;
import java.util.Collections;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AiControllerStreamCapacityTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void analyzeStreamMapsCapacityRejectionToTooManyRequests() throws Exception {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(1L, null, Collections.emptyList()));
        AiController controller = controllerWith(new BusyAiService());

        AiStreamBusyException exception = assertThrows(
                AiStreamBusyException.class,
                () -> controller.analyzeStream(null, "test"));

        assertEquals("当前服务繁忙，请稍后重试", exception.getMessage());
    }

    private static AiController controllerWith(AiService aiService) throws Exception {
        AiController controller = new AiController();
        Field field = AiController.class.getDeclaredField("aiService");
        field.setAccessible(true);
        field.set(controller, aiService);
        return controller;
    }

    private static final class BusyAiService extends AiService {
        @Override
        public SseEmitter analyzeStream(org.springframework.web.multipart.MultipartFile file, String text, Long userId) {
            throw new AiStreamBusyException();
        }

    }
}
