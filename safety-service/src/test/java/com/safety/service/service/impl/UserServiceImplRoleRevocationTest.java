package com.safety.service.service.impl;

import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import com.safety.common.util.JwtUtil;
import com.safety.pojo.entity.User;
import com.safety.service.mapper.UserMapper;
import com.safety.service.service.MailService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;

import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class UserServiceImplRoleRevocationTest {

    @Mock private UserMapper userMapper;
    @Mock private StringRedisTemplate redisTemplate;
    @Mock private BCryptPasswordEncoder passwordEncoder;
    @Mock private MailService mailService;
    @Mock private JwtUtil jwtUtil;
    @Mock private SetOperations<String, String> setOperations;
    @Mock private ValueOperations<String, String> valueOperations;

    private UserServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new UserServiceImpl(userMapper, redisTemplate, passwordEncoder, mailService, jwtUtil);
    }

    @Test
    void roleChangeRevokesEveryIssuedTokenForUser() {
        User user = new User();
        user.setId(7L);
        user.setRole(0);
        when(userMapper.selectByIdForUpdate(7L)).thenReturn(user);
        when(redisTemplate.opsForSet()).thenReturn(setOperations);
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(jwtUtil.authVersionKey(7L)).thenReturn("safety:token:version:7");
        when(setOperations.members(RedisConstant.TOKEN_USER_PREFIX + 7L))
                .thenReturn(Set.of("jti-a", "jti-b"));
        when(jwtUtil.sessionKey("jti-a")).thenReturn("session:a");
        when(jwtUtil.sessionKey("jti-b")).thenReturn("session:b");

        service.updateRole(7L, 2);

        assertEquals(2, user.getRole());
        verify(userMapper).updateById(user);
        verify(redisTemplate).delete("session:a");
        verify(redisTemplate).delete("session:b");
        verify(valueOperations).increment("safety:token:version:7");
        verify(redisTemplate).delete(RedisConstant.TOKEN_USER_PREFIX + 7L);
    }

    @Test
    void invalidRoleIsRejected() {
        BusinessException e = assertThrows(BusinessException.class, () -> service.updateRole(7L, 9));
        assertEquals(400, e.getCode());
    }
}


