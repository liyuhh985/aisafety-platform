package com.safety.web.controller;

import com.safety.common.util.JwtUtil;
import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.SendCodeDTO;
import com.safety.service.service.MailService;
import com.safety.service.service.UserService;
import com.safety.web.annotation.RateLimit;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class AuthControllerSecurityTest {

    private static final String SECRET =
            "task-a-test-only-jwt-secret-at-least-thirty-two-bytes";

    @Test
    void loginAndSendCodeAreLimitedByRemoteAddressToPreventEmailSpray() throws Exception {
        Method login = AuthController.class.getMethod(
                "login", LoginDTO.class, HttpServletRequest.class);
        Method sendCode = AuthController.class.getMethod(
                "sendCode", SendCodeDTO.class, HttpServletRequest.class);

        RateLimit loginLimit = login.getAnnotation(RateLimit.class);
        RateLimit codeLimit = sendCode.getAnnotation(RateLimit.class);

        assertFalse(loginLimit.key().contains("#dto.email"));
        assertTrue(loginLimit.key().contains("#request.remoteAddr"));
        assertEquals(10L, loginLimit.count());
        assertFalse(codeLimit.key().contains("#dto.email"));
        assertTrue(codeLimit.key().contains("#request.remoteAddr"));
        assertEquals(5L, codeLimit.count());
    }

    @Test
    void logoutDeletesCurrentJtiSession() {
        UserService userService = mock(UserService.class);
        MailService mailService = mock(MailService.class);
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        SetOperations<String, String> setOperations = mock(SetOperations.class);
        when(redisTemplate.opsForSet()).thenReturn(setOperations);
        JwtUtil jwtUtil = new JwtUtil(SECRET, 60_000L);
        String token = jwtUtil.generate(7L, 0);
        JwtUtil.TokenPayload payload = jwtUtil.parse(token);
        String sessionKey = jwtUtil.sessionKey(payload.jti());

        AuthController controller = new AuthController(
                userService, mailService, jwtUtil, redisTemplate);

        controller.logout("Bearer " + token);

        verify(redisTemplate).delete(sessionKey);
        verify(setOperations).remove("safety:token:user:7", payload.jti());
    }
}

