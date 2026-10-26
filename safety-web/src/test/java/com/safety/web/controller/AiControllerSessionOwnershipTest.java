package com.safety.web.controller;

import com.safety.web.service.AiService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import java.lang.reflect.Field;
import java.util.Collections;

import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class AiControllerSessionOwnershipTest {

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void historyPassesAuthenticatedUserIdInsteadOfSessionOnly() throws Exception {
        AiService aiService = mock(AiService.class);
        AiController controller = controllerWith(aiService);
        authenticate(42L);

        controller.history("session-1");

        verify(aiService).getHistory("session-1", 42L);
    }

    @Test
    void deletePassesAuthenticatedUserIdInsteadOfSessionOnly() throws Exception {
        AiService aiService = mock(AiService.class);
        AiController controller = controllerWith(aiService);
        authenticate(42L);

        controller.clearSession("session-1");

        verify(aiService).clearSession("session-1", 42L);
    }

    private static void authenticate(Long userId) {
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken(userId, null, Collections.emptyList()));
    }

    private static AiController controllerWith(AiService aiService) throws Exception {
        AiController controller = new AiController();
        Field field = AiController.class.getDeclaredField("aiService");
        field.setAccessible(true);
        field.set(controller, aiService);
        return controller;
    }
}
