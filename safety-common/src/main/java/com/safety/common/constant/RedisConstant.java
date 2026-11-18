package com.safety.common.constant;

public class RedisConstant {
    public static final String KEY_PREFIX = "safety:";

    public static final String TOKEN_PREFIX = KEY_PREFIX + "token:";
    public static final String TOKEN_USER_PREFIX = KEY_PREFIX + "token:user:";
    public static final String TOKEN_VERSION_PREFIX = KEY_PREFIX + "token:version:";
    public static final String EMAIL_CODE_PREFIX = KEY_PREFIX + "email_code:";
    public static final String RATE_LIMIT_PREFIX = KEY_PREFIX + "limit:";
    public static final String HAZARD_CACHE_PREFIX = KEY_PREFIX + "hazard:";
    public static final String HAZARD_LIST_CACHE_PREFIX = KEY_PREFIX + "hazard:list:";

    public static final long TOKEN_TTL = 60 * 60 * 24; // 24小时
    public static final long EMAIL_CODE_TTL = 5; // 5分钟
    public static final long HAZARD_CACHE_TTL = 5; // 5分钟
    public static final long HAZARD_LIST_CACHE_TTL = 1; // 1分钟

    private RedisConstant() {}
}

