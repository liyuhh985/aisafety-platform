package com.safety.service.service;

import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.test.util.ReflectionTestUtils;

import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.matches;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MailServiceErrorCodeTest {

    private static final String EMAIL = "e2e.codex@test.invalid";

    @Mock
    private JavaMailSender mailSender;
    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private ValueOperations<String, String> valueOperations;

    @Test
    void expiredCodeIsBadRequest() {
        MailService service = serviceWithConsumeResult(0L);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.verifyCode(EMAIL, "123456"));

        assertEquals(400, raised.getCode());
        assertEquals("验证码已过期，请重新获取", raised.getMessage());
    }

    @Test
    void wrongCodeIsBadRequest() {
        MailService service = serviceWithConsumeResult(-2L);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.verifyCode(EMAIL, "000000"));

        assertEquals(400, raised.getCode());
        assertEquals("验证码错误", raised.getMessage());
    }

    @Test
    void tooManyWrongAttemptsConsumesCode() {
        MailService service = serviceWithConsumeResult(-1L);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.verifyCode(EMAIL, "000000"));

        assertEquals(400, raised.getCode());
        assertEquals("验证码错误次数过多，请重新获取", raised.getMessage());
    }

    @Test
    void matchingCodeIsConsumed() {
        MailService service = serviceWithConsumeResult(1L);

        assertDoesNotThrow(() -> service.verifyCode(EMAIL, "123456"));

        verify(redisTemplate).execute(
                any(RedisScript.class),
                anyList(),
                eq("123456"),
                eq(String.valueOf(RedisConstant.EMAIL_CODE_TTL * 60)),
                eq("5"));
    }

    @Test
    void sendCodeUsesSixDigitsAndMockedMailOnly() {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        MailService service = new MailService(mailSender, redisTemplate);
        ReflectionTestUtils.setField(service, "from", "no-reply@test.invalid");

        service.sendCode(EMAIL);

        verify(valueOperations).set(
                eq(RedisConstant.EMAIL_CODE_PREFIX + EMAIL),
                matches("\\d{6}"),
                eq(RedisConstant.EMAIL_CODE_TTL),
                eq(TimeUnit.MINUTES));
        verify(mailSender).send(any(SimpleMailMessage.class));
    }

    private MailService serviceWithConsumeResult(Long result) {
        when(redisTemplate.execute(
                any(RedisScript.class),
                anyList(),
                any(Object[].class))).thenReturn(result);
        return new MailService(mailSender, redisTemplate);
    }
}