package com.safety.web.aspect;

import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import com.safety.web.annotation.RateLimit;
import lombok.RequiredArgsConstructor;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.reflect.MethodSignature;
import org.redisson.api.RRateLimiter;
import org.redisson.api.RateIntervalUnit;
import org.redisson.api.RateType;
import org.redisson.api.RedissonClient;
import org.springframework.core.DefaultParameterNameDiscoverer;
import org.springframework.expression.EvaluationContext;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.stereotype.Component;

import java.lang.reflect.Method;

@Aspect
@Component
@RequiredArgsConstructor
public class RateLimitAspect {

    private final RedissonClient redissonClient;
    private final ExpressionParser parser = new SpelExpressionParser();
    private final DefaultParameterNameDiscoverer discoverer = new DefaultParameterNameDiscoverer();

    @Around("@annotation(rateLimit)")
    public Object around(ProceedingJoinPoint pjp, RateLimit rateLimit) throws Throwable {
        // 解析 SpEL 表达式，从入参中动态拼出 key
        String resolvedKey = resolveKey(rateLimit.key(), pjp);
        String redisKey = RedisConstant.RATE_LIMIT_PREFIX + resolvedKey;

        RRateLimiter limiter = redissonClient.getRateLimiter(redisKey);
        limiter.trySetRate(RateType.OVERALL, rateLimit.count(),
                rateLimit.time(), RateIntervalUnit.SECONDS);

        if (!limiter.tryAcquire()) {
            throw new BusinessException(429,
                    "操作过于频繁，请" + rateLimit.time() + "秒后再试");
        }
        return pjp.proceed();
    }

    private String resolveKey(String expression, ProceedingJoinPoint pjp) {
        // 不含 # 说明是固定 key，直接返回
        if (!expression.contains("#")) {
            return expression;
        }

        MethodSignature signature = (MethodSignature) pjp.getSignature();
        Method method = signature.getMethod();
        String[] paramNames = discoverer.getParameterNames(method);
        Object[] args = pjp.getArgs();

        EvaluationContext context = new StandardEvaluationContext();
        if (paramNames != null) {
            for (int i = 0; i < paramNames.length; i++) {
                context.setVariable(paramNames[i], args[i]);
            }
        }
        return parser.parseExpression(expression).getValue(context, String.class);
    }
}
