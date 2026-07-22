package com.safety.common.util;

import io.jsonwebtoken.Claims;
import io.jsonwebtoken.Jwts;

import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Date;

public class JwtUtil {

    private static final String SECRET = "SafetyPlatformJwtSecretKey2026July22!!!";
    private static final long EXPIRE_MS = 24 * 60 * 60 * 1000L; // 24小时

    private static SecretKey getKey() {
        byte[] keyBytes = SECRET.getBytes(StandardCharsets.UTF_8);
        return new SecretKeySpec(keyBytes, "HmacSHA256");
    }

    /** 生成 token，内含 userId */
    public static String generate(Long userId) {
        return Jwts.builder()
                .subject(String.valueOf(userId))
                .issuedAt(new Date())
                .expiration(new Date(System.currentTimeMillis() + EXPIRE_MS))
                .signWith(getKey())
                .compact();
    }

    /** 从 token 提取 userId，过期或非法返回 null */
    public static Long parseUserId(String token) {
        try {
            Claims claims = Jwts.parser()
                    .verifyWith(getKey())
                    .build()
                    .parseSignedClaims(token)
                    .getPayload();
            return Long.valueOf(claims.getSubject());
        } catch (Exception e) {
            return null;
        }
    }
}
