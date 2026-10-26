package com.safety.web.config;

import com.safety.common.util.JwtUtil;
import jakarta.servlet.FilterChain;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class JwtAuthenticationFilterTest {

    private static final String SECRET =
            "task-a-test-only-jwt-secret-at-least-thirty-two-bytes";

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void validTokenWithActiveJtiSessionAuthenticates() throws Exception {
        JwtUtil jwtUtil = new JwtUtil(SECRET, 60_000L);
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        ValueOperations<String, String> valueOperations = mock(ValueOperations.class);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);

        String token = jwtUtil.generate(7L, 2);
        JwtUtil.TokenPayload payload = jwtUtil.parse(token);
        when(valueOperations.get(jwtUtil.sessionKey(payload.jti()))).thenReturn("7:2");
        when(valueOperations.get(jwtUtil.authVersionKey(7L))).thenReturn("0");

        JwtAuthenticationFilter filter = new JwtAuthenticationFilter(redisTemplate, jwtUtil);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/hazard");
        request.addHeader("Authorization", "Bearer " + token);
        MockHttpServletResponse response = new MockHttpServletResponse();
        FilterChain chain = mock(FilterChain.class);

        filter.doFilter(request, response, chain);

        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        assertEquals(7L, authentication.getPrincipal());
        assertTrue(authentication.getAuthorities().stream()
                .anyMatch(authority -> "ROLE_HANDLER".equals(authority.getAuthority())));
        verify(chain).doFilter(request, response);
    }

    @Test
    void signedTokenWithoutActiveSessionIsRejected() throws Exception {
        JwtUtil jwtUtil = new JwtUtil(SECRET, 60_000L);
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        ValueOperations<String, String> valueOperations = mock(ValueOperations.class);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);

        String token = jwtUtil.generate(7L, 0);
        JwtUtil.TokenPayload payload = jwtUtil.parse(token);
        when(valueOperations.get(jwtUtil.sessionKey(payload.jti()))).thenReturn(null);

        JwtAuthenticationFilter filter = new JwtAuthenticationFilter(redisTemplate, jwtUtil);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/hazard");
        request.addHeader("Authorization", "Bearer " + token);

        filter.doFilter(request, new MockHttpServletResponse(), mock(FilterChain.class));

        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }
    @Test
    void tokenWithStaleSessionVersionIsRejectedEvenIfJtiExists() throws Exception {
        JwtUtil jwtUtil = new JwtUtil(SECRET, 60_000L);
        StringRedisTemplate redisTemplate = mock(StringRedisTemplate.class);
        @SuppressWarnings("unchecked")
        ValueOperations<String, String> valueOperations = mock(ValueOperations.class);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);

        String token = jwtUtil.generate(7L, 2, 3L);
        JwtUtil.TokenPayload payload = jwtUtil.parse(token);
        when(valueOperations.get(jwtUtil.sessionKey(payload.jti()))).thenReturn("7:2");
        when(valueOperations.get(jwtUtil.authVersionKey(7L))).thenReturn("4");

        JwtAuthenticationFilter filter = new JwtAuthenticationFilter(redisTemplate, jwtUtil);
        MockHttpServletRequest request = new MockHttpServletRequest("GET", "/api/hazard");
        request.addHeader("Authorization", "Bearer " + token);

        filter.doFilter(request, new MockHttpServletResponse(), mock(FilterChain.class));

        assertNull(SecurityContextHolder.getContext().getAuthentication());
    }}

