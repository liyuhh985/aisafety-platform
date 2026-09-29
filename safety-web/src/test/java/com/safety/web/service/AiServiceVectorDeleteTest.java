package com.safety.web.service;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import java.util.List;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.content;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class AiServiceVectorDeleteTest {

    @Test
    void deleteVectorsSendsConfiguredTokenAndExactJsonPayload() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        AiService service = new AiService(
                restTemplate,
                "http://python-ai:8000/api/ai",
                "shared-token");
        server.expect(requestTo(
                        "http://python-ai:8000/api/ai/internal/vectors/delete"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Internal-Token", "shared-token"))
                .andExpect(content().contentType(MediaType.APPLICATION_JSON))
                .andExpect(content().json(
                        "{\"table\":\"tb_hazard_case\",\"ids\":[42]}"))
                .andRespond(withSuccess("{\"deleted_count\":1}", MediaType.APPLICATION_JSON));

        service.deleteVectors("tb_hazard_case", List.of(42L));

        server.verify();
    }

    @Test
    void clientValidationErrorsArePermanent() {
        for (HttpStatus status : List.of(
                HttpStatus.BAD_REQUEST,
                HttpStatus.UNPROCESSABLE_ENTITY)) {
            RestTemplate restTemplate = new RestTemplate();
            MockRestServiceServer server =
                    MockRestServiceServer.bindTo(restTemplate).build();
            AiService service = new AiService(
                    restTemplate, "http://python-ai:8000/api/ai", "shared-token");
            server.expect(requestTo(
                            "http://python-ai:8000/api/ai/internal/vectors/delete"))
                    .andRespond(withStatus(status));

            assertThrows(VectorSyncPermanentException.class,
                    () -> service.deleteVectors("tb_hazard_case", List.of(42L)));
            server.verify();
        }
    }

    @Test
    void serverFailureRemainsRetryable() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        AiService service = new AiService(
                restTemplate, "http://python-ai:8000/api/ai", "shared-token");
        server.expect(requestTo(
                        "http://python-ai:8000/api/ai/internal/vectors/delete"))
                .andRespond(withStatus(HttpStatus.SERVICE_UNAVAILABLE));

        assertThrows(org.springframework.web.client.RestClientException.class,
                () -> service.deleteVectors("tb_hazard_case", List.of(42L)));
        server.verify();
    }

    @Test
    void notFoundMethodAndConflictArePermanent() {
        for (HttpStatus status : List.of(
                HttpStatus.NOT_FOUND,
                HttpStatus.METHOD_NOT_ALLOWED,
                HttpStatus.CONFLICT)) {
            RestTemplate restTemplate = new RestTemplate();
            MockRestServiceServer server =
                    MockRestServiceServer.bindTo(restTemplate).build();
            AiService service = new AiService(
                    restTemplate, "http://python-ai:8000/api/ai", "shared-token");
            server.expect(requestTo(
                            "http://python-ai:8000/api/ai/internal/vectors/delete"))
                    .andRespond(withStatus(status));

            assertThrows(VectorSyncPermanentException.class,
                    () -> service.deleteVectors("tb_hazard_case", List.of(42L)),
                    "HTTP " + status.value() + " 应判为永久失败");
            server.verify();
        }
    }

    @Test
    void unauthorizedAndForbiddenStayRetryable() {
        // 运维修完 token/权限后同一请求就能通 → 必须可重试；重试到上限由 service 转 FAILED 兜住
        for (HttpStatus status : List.of(
                HttpStatus.UNAUTHORIZED,
                HttpStatus.FORBIDDEN)) {
            RestTemplate restTemplate = new RestTemplate();
            MockRestServiceServer server =
                    MockRestServiceServer.bindTo(restTemplate).build();
            AiService service = new AiService(
                    restTemplate, "http://python-ai:8000/api/ai", "shared-token");
            server.expect(requestTo(
                            "http://python-ai:8000/api/ai/internal/vectors/delete"))
                    .andRespond(withStatus(status));

            RuntimeException raised = assertThrows(RuntimeException.class,
                    () -> service.deleteVectors("tb_hazard_case", List.of(42L)),
                    "HTTP " + status.value() + " 应可重试");
            assertFalse(raised instanceof VectorSyncPermanentException,
                    "HTTP " + status.value() + " 不该被判为永久失败");
            server.verify();
        }
    }

    @Test
    void rateLimitStaysRetryable() {
        RestTemplate restTemplate = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(restTemplate).build();
        AiService service = new AiService(
                restTemplate, "http://python-ai:8000/api/ai", "shared-token");
        server.expect(requestTo(
                        "http://python-ai:8000/api/ai/internal/vectors/delete"))
                .andRespond(withStatus(HttpStatus.TOO_MANY_REQUESTS));

        RuntimeException raised =
                assertThrows(RuntimeException.class,
                        () -> service.deleteVectors("tb_hazard_case", List.of(42L)));

        assertFalse(raised instanceof VectorSyncPermanentException,
                "429 是限流，属于可恢复错误，不应判为永久失败");
        server.verify();
    }
}
