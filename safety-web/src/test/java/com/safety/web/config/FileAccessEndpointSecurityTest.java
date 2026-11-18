package com.safety.web.config;

import com.safety.service.service.FileAssetService;
import com.safety.service.service.FileUploadService;
import com.safety.web.controller.FileController;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(FileController.class)
@ContextConfiguration(classes = {
        FileController.class,
        SecurityConfig.class,
        JwtAuthenticationFilter.class
})
@TestPropertySource(properties = {
        "jwt.secret=task-a-test-only-jwt-secret-at-least-thirty-two-bytes",
        "jwt.expiration-ms=60000"
})
class FileAccessEndpointSecurityTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private FileAssetService fileAssetService;
    @MockBean
    private FileUploadService fileUploadService;
    @MockBean
    private StringRedisTemplate redisTemplate;

    @Test
    void anonymousFileReadIsRejected() throws Exception {
        mockMvc.perform(get("/api/files/88"))
                .andExpect(status().isForbidden());
    }
}
