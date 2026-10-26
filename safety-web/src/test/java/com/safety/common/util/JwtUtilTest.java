package com.safety.common.util;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JwtUtilTest {

    private static final String VALID_SECRET =
            "task-a-test-only-jwt-secret-at-least-thirty-two-bytes";

    @Test
    void rejectsMissingShortAndPlaceholderSecrets() {
        assertThrows(IllegalStateException.class, () -> new JwtUtil("", 60_000L));
        assertThrows(IllegalStateException.class, () -> new JwtUtil("too-short", 60_000L));
        assertThrows(IllegalStateException.class,
                () -> new JwtUtil("replace-with-a-high-entropy-secret-for-production", 60_000L));
    }

    @Test
    void generatedTokensContainUserRoleAndUniqueJti() {
        JwtUtil jwtUtil = new JwtUtil(VALID_SECRET, 60_000L);

        String first = jwtUtil.generate(7L, 1);
        String second = jwtUtil.generate(7L, 1);

        JwtUtil.TokenPayload firstPayload = jwtUtil.parse(first);
        JwtUtil.TokenPayload secondPayload = jwtUtil.parse(second);

        assertNotNull(firstPayload);
        assertEquals(7L, firstPayload.userId());
        assertEquals(1, firstPayload.role());
        assertNotNull(firstPayload.jti());
        assertNotEquals(firstPayload.jti(), secondPayload.jti());
        assertEquals("safety:token:session:" + firstPayload.jti(),
                jwtUtil.sessionKey(firstPayload.jti()));
    }

    @Test
    void tamperedTokenIsRejected() {
        JwtUtil jwtUtil = new JwtUtil(VALID_SECRET, 60_000L);
        String token = jwtUtil.generate(7L, 0);
        String tampered = token.substring(0, token.length() - 1)
                + (token.endsWith("a") ? "b" : "a");

        assertNull(jwtUtil.parse(tampered));
    }
    @Test
    void tokenCarriesSessionVersionForRoleRevocationRace() {
        JwtUtil jwtUtil = new JwtUtil(VALID_SECRET, 60_000L);
        String token = jwtUtil.generate(7L, 1, 3L);

        assertEquals(3L, jwtUtil.parse(token).authVersion());
    }
}
