package com.safety.service.service;

import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.security.SecureRandom;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class MailService {

    private static final int CODE_BOUND = 1_000_000;
    private static final int MAX_VERIFY_ATTEMPTS = 5;
    private static final SecureRandom SECURE_RANDOM = new SecureRandom();
    private static final RedisScript<Long> VERIFY_CODE_SCRIPT = new DefaultRedisScript<>(
            """
            local saved = redis.call('GET', KEYS[1])
            if not saved then
                return 0
            end
            if saved == ARGV[1] then
                redis.call('DEL', KEYS[1])
                redis.call('DEL', KEYS[2])
                return 1
            end
            local attempts = redis.call('INCR', KEYS[2])
            redis.call('EXPIRE', KEYS[2], ARGV[2])
            if attempts >= tonumber(ARGV[3]) then
                redis.call('DEL', KEYS[1])
                redis.call('DEL', KEYS[2])
                return -1
            end
            return -2
            """,
            Long.class);

    private final JavaMailSender mailSender;
    private final StringRedisTemplate redisTemplate;

    @Value("${spring.mail.username}")
    private String from;

    public void sendCode(String toEmail) {
        String email = normalizeEmail(toEmail);
        String code = String.format(Locale.ROOT, "%06d", SECURE_RANDOM.nextInt(CODE_BOUND));
        String codeKey = RedisConstant.EMAIL_CODE_PREFIX + email;
        redisTemplate.delete(attemptsKey(codeKey));
        redisTemplate.opsForValue().set(
                codeKey, code,
                RedisConstant.EMAIL_CODE_TTL, TimeUnit.MINUTES);

        SimpleMailMessage msg = new SimpleMailMessage();
        msg.setFrom(from);
        msg.setTo(email);
        msg.setSubject("安全隐患分析平台 - 验证码");
        msg.setText("你的验证码是：" + code + "，5分钟内有效。");
        mailSender.send(msg);
    }

    /**
     * Redis Lua 原子完成“比较 + 消费 + 错误计数”，避免并发下同一验证码成功两次。
     * 返回：1=成功，0=过期，-1=错误次数耗尽，-2=本次错误但仍有重试机会。
     */
    public void verifyCode(String email, String inputCode) {
        String codeKey = RedisConstant.EMAIL_CODE_PREFIX + normalizeEmail(email);
        Long result = redisTemplate.execute(
                VERIFY_CODE_SCRIPT,
                List.of(codeKey, attemptsKey(codeKey)),
                inputCode,
                String.valueOf(RedisConstant.EMAIL_CODE_TTL * 60),
                String.valueOf(MAX_VERIFY_ATTEMPTS));
        if (result == null || result == 0L) {
            throw new BusinessException(400, "验证码已过期，请重新获取");
        }
        if (result == -1L) {
            throw new BusinessException(400, "验证码错误次数过多，请重新获取");
        }
        if (result != 1L) {
            throw new BusinessException(400, "验证码错误");
        }
    }

    private static String attemptsKey(String codeKey) {
        return codeKey + ":attempts";
    }

    private static String normalizeEmail(String email) {
        return email == null ? null : email.trim().toLowerCase(Locale.ROOT);
    }
}