package com.safety.service.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import com.safety.common.util.JwtUtil;
import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.pojo.entity.User;
import com.safety.pojo.vo.LoginVO;
import com.safety.pojo.vo.UserVO;
import com.safety.service.mapper.UserMapper;
import com.safety.service.service.MailService;
import com.safety.service.service.UserService;
import lombok.RequiredArgsConstructor;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.Locale;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {

    private static final String LOGIN_FAILED_MESSAGE = "邮箱或密码错误";
    private static final String DUMMY_PASSWORD_HASH =
            "$2b$10$EzaApQFYJBd6QP7J/pqSWOx.2pQydbCKCXamyuT9FzXx/zMMaieI6";

    private final UserMapper userMapper;
    private final StringRedisTemplate redisTemplate;
    private final BCryptPasswordEncoder passwordEncoder;
    private final MailService mailService;
    private final JwtUtil jwtUtil;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public LoginVO login(LoginDTO dto) {
        String email = normalizeEmail(dto.getEmail());
        User user = userMapper.selectByEmailForUpdate(email);
        if (user == null) {
            // Keep the expensive BCrypt work on the unknown-account path as well.
            passwordEncoder.matches(dto.getPassword(), DUMMY_PASSWORD_HASH);
            throw new BusinessException(401, LOGIN_FAILED_MESSAGE);
        }
        if (!passwordEncoder.matches(dto.getPassword(), user.getPassword())) {
            throw new BusinessException(401, LOGIN_FAILED_MESSAGE);
        }
        return issueToken(user);
    }

    @Override
    public LoginVO register(RegisterDTO dto) {
        String email = normalizeEmail(dto.getEmail());
        // 先验证邮箱所有权，避免未收到验证码的人通过 409 枚举已注册邮箱。
        mailService.verifyCode(email, dto.getCode());
        User exist = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getEmail, email));
        if (exist != null) {
            throw new BusinessException(409, "该邮箱已注册");
        }

        User user = new User();
        user.setEmail(email);
        user.setPassword(passwordEncoder.encode(dto.getPassword()));
        user.setNickname(
                dto.getNickname() != null ? dto.getNickname() : email.split("@")[0]);
        try {
            userMapper.insert(user);
        } catch (DuplicateKeyException e) {
            throw new BusinessException(409, "该邮箱已注册");
        }

        return issueToken(user);
    }

    @Override
    public UserVO getUserById(Long id) {
        User user = userMapper.selectById(id);
        if (user == null) {
            throw new BusinessException(404, "用户不存在");
        }
        return UserVO.builder()
                .id(user.getId())
                .email(user.getEmail())
                .nickname(user.getNickname())
                .avatar(user.getAvatar())
                .role(user.getRole())
                .createTime(user.getCreateTime())
                .build();
    }

    private LoginVO issueToken(User user) {
        int role = user.getRole() == null ? 0 : user.getRole();
        long authVersion = currentAuthVersion(user.getId());
        String token = jwtUtil.generate(user.getId(), role, authVersion);
        JwtUtil.TokenPayload payload = jwtUtil.parse(token);
        if (payload == null) {
            throw new IllegalStateException("Generated JWT could not be parsed");
        }
        redisTemplate.opsForValue().set(
                jwtUtil.sessionKey(payload.jti()),
                user.getId() + ":" + role,
                jwtUtil.sessionTtlSeconds(),
                TimeUnit.SECONDS);
        String userTokensKey = RedisConstant.TOKEN_USER_PREFIX + user.getId();
        redisTemplate.opsForSet().add(userTokensKey, payload.jti());
        redisTemplate.expire(userTokensKey, jwtUtil.sessionTtlSeconds(), TimeUnit.SECONDS);
        return LoginVO.builder()
                .token(token)
                .userId(user.getId())
                .nickname(user.getNickname())
                .avatar(user.getAvatar())
                .role(user.getRole())
                .build();
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateRole(Long userId, Integer role) {
        if (role == null || (role != 0 && role != 1 && role != 2)) {
            throw new BusinessException(400, "角色值不合法");
        }
        User user = userMapper.selectByIdForUpdate(userId);
        if (user == null) {
            throw new BusinessException(404, "用户不存在");
        }
        user.setRole(role);
        userMapper.updateById(user);
        redisTemplate.opsForValue().increment(jwtUtil.authVersionKey(userId));
        revokeAllTokens(userId);
    }

    private long currentAuthVersion(Long userId) {
        String value = redisTemplate.opsForValue().get(jwtUtil.authVersionKey(userId));
        if (value == null || value.isBlank()) {
            return 0L;
        }
        try {
            return Long.parseLong(value);
        } catch (NumberFormatException e) {
            throw new IllegalStateException("Invalid token session version", e);
        }
    }

    private void revokeAllTokens(Long userId) {
        String key = RedisConstant.TOKEN_USER_PREFIX + userId;
        var jtis = redisTemplate.opsForSet().members(key);
        if (jtis != null) {
            for (String jti : jtis) {
                redisTemplate.delete(jwtUtil.sessionKey(jti));
            }
        }
        redisTemplate.delete(key);
    }

    private static String normalizeEmail(String email) {
        return email == null ? null : email.trim().toLowerCase(Locale.ROOT);
    }
}



