package com.safety.web.controller;

import com.safety.common.constant.RedisConstant;
import com.safety.common.result.R;
import com.safety.common.util.JwtUtil;
import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.pojo.dto.SendCodeDTO;
import com.safety.pojo.vo.LoginVO;
import com.safety.service.service.MailService;
import com.safety.service.service.UserService;
import com.safety.web.annotation.RateLimit;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.util.StringUtils;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final UserService userService;
    private final MailService mailService;
    private final JwtUtil jwtUtil;
    private final StringRedisTemplate redisTemplate;

    @RateLimit(
            key = "'send_code:' + #request.remoteAddr",
            count = 5,
            time = 60)
    @PostMapping(value = {"/send-code", "/code"})
    public R<Void> sendCode(@Valid @RequestBody SendCodeDTO dto,
                            HttpServletRequest request) {
        mailService.sendCode(dto.getEmail());
        return R.ok();
    }

    @RateLimit(
            key = "'login:' + #request.remoteAddr",
            count = 10,
            time = 60)
    @PostMapping("/login")
    public R<LoginVO> login(@Valid @RequestBody LoginDTO dto,
                            HttpServletRequest request) {
        return R.ok(userService.login(dto));
    }

    @PostMapping("/register")
    public R<LoginVO> register(@Valid @RequestBody RegisterDTO dto) {
        return R.ok(userService.register(dto));
    }

    @PostMapping("/logout")
    public R<Void> logout(
            @RequestHeader(value = "Authorization", required = false) String authorizationHeader) {
        JwtUtil.TokenPayload payload = jwtUtil.parse(extractBearerToken(authorizationHeader));
        if (payload != null) {
            redisTemplate.delete(jwtUtil.sessionKey(payload.jti()));
            redisTemplate.opsForSet().remove(
                    RedisConstant.TOKEN_USER_PREFIX + payload.userId(), payload.jti());
        }
        SecurityContextHolder.clearContext();
        return R.ok();
    }

    private static String extractBearerToken(String authorizationHeader) {
        if (StringUtils.hasText(authorizationHeader)
                && authorizationHeader.startsWith("Bearer ")) {
            return authorizationHeader.substring(7);
        }
        return null;
    }
}


