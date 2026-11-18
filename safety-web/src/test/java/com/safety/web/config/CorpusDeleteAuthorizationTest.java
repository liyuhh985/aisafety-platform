package com.safety.web.config;

import com.safety.common.util.JwtUtil;
import com.safety.service.service.CaseService;
import com.safety.service.service.KnowledgeService;
import com.safety.service.service.RegulationService;
import com.safety.web.controller.CaseController;
import com.safety.web.controller.KnowledgeController;
import com.safety.web.controller.RegulationController;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 语料表（案例/法规/知识）的 DELETE 必须只对管理员开放。
 * 这层是方法级安全（@PreAuthorize），只有走 Spring 代理的请求才覆盖得到：
 * KnowledgeDeleteControllerTest 直接 new Controller，绕过代理，因此测不到这里。
 */
@WebMvcTest({CaseController.class, RegulationController.class, KnowledgeController.class})
@ContextConfiguration(classes = {
        CaseController.class,
        RegulationController.class,
        KnowledgeController.class,
        SecurityConfig.class,
        JwtAuthenticationFilter.class
})
@TestPropertySource(properties = {
        "jwt.secret=task-a-test-only-jwt-secret-at-least-thirty-two-bytes",
        "jwt.expiration-ms=60000"
})
class CorpusDeleteAuthorizationTest {

    private static final String[] CORPUS_DELETE_PATHS = {
            "/api/case/42",
            "/api/regulation/42",
            "/api/knowledge/42"
    };

    @Autowired
    private MockMvc mockMvc;
    @Autowired
    private JwtUtil jwtUtil;

    @MockBean
    private CaseService caseService;
    @MockBean
    private RegulationService regulationService;
    @MockBean
    private KnowledgeService knowledgeService;
    @MockBean
    private StringRedisTemplate redisTemplate;
    @MockBean
    private ValueOperations<String, String> valueOperations;

    @BeforeEach
    void setUpRedisSessions() {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
    }

    private String bearer(long userId, int role) {
        String token = jwtUtil.generate(userId, role);
        JwtUtil.TokenPayload payload = jwtUtil.parse(token);
        when(valueOperations.get(jwtUtil.sessionKey(payload.jti())))
                .thenReturn(userId + ":" + role);
        return "Bearer " + token;
    }

    @Test
    void regularUserCannotDeleteCorpus() throws Exception {
        for (String path : CORPUS_DELETE_PATHS) {
            mockMvc.perform(delete(path).header("Authorization", bearer(2L, 0)))
                    .andExpect(status().isForbidden());
        }
    }

    @Test
    void handlerCannotDeleteCorpus() throws Exception {
        for (String path : CORPUS_DELETE_PATHS) {
            mockMvc.perform(delete(path).header("Authorization", bearer(3L, 2)))
                    .andExpect(status().isForbidden());
        }
    }

    @Test
    void anonymousCannotDeleteCorpus() throws Exception {
        for (String path : CORPUS_DELETE_PATHS) {
            mockMvc.perform(delete(path))
                    .andExpect(status().isForbidden());
        }
    }

    @Test
    void adminCanDeleteCorpus() throws Exception {
        when(caseService.delete(42L)).thenReturn(true);
        when(regulationService.delete(42L)).thenReturn(true);
        when(knowledgeService.delete(42L)).thenReturn(true);

        for (String path : CORPUS_DELETE_PATHS) {
            mockMvc.perform(delete(path).header("Authorization", bearer(1L, 1)))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.code").value(200));
        }
    }
}