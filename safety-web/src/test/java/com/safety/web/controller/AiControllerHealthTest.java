package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.web.service.AiService;
import org.junit.jupiter.api.Test;

import java.lang.reflect.Field;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

class AiControllerHealthTest {

    @Test
    void returnsSuccessWhenPythonAiIsHealthy() throws Exception {
        R<String> response = controllerWith(new StubAiService(true)).health();

        assertEquals(200, response.getCode());
    }

    @Test
    void returnsFailureWhenPythonAiIsUnavailable() throws Exception {
        R<String> response = controllerWith(new StubAiService(false)).health();

        assertNotEquals(200, response.getCode());
    }

    private static AiController controllerWith(AiService aiService) throws Exception {
        AiController controller = new AiController();
        Field field = AiController.class.getDeclaredField("aiService");
        field.setAccessible(true);
        field.set(controller, aiService);
        return controller;
    }

    private static final class StubAiService extends AiService {
        private final boolean healthy;

        private StubAiService(boolean healthy) {
            this.healthy = healthy;
        }

        @Override
        public boolean isHealthy() {
            return healthy;
        }
    }
}
