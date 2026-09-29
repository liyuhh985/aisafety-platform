package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
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
        MailService service = serviceWithStoredCode(null);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.verifyCode(EMAIL, "123456"));

        assertEquals(400, raised.getCode());
    }

    @Test
    void wrongCodeIsBadRequest() {
        MailService service = serviceWithStoredCode("123456");

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.verifyCode(EMAIL, "000000"));

        assertEquals(400, raised.getCode());
    }

    @Test
    void matchingCodeIsConsumed() {
        MailService service = serviceWithStoredCode("123456");

        assertDoesNotThrow(() -> service.verifyCode(EMAIL, "123456"));

        verify(redisTemplate).delete(anyString());
    }

    private MailService serviceWithStoredCode(String stored) {
        when(redisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get(anyString())).thenReturn(stored);
        return new MailService(mailSender, redisTemplate);
    }
}
