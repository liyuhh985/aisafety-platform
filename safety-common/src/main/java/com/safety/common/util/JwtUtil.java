package com.safety.common.util;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Date;
import java.util.Locale;
import java.util.UUID;

public class JwtUtil {

    private static final int MIN_SECRET_BYTES = 32;
    private static final String[] PLACEHOLDER_SECRET_MARKERS = {
            "replace-with", "change-me", "changeme", "your-secret", "default-secret"
    };

    private final SecretKey key;
    private final long expirationMs;

    public JwtUtil(String secret, long expirationMs) {
        validateSecret(secret);
        if (expirationMs <= 0) {
            throw new IllegalStateException("jwt.expiration-ms must be greater than 0");
        }
        this.key = new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256");
        this.expirationMs = expirationMs;
    }

    /** 兼容测试和旧调用；新登录应传入当前 sessionVersion。 */
    public String generate(Long userId, Integer role) {
        return generate(userId, role, 0L);
    }

    /** 生成 token，内含 userId、role、jti 和用户级 sessionVersion。 */
    public String generate(Long userId, Integer role, long authVersion) {
        if (userId == null) {
            throw new IllegalArgumentException("userId must not be null");
        }
        Date issuedAt = new Date();
        return Jwts.builder()
                .id(UUID.randomUUID().toString())
                .subject(String.valueOf(userId))
                .claim("role", normalizedRole(role))
                .claim("sv", authVersion)
                .issuedAt(issuedAt)
                .expiration(new Date(issuedAt.getTime() + expirationMs))
                .signWith(key)
                .compact();
    }

    /** 验签并提取 jti、userId、role、sessionVersion；非法或过期时返回 null。 */
    public TokenPayload parse(String token) {
        if (token == null || token.isBlank()) {
            return null;
        }
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(key)
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            Long userId = Long.valueOf(claims.getSubject());
            Integer role = Integer.valueOf(claims.get("role").toString());
            String jti = claims.getId();
            if (jti == null || jti.isBlank()) {
                return null;
            }
            Object versionClaim = claims.get("sv");
            long authVersion = versionClaim == null ? 0L : Long.parseLong(versionClaim.toString());
            return new TokenPayload(userId, role, jti, authVersion);
        } catch (Exception e) {
            return null;
        }
    }

    public String sessionKey(String jti) {
        if (jti == null || jti.isBlank()) {
            throw new IllegalArgumentException("jti must not be blank");
        }
        return "safety:token:session:" + jti;
    }

    public String authVersionKey(Long userId) {
        if (userId == null) {
            throw new IllegalArgumentException("userId must not be null");
        }
        return "safety:token:version:" + userId;
    }

    public long sessionTtlSeconds() {
        return Math.max(1L, expirationMs / 1000L);
    }

    private static int normalizedRole(Integer role) {
        return role == null ? 0 : role;
    }

    private static void validateSecret(String secret) {
        if (secret == null || secret.isBlank()) {
            throw new IllegalStateException("JWT_SECRET is required");
        }
        String normalized = secret.toLowerCase(Locale.ROOT);
        for (String marker : PLACEHOLDER_SECRET_MARKERS) {
            if (normalized.contains(marker)) {
                throw new IllegalStateException("JWT_SECRET must not use a placeholder value");
            }
        }
        if (secret.getBytes(StandardCharsets.UTF_8).length < MIN_SECRET_BYTES) {
            throw new IllegalStateException("JWT_SECRET must be at least 32 UTF-8 bytes");
        }
    }

    public record TokenPayload(Long userId, Integer role, String jti, long authVersion) {
    }
}
