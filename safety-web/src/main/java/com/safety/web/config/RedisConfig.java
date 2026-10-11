package com.safety.web.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

/**
 * Redis 配置。
 *
 * 这里只保留 StringRedisTemplate。原先还有一个 RedisCacheManager，但全仓
 * 没有任何 @EnableCaching / @Cacheable，它是个死 bean —— 留着会让人误以为
 * "缓存已经交给 Spring 管了"，进而重复造轮子。以后真要用声明式缓存，
 * 把 @EnableCaching 和它一起加回来。
 *
 * 隐患详情那条三级缓存（Caffeine -> Redis -> MySQL）是手写在
 * HazardServiceImpl 里的，不依赖这个 bean。
 */
@Configuration
public class RedisConfig {

    @Bean
    public StringRedisTemplate stringRedisTemplate(RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}