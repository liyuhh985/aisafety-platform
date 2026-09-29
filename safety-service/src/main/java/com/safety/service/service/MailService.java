package com.safety.service.service;

import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class MailService {

    private final JavaMailSender mailSender;
    private final StringRedisTemplate redisTemplate;

    @Value("${spring.mail.username}")
    private String from;

    public void sendCode(String toEmail) {
        String code = String.valueOf((int) ((Math.random() * 9 + 1) * 100000));
        redisTemplate.opsForValue().set(
                RedisConstant.EMAIL_CODE_PREFIX + toEmail, code,
                RedisConstant.EMAIL_CODE_TTL, TimeUnit.MINUTES);

        SimpleMailMessage msg = new SimpleMailMessage();
        msg.setFrom(from);
        msg.setTo(toEmail);
        msg.setSubject("安全隐患分析平台 - 验证码");
        msg.setText("你的验证码是：" + code + "，5分钟内有效。");
        mailSender.send(msg);
    }

    public void verifyCode(String email, String inputCode) {
        String saved = redisTemplate.opsForValue()
                .get(RedisConstant.EMAIL_CODE_PREFIX + email);
        if (saved == null) {
            throw new BusinessException(400, "验证码已过期，请重新获取");
        }
        if (!saved.equals(inputCode)) {
            throw new BusinessException(400, "验证码错误");
        }
        redisTemplate.delete(RedisConstant.EMAIL_CODE_PREFIX + email);
    }
}
