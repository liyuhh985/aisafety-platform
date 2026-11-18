package com.safety.web.config;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.entity.HazardCase;
import com.safety.service.service.CaseService;
import com.safety.web.controller.CaseController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CaseController.class)
@TestPropertySource(properties = {
        "jwt.secret=task-a-test-only-jwt-secret-at-least-thirty-two-bytes",
        "jwt.expiration-ms=60000"
})
@ContextConfiguration(classes = {
        CaseController.class,
        SecurityConfig.class,
        JwtAuthenticationFilter.class
})
class KnowledgeEndpointSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private CaseService caseService;

    @MockBean
    private StringRedisTemplate redisTemplate;

    @Test
    void anonymousReadRemainsAvailable() throws Exception {
        when(caseService.page(anyInt(), anyInt(), isNull(), isNull()))
                .thenReturn(new Page<>());

        mockMvc.perform(get("/api/case"))
                .andExpect(status().isOk());
    }

    @Test
    void anonymousDeleteIsRejected() throws Exception {
        mockMvc.perform(delete("/api/case/42"))
                .andExpect(status().isForbidden());
    }
}
