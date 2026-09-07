package com.safety.web.config;

import com.safety.common.constant.RedisConstant;
import com.safety.common.util.JwtUtil;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

import java.io.IOException;
import java.util.Collections;
import java.util.List;

@Component
@RequiredArgsConstructor
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    private final StringRedisTemplate redisTemplate;

    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        String token = extractToken(request);
        if (StringUtils.hasText(token)) {
            Long userId = JwtUtil.parseUserId(token);
            // JWT 解析失败，回退 Redis 查询（兼容旧 token）
            if (userId == null) {
                String uidStr = redisTemplate.opsForValue().get(RedisConstant.TOKEN_PREFIX + token);
                if (StringUtils.hasText(uidStr)) {
                    userId = Long.parseLong(uidStr);
                }
            }
            if (userId != null) {
                Integer role = JwtUtil.parseRole(token);
                String roleName = roleName(role);
                List<GrantedAuthority> authorities = roleName == null
                        ? Collections.emptyList()
                        : Collections.singletonList(new SimpleGrantedAuthority(roleName));
                UsernamePasswordAuthenticationToken auth =
                        new UsernamePasswordAuthenticationToken(userId, null, authorities);
                SecurityContextHolder.getContext().setAuthentication(auth);
            }
        }
        chain.doFilter(request, response);
    }

    private String extractToken(HttpServletRequest request) {
        String header = request.getHeader("Authorization");
        if (StringUtils.hasText(header) && header.startsWith("Bearer ")) {
            return header.substring(7);
        }
        return null;
    }

    /** role: 0 普通 / 1 管理员 / 2 处理人员 */
    private static String roleName(Integer role) {
        if (role == null) {
            return null;
        }
        return switch (role) {
            case 1 -> "ROLE_ADMIN";
            case 2 -> "ROLE_HANDLER";
            default -> "ROLE_USER";
        };
    }
}
