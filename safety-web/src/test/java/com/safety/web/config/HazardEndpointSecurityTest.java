package com.safety.web.config;

import com.safety.pojo.vo.HazardStatsVO;
import com.safety.service.service.HazardService;
import com.safety.web.controller.HazardController;
import com.safety.web.service.AiService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(HazardController.class)
@ContextConfiguration(classes = {
        HazardController.class,
        SecurityConfig.class,
        JwtAuthenticationFilter.class
})
@TestPropertySource(properties = {
        "jwt.secret=task-a-test-only-jwt-secret-at-least-thirty-two-bytes",
        "jwt.expiration-ms=60000"
})
class HazardEndpointSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private HazardService hazardService;
    @MockBean
    private AiService aiService;
    @MockBean
    private StringRedisTemplate redisTemplate;

    @Test
    void anonymousHazardListIsRejected() throws Exception {
        mockMvc.perform(get("/api/hazard"))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousHazardDetailIsRejected() throws Exception {
        mockMvc.perform(get("/api/hazard/42"))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousStatsRemainAvailable() throws Exception {
        when(hazardService.getStats()).thenReturn(HazardStatsVO.builder().build());

        mockMvc.perform(get("/api/hazard/stats"))
                .andExpect(status().isOk());
    }
}