package com.safety.web.service;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.header;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class AiServiceInternalTokenTest {

    private static final String BASE = "http://python-ai:8000/api/ai";
    private static final String TOKEN = "shared-token";

    @Test
    void analyzeSendsInternalToken() throws Exception {
        RestTemplate rest = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(rest).build();
        AiService service = new AiService(rest, BASE, TOKEN);
        server.expect(requestTo(BASE + "/analyze"))
                .andExpect(method(HttpMethod.POST))
                .andExpect(header("X-Internal-Token", TOKEN))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        service.analyze(null, "test", 7L);

        server.verify();
    }

    @Test
    void historyUsesCurrentUserAndInternalToken() {
        RestTemplate rest = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(rest).build();
        AiService service = new AiService(rest, BASE, TOKEN);
        server.expect(requestTo(BASE + "/history?user_id=7&session_id=s-1"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("X-Internal-Token", TOKEN))
                .andRespond(withSuccess("{\"messages\":[]}", MediaType.APPLICATION_JSON));

        service.getHistory("s-1", 7L);

        server.verify();
    }

    @Test
    void deleteSessionUsesCurrentUserAndInternalToken() {
        RestTemplate rest = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(rest).build();
        AiService service = new AiService(rest, BASE, TOKEN);
        server.expect(requestTo(BASE + "/session?user_id=7&session_id=s-1"))
                .andExpect(method(HttpMethod.DELETE))
                .andExpect(header("X-Internal-Token", TOKEN))
                .andRespond(withSuccess("{}", MediaType.APPLICATION_JSON));

        service.clearSession("s-1", 7L);

        server.verify();
    }

    @Test
    void hazardCreateStatusUsesCurrentUserAndInternalToken() {
        RestTemplate rest = new RestTemplate();
        MockRestServiceServer server = MockRestServiceServer.bindTo(rest).build();
        AiService service = new AiService(rest, BASE, TOKEN);
        server.expect(requestTo(BASE + "/hazard-create/requests/req-1?user_id=7"))
                .andExpect(method(HttpMethod.GET))
                .andExpect(header("X-Internal-Token", TOKEN))
                .andRespond(withSuccess("{\"status\":\"SUCCESS\"}", MediaType.APPLICATION_JSON));

        service.hazardCreateStatus("req-1", 7L);

        server.verify();
    }
}
