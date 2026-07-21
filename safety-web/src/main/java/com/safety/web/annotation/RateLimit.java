package com.safety.web.annotation;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.concurrent.TimeUnit;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RateLimit {
    /** 限流 key，支持 SpEL 表达式，如 "send_code:#{#dto.email}" */
    String key();
    long count() default 1;
    long time() default 60;
    TimeUnit unit() default TimeUnit.SECONDS;
}
