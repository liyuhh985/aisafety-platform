package com.safety.web.aspect;

import com.safety.common.exception.BusinessException;
import com.safety.web.annotation.RateLimit;
import org.aspectj.lang.ProceedingJoinPoint;
import org.junit.jupiter.api.Test;
import org.redisson.api.RRateLimiter;
import org.redisson.api.RedissonClient;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class RateLimitAspectTest {

    @Test
    void rejectedAcquisitionRaisesTooManyRequestsCode() throws Throwable {
        RedissonClient redisson = mock(RedissonClient.class);
        RRateLimiter limiter = mock(RRateLimiter.class);
        when(redisson.getRateLimiter(anyString())).thenReturn(limiter);
        when(limiter.tryAcquire()).thenReturn(false);
        ProceedingJoinPoint joinPoint = mock(ProceedingJoinPoint.class);

        RateLimitAspect aspect = new RateLimitAspect(redisson);

        BusinessException raised = assertThrows(BusinessException.class,
                () -> aspect.around(joinPoint, annotation()));

        assertEquals(429, raised.getCode());
        verify(joinPoint, never()).proceed();
    }

    @Test
    void grantedRequestProceeds() throws Throwable {
        RedissonClient redisson = mock(RedissonClient.class);
        RRateLimiter limiter = mock(RRateLimiter.class);
        when(redisson.getRateLimiter(anyString())).thenReturn(limiter);
        when(limiter.tryAcquire()).thenReturn(true);
        ProceedingJoinPoint joinPoint = mock(ProceedingJoinPoint.class);
        when(joinPoint.proceed()).thenReturn("ok");

        RateLimitAspect aspect = new RateLimitAspect(redisson);

        assertEquals("ok", aspect.around(joinPoint, annotation()));
    }

    private static RateLimit annotation() {
        RateLimit rateLimit = mock(RateLimit.class);
        when(rateLimit.key()).thenReturn("fixed-key");
        when(rateLimit.count()).thenReturn(1L);
        when(rateLimit.time()).thenReturn(60L);
        return rateLimit;
    }
}
