package com.safety.web.controller;

import com.safety.pojo.vo.FileUploadVO;
import com.safety.service.service.FileUploadService;
import com.safety.web.service.AiService;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.lang.reflect.Field;
import java.util.Collections;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AiControllerImagePassthroughTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void assistantUploadUsesOwnedImageUrlAndFileId() throws Exception {
        AiService aiService = mock(AiService.class);
        FileUploadService fileUploadService = mock(FileUploadService.class);
        HttpServletRequest request = mock(HttpServletRequest.class);
        HttpServletResponse response = mock(HttpServletResponse.class);
        MockMultipartFile file = new MockMultipartFile(
                "file", "scene.png", "image/png", new byte[]{1, 2, 3});
        FileUploadVO upload = FileUploadVO.builder()
                .fileId(9L).objectKey("scene.png").url("/api/files/9").build();
        when(request.getContentType()).thenReturn("multipart/form-data");
        when(fileUploadService.upload(42L, file)).thenReturn(upload);
        when(aiService.assistantStream("", "s-1", 42L, "", file,
                "/api/files/9", 9L)).thenReturn(new SseEmitter());

        AiController controller = controllerWith(aiService, fileUploadService);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(42L, null, Collections.emptyList()));

        controller.assistantStream(request, response, null, "s-1", null, null, file);

        verify(fileUploadService).upload(42L, file);
        verify(aiService).assistantStream("", "s-1", 42L, "", file,
                "/api/files/9", 9L);
    }

    private static AiController controllerWith(AiService aiService,
                                               FileUploadService fileUploadService) throws Exception {
        AiController controller = new AiController();
        Field aiField = AiController.class.getDeclaredField("aiService");
        aiField.setAccessible(true);
        aiField.set(controller, aiService);
        Field fileField = AiController.class.getDeclaredField("fileUploadService");
        fileField.setAccessible(true);
        fileField.set(controller, fileUploadService);
        return controller;
    }
}

