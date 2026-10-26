package com.safety.service.service.impl;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.service.mapper.UserMapper;
import com.safety.service.service.MailService;
import com.safety.common.util.JwtUtil;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class UserServiceImplRegistrationTest {

    @Mock private UserMapper userMapper;
    @Mock private StringRedisTemplate redisTemplate;
    @Mock private BCryptPasswordEncoder passwordEncoder;
    @Mock private MailService mailService;
    @Mock private JwtUtil jwtUtil;

    @Test
    void registrationChecksEmailOwnershipBeforeRevealingDuplicateAccount() {
        RegisterDTO dto = new RegisterDTO();
        dto.setEmail("existing@example.com");
        dto.setCode("000000");
        doThrow(new BusinessException(400, "验证码错误"))
                .when(mailService).verifyCode("existing@example.com", "000000");

        UserServiceImpl service = new UserServiceImpl(
                userMapper, redisTemplate, passwordEncoder, mailService, jwtUtil);

        BusinessException error = assertThrows(BusinessException.class, () -> service.register(dto));
        assertEquals(400, error.getCode());
        verify(userMapper, never()).selectOne(any());
    }
}
