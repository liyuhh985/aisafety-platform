package com.safety.service.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import com.safety.common.constant.RedisConstant;
import com.safety.common.exception.BusinessException;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.mapper.HazardMapper;
import com.safety.service.service.HazardService;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.beans.BeanUtils;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class HazardServiceImpl implements HazardService {

    private final HazardMapper hazardMapper;
    private final StringRedisTemplate redisTemplate;
    private final RedissonClient redissonClient;
    private static final ObjectMapper objectMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    private Cache<Long, HazardVO> localCache;

    public HazardServiceImpl(HazardMapper hazardMapper,
                             StringRedisTemplate redisTemplate,
                             RedissonClient redissonClient) {
        this.hazardMapper = hazardMapper;
        this.redisTemplate = redisTemplate;
        this.redissonClient = redissonClient;
    }

    @PostConstruct
    public void init() {
        localCache = Caffeine.newBuilder()
                .maximumSize(1000)
                .expireAfterWrite(Duration.ofMinutes(1))
                .recordStats()
                .build();
    }

    @Override
    public HazardVO create(Long userId, HazardDTO dto) {
        // 分布式锁: 防止同一用户并发重复上报
        String lockKey = RedisConstant.KEY_PREFIX + "lock:hazard:create:" + userId;
        RLock lock = redissonClient.getLock(lockKey);
        try {
            if (!lock.tryLock(3, 10, TimeUnit.SECONDS)) {
                throw new BusinessException("操作太频繁，请稍后再试");
            }
            Hazard hazard = new Hazard();
            BeanUtils.copyProperties(dto, hazard);
            hazard.setUserId(userId);
            hazard.setStatus(0);
            if (hazard.getSeverity() == null) {
                hazard.setSeverity(1);
            }
            hazardMapper.insert(hazard);
            hazard = hazardMapper.selectById(hazard.getId());
            return toVO(hazard);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new BusinessException("系统繁忙，请重试");
        } finally {
            if (lock.isHeldByCurrentThread()) {
                lock.unlock();
            }
        }
    }

    @Override
    public Page<HazardVO> page(int current, int size) {
        Page<Hazard> page = new Page<>(current, size);
        Page<Hazard> result = hazardMapper.selectPage(page,
                new LambdaQueryWrapper<Hazard>().orderByDesc(Hazard::getCreateTime));
        Page<HazardVO> voPage = new Page<>(current, size, result.getTotal());
        voPage.setRecords(result.getRecords().stream().map(this::toVO).toList());
        return voPage;
    }

    @Override
    public HazardVO getById(Long id) {
        // L1: Caffeine
        HazardVO cached = localCache.getIfPresent(id);
        if (cached != null) {
            log.debug("L1 Caffeine 命中: hazardId={}", id);
            return cached;
        }

        // L2: Redis
        String cacheKey = RedisConstant.HAZARD_CACHE_PREFIX + id;
        String redisData = redisTemplate.opsForValue().get(cacheKey);
        if (redisData != null) {
            try {
                HazardVO vo = objectMapper.readValue(redisData, HazardVO.class);
                localCache.put(id, vo);
                log.debug("L2 Redis 命中, 回填L1: hazardId={}", id);
                return vo;
            } catch (JsonProcessingException e) {
                log.warn("L2 反序列化失败, key={}", cacheKey);
            }
        }

        // L3: MySQL
        Hazard hazard = hazardMapper.selectById(id);
        if (hazard == null) {
            throw new BusinessException("隐患记录不存在");
        }
        HazardVO vo = toVO(hazard);

        // 回填 L2 + L1
        try {
            redisTemplate.opsForValue().set(cacheKey,
                    objectMapper.writeValueAsString(vo),
                    RedisConstant.HAZARD_CACHE_TTL, TimeUnit.MINUTES);
        } catch (JsonProcessingException e) {
            log.warn("L2 序列化失败, key={}", cacheKey);
        }
        localCache.put(id, vo);
        log.debug("L3 MySQL 命中, 回填L2+L1: hazardId={}", id);

        return vo;
    }

    private HazardVO toVO(Hazard hazard) {
        return new HazardVO(
                hazard.getId(), hazard.getUserId(), hazard.getImageUrl(),
                hazard.getHazardType(), hazard.getDescription(),
                hazard.getLongitude(), hazard.getLatitude(), hazard.getAddress(),
                hazard.getSeverity(), hazard.getStatus(),
                switch (hazard.getStatus()) {
                    case 0 -> "待审核";
                    case 1 -> "已确认";
                    case 2 -> "处理中";
                    case 3 -> "已处理";
                    case 4 -> "已关闭";
                    default -> "未知";
                },
                hazard.getCreateTime());
    }
}
