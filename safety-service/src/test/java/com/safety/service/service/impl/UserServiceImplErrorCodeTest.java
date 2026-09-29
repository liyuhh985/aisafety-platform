package com.safety.service.service.impl;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.pojo.entity.User;
import com.safety.service.mapper.UserMapper;
import com.safety.service.service.MailService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
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

    private UserServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new UserServiceImpl(userMapper, redisTemplate, passwordEncoder, mailService);
    }

    @Test
    void unknownEmailIsUnauthorized() {
        when(userMapper.selectOne(any())).thenReturn(null);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.login(loginDto()));

        assertEquals(401, raised.getCode());
    }

    @Test
    void wrongPasswordIsUnauthorized() {
        User stored = new User();
        stored.setId(7L);
        stored.setPassword("hashed");
        when(userMapper.selectOne(any())).thenReturn(stored);
        when(passwordEncoder.matches("pw", "hashed")).thenReturn(false);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.login(loginDto()));

        assertEquals(401, raised.getCode());
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
