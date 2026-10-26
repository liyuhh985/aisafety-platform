package com.safety.service.service.impl;

import com.safety.common.exception.BusinessException;
import com.safety.common.util.JwtUtil;
import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.pojo.entity.User;
import com.safety.pojo.vo.LoginVO;
import com.safety.service.mapper.UserMapper;
import com.safety.service.service.MailService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserServiceImplErrorCodeTest {

    @Mock
    private UserMapper userMapper;
    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private BCryptPasswordEncoder passwordEncoder;
    @Mock
    private MailService mailService;
    @Mock
    private JwtUtil jwtUtil;
    @Mock
    private ValueOperations<String, String> valueOperations;
    @Mock
    private SetOperations<String, String> setOperations;

    private UserServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new UserServiceImpl(userMapper, redisTemplate, passwordEncoder, mailService, jwtUtil);
    }

    @Test
    void unknownEmailStillRunsBcryptAndReturnsUnifiedMessage() {
        when(userMapper.selectByEmailForUpdate("e2e.codex@test.invalid")).thenReturn(null);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.login(loginDto()));

        assertEquals(401, raised.getCode());
        assertEquals("邮箱或密码错误", raised.getMessage());
        verify(passwordEncoder).matches(eq("pw"), anyString());
        verify(jwtUtil, never()).generate(any(), any());
        verify(redisTemplate, never()).opsForValue();
    }

    @Test
    void wrongPasswordReturnsUnifiedMessage() {
        User stored = new User();
        stored.setId(7L);
        stored.setPassword("hashed");
        when(userMapper.selectByEmailForUpdate("e2e.codex@test.invalid")).thenReturn(stored);
        when(passwordEncoder.matches("pw", "hashed")).thenReturn(false);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.login(loginDto()));

        assertEquals(401, raised.getCode());
        assertEquals("邮箱或密码错误", raised.getMessage());
        verify(jwtUtil, never()).generate(any(), any());
    }

    @Test
    void successfulLoginStoresJtiSessionForLogoutValidation() {
        User stored = new User();
        stored.setId(7L);
        stored.setPassword("hashed");
        stored.setRole(0);
        when(userMapper.selectByEmailForUpdate("e2e.codex@test.invalid")).thenReturn(stored);
        when(passwordEncoder.matches("pw", "hashed")).thenReturn(true);
        when(jwtUtil.authVersionKey(7L)).thenReturn("safety:token:version:7");
        when(jwtUtil.generate(7L, 0, 0L)).thenReturn("signed-token");
        when(jwtUtil.parse("signed-token"))
                .thenReturn(new JwtUtil.TokenPayload(7L, 0, "jti-7", 0L));
        when(jwtUtil.sessionKey("jti-7")).thenReturn("safety:token:session:jti-7");
        when(jwtUtil.sessionTtlSeconds()).thenReturn(3600L);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(redisTemplate.opsForSet()).thenReturn(setOperations);

        LoginVO result = service.login(loginDto());

        assertEquals("signed-token", result.getToken());
        verify(valueOperations).set(
                "safety:token:session:jti-7",
                "7:0",
                3600L,
                TimeUnit.SECONDS);
        verify(setOperations).add("safety:token:user:7", "jti-7");
        verify(redisTemplate).expire("safety:token:user:7", 3600L, TimeUnit.SECONDS);
    }

    @Test
    void duplicateEmailIsConflict() {
        when(userMapper.selectOne(any())).thenReturn(new User());

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.register(registerDto()));

        assertEquals(409, raised.getCode());
    }

    @Test
    void missingUserProfileIsNotFound() {
        when(userMapper.selectById(7L)).thenReturn(null);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.getUserById(7L));

        assertEquals(404, raised.getCode());
    }

    private static LoginDTO loginDto() {
        LoginDTO dto = new LoginDTO();
        dto.setEmail("e2e.codex@test.invalid");
        dto.setPassword("pw");
        return dto;
    }

    private static RegisterDTO registerDto() {
        RegisterDTO dto = new RegisterDTO();
        dto.setEmail("e2e.codex@test.invalid");
        dto.setCode("123456");
        dto.setPassword("pw123456");
        return dto;
    }
}

