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
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.UUID;
import java.util.concurrent.TimeUnit;

@Service
@RequiredArgsConstructor
public class UserServiceImpl implements UserService {

    private final UserMapper userMapper;
    private final StringRedisTemplate redisTemplate;
    private final BCryptPasswordEncoder passwordEncoder;
    private final MailService mailService;

    @Override
    public LoginVO login(LoginDTO dto) {
        User user = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getEmail, dto.getEmail()));
        if (user == null) {
            throw new BusinessException("用户不存在");
        }
        if (!passwordEncoder.matches(dto.getPassword(), user.getPassword())) {
            throw new BusinessException("密码错误");
        }
        String token = JwtUtil.generate(user.getId());
        redisTemplate.opsForValue().set(
                RedisConstant.TOKEN_PREFIX + token,
                user.getId().toString(),
                RedisConstant.TOKEN_TTL,
                TimeUnit.SECONDS);
        return LoginVO.builder()
                .token(token)
                .userId(user.getId())
                .nickname(user.getNickname())
                .avatar(user.getAvatar())
                .role(user.getRole())
                .build();
    }

    @Override
    public LoginVO register(RegisterDTO dto) {
        User exist = userMapper.selectOne(
                new LambdaQueryWrapper<User>().eq(User::getEmail, dto.getEmail()));
        if (exist != null) {
            throw new BusinessException("该邮箱已注册");
        }
        mailService.verifyCode(dto.getEmail(), dto.getCode());

        User user = new User();
        user.setEmail(dto.getEmail());
        user.setPassword(passwordEncoder.encode(dto.getPassword()));
        user.setNickname(
                dto.getNickname() != null ? dto.getNickname() : dto.getEmail().split("@")[0]);
        userMapper.insert(user);

        String token = JwtUtil.generate(user.getId());
        redisTemplate.opsForValue().set(
                RedisConstant.TOKEN_PREFIX + token,
                user.getId().toString(),
                RedisConstant.TOKEN_TTL,
                TimeUnit.SECONDS);
        return LoginVO.builder()
                .token(token)
                .userId(user.getId())
                .nickname(user.getNickname())
                .avatar(user.getAvatar())
                .role(user.getRole())
                .build();
    }

    @Override
    public UserVO getUserById(Long id) {
        User user = userMapper.selectById(id);
        if (user == null) {
            throw new BusinessException("用户不存在");
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
}
