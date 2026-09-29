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
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.entity.HazardAction;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.mapper.HazardActionMapper;
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
    private final HazardActionMapper hazardActionMapper;
    private final StringRedisTemplate redisTemplate;
    private final RedissonClient redissonClient;
    /** 已撤回：仅创建人本人、仅 status=0 时可达；普通用户与处理人不可见，管理员可见可统计 */
    private static final int STATUS_WITHDRAWN = 5;
    private static final ObjectMapper objectMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    private Cache<Long, HazardVO> localCache;

    public HazardServiceImpl(HazardMapper hazardMapper,
                             HazardActionMapper hazardActionMapper,
                             StringRedisTemplate redisTemplate,
                             RedissonClient redissonClient) {
        this.hazardMapper = hazardMapper;
        this.hazardActionMapper = hazardActionMapper;
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
        RLock lock;
        try {
            lock = redissonClient.getLock(lockKey);
        } catch (RuntimeException e) {
            log.error("隐患创建分布式锁不可用, key={}", lockKey, e);
            throw new BusinessException("hazard creation temporarily unavailable");
        }
        try {
            boolean acquired;
            try {
                acquired = lock.tryLock(3, 10, TimeUnit.SECONDS);
            } catch (RuntimeException e) {
                log.error("隐患创建分布式锁获取失败, key={}", lockKey, e);
                throw new BusinessException("hazard creation temporarily unavailable");
            }
            if (!acquired) {
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
            invalidateDetailCache(hazard.getId());
            invalidateListCache();
            return toVO(hazard);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new BusinessException("系统繁忙，请重试");
        } finally {
            try {
                if (lock.isHeldByCurrentThread()) {
                    lock.unlock();
                }
            } catch (RuntimeException e) {
                log.warn("隐患创建分布式锁释放失败, key={}", lockKey, e);
            }
        }
    }

    @Override
    public HazardVO createAi(AiHazardDTO dto) {
        if (dto.getUserId() == null) {
            throw new BusinessException("missing user id");
        }
        // 分布式锁: 防止同一用户并发重复上报
        String lockKey = RedisConstant.KEY_PREFIX + "lock:hazard:create:" + dto.getUserId();
        RLock lock;
        try {
            lock = redissonClient.getLock(lockKey);
        } catch (RuntimeException e) {
            log.error("隐患创建分布式锁不可用, key={}", lockKey, e);
            throw new BusinessException("hazard creation temporarily unavailable");
        }
        try {
            boolean acquired;
            try {
                acquired = lock.tryLock(3, 10, TimeUnit.SECONDS);
            } catch (RuntimeException e) {
                log.error("隐患创建分布式锁获取失败, key={}", lockKey, e);
                throw new BusinessException("hazard creation temporarily unavailable");
            }
            if (!acquired) {
                throw new BusinessException("操作太频繁，请稍后再试");
            }
            Hazard hazard = new Hazard();
            BeanUtils.copyProperties(dto, hazard);
            hazard.setUserId(dto.getUserId());
            hazard.setStatus(0);
            if (hazard.getSeverity() == null) {
                hazard.setSeverity(1);
            }
            // 4 类特化：hazard_type 承载类别（category 仅作入参，不落库）
            if (dto.getCategory() != null && !dto.getCategory().isBlank()) {
                hazard.setHazardType(dto.getCategory());
            }
            hazardMapper.insert(hazard);
            hazard = hazardMapper.selectById(hazard.getId());
            invalidateDetailCache(hazard.getId());
            invalidateListCache();
            return toVO(hazard);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new BusinessException("系统繁忙，请重试");
        } finally {
            try {
                if (lock.isHeldByCurrentThread()) {
                    lock.unlock();
                }
            } catch (RuntimeException e) {
                log.warn("隐患创建分布式锁释放失败, key={}", lockKey, e);
            }
        }
    }

    @Override
    public HazardVO assign(Long id, Long adminId, Long handlerId) {
        Hazard hazard = hazardMapper.selectById(id);
        if (hazard == null) {
            throw new BusinessException(404, "隐患不存在");
        }
        if (hazard.getStatus() == null || (hazard.getStatus() != 0 && hazard.getStatus() != 4)) {
            throw new BusinessException("仅待处理或已驳回任务可指派责任人");
        }
        hazard.setStatus(1);
        hazard.setReviewed(0);
        hazard.setHandlerId(handlerId);
        hazardMapper.updateById(hazard);
        saveAction(id, adminId, "ASSIGN", "status -> 1 (handler=" + handlerId + ")");
        invalidateDetailCache(id);
        invalidateListCache();
        return toVO(hazardMapper.selectById(id));
    }

    @Override
    public HazardVO start(Long id, Long userId, Integer role) {
        return transition(id, 1, 2, "START", userId, false, role);
    }

    @Override
    public HazardVO complete(Long id, Long userId, Integer role) {
        return transition(id, 2, 3, "COMPLETE", userId, false, role);
    }

    @Override
    public HazardVO review(Long id, Long adminId, boolean pass, String remark) {
        Hazard hazard = hazardMapper.selectById(id);
        if (hazard == null) {
            throw new BusinessException(404, "隐患不存在");
        }
        Integer st = hazard.getStatus();
        Integer rev = hazard.getReviewed();
        if (pass) {
            if (st != null && st == 3 && rev != null && rev == 1) {
                throw new BusinessException("该工单已办结归档，不可重复办结");
            }
            if (st == null || st != 3) {
                throw new BusinessException("仅处于待验收状态的工单可执行终审办结");
            }
            hazard.setStatus(3);
            hazard.setReviewed(1);
            hazardMapper.updateById(hazard);
            saveAction(id, adminId, "REVIEW_PASS", "验收通过; " + (remark == null ? "" : remark));
        } else {
            if (st != null && ((st == 3 && rev != null && rev == 1) || st == 4)) {
                throw new BusinessException("已办结归档或已驳回的任务不可重复驳回");
            }
            if (st == null || st != 3) {
                throw new BusinessException("仅处于待验收状态的工单可执行审查驳回");
            }
            hazard.setStatus(4);
            hazard.setReviewed(1);
            hazardMapper.updateById(hazard);
            saveAction(id, adminId, "REVIEW_REJECT", "审查驳回; " + (remark == null ? "" : remark));
        }
        invalidateDetailCache(id);
        invalidateListCache();
        return toVO(hazardMapper.selectById(id));
    }

    @Override
    public java.util.List<HazardVO> batchReview(java.util.List<Long> ids, Long adminId, boolean pass, String remark) {
        if (ids == null || ids.isEmpty()) {
            return java.util.Collections.emptyList();
        }
        java.util.List<HazardVO> results = new java.util.ArrayList<>();
        for (Long id : ids) {
            try {
                results.add(review(id, adminId, pass, remark));
            } catch (RuntimeException e) {
                log.warn("批量审批工单跳过, id={}, error={}", id, e.getMessage());
            }
        }
        return results;
    }

    private HazardVO transition(Long id, int from, int to, String actionType, Long userId, boolean setHandler, Integer role) {
        Hazard hazard = hazardMapper.selectById(id);
        if (hazard == null) {
            throw new BusinessException(404, "隐患不存在");
        }
        Integer cur = hazard.getStatus();
        if (cur == null || cur != from) {
            throw new BusinessException(409, "当前状态不允许流转到该状态");
        }
        boolean isAdmin = (role != null && role == 1);
        if (!isAdmin) {
            if (hazard.getHandlerId() == null || !hazard.getHandlerId().equals(userId)) {
                throw new BusinessException(403, "只能处理分配给自己的任务");
            }
        }
        hazard.setStatus(to);
        if (setHandler) {
            hazard.setHandlerId(userId);
        }
        if (to == 3) {
            hazard.setReviewed(0); // 专员完成整改，流转为待验收(reviewed=0)
        }
        hazardMapper.updateById(hazard);
        saveAction(id, userId, actionType, "status " + from + " -> " + to);
        invalidateDetailCache(id);
        invalidateListCache();
        return toVO(hazardMapper.selectById(id));
    }

    @Override
    public HazardVO withdraw(Long id, Long userId) {
        int rows = hazardMapper.withdraw(id, userId);
        if (rows == 0) {
            Hazard current = hazardMapper.selectById(id);
            if (current == null || !java.util.Objects.equals(current.getUserId(), userId)) {
                throw new BusinessException(404, "隐患不存在或无权限");
            }
            if (current.getStatus() != null && current.getStatus() == STATUS_WITHDRAWN) {
                // 重复点撤回：幂等，直接返回当前状态
                return toVO(current);
            }
            throw new BusinessException(409, "该任务已被受理，无法撤回");
        }
        saveAction(id, userId, "WITHDRAW", "status 0 -> " + STATUS_WITHDRAWN);
        invalidateDetailCache(id);
        invalidateListCache();
        return toVO(hazardMapper.selectById(id));
    }

    private void saveAction(Long hazardId, Long operatorId, String actionType, String remark) {
        try {
            HazardAction action = new HazardAction();
            action.setHazardId(hazardId);
            action.setOperatorId(operatorId);
            action.setActionType(actionType);
            action.setRemark(remark);
            hazardActionMapper.insert(action);
        } catch (RuntimeException e) {
            log.warn("记录隐患操作失败, hazardId={}, actionType={}", hazardId, actionType, e);
        }
    }

    @Override
    public Page<HazardVO> page(int current, int size, Long userId, Integer role) {
        // 普通用户(role=0)只能看自己上报的；处理人员/管理员看全部
        boolean restricted = (role != null && role == 0);
        boolean isAdmin = (role != null && role == 1);
        Page<Hazard> pg = new Page<>(current, size);
        LambdaQueryWrapper<Hazard> qw = new LambdaQueryWrapper<Hazard>()
                .orderByDesc(Hazard::getCreateTime);
        if (restricted && userId != null) {
            qw.eq(Hazard::getUserId, userId);
        }
        if (hidesWithdrawn(role)) {
            // 已撤回只对管理员可见（创建人自己、处理团队都看不到）
            qw.ne(Hazard::getStatus, STATUS_WITHDRAWN);
        }
        Page<Hazard> result = hazardMapper.selectPage(pg, qw);
        Page<HazardVO> voPage = new Page<>(current, size, result.getTotal());
        voPage.setRecords(result.getRecords().stream().map(this::toVO).toList());
        return voPage;
    }

    /**
     * 已撤回（status=5）是否对该角色隐藏：只有管理员（role=1）可见。
     * 抽成静态纯函数是为了让"可见性规则"本身可被单测锁住（SQL 层的真实行为由部署后的 e2e 覆盖）。
     */
    static boolean hidesWithdrawn(Integer role) {
        return role == null || role != 1;
    }

    private void invalidateListCache() {
        // 列表已改为轻量直接查库，无需跨公网遍历 keys
    }

    private void invalidateDetailCache(Long id) {
        localCache.invalidate(id);
        try {
            redisTemplate.delete(RedisConstant.HAZARD_CACHE_PREFIX + id);
        } catch (RuntimeException e) {
            log.warn("隐患详情缓存失效失败, id={}", id, e);
        }
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
        String redisData = null;
        try {
            redisData = redisTemplate.opsForValue().get(cacheKey);
        } catch (RuntimeException e) {
            log.warn("L2 Redis 读取失败, key={}", cacheKey, e);
        }
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
        } catch (JsonProcessingException | RuntimeException e) {
            log.warn("L2 Redis 写入失败, key={}", cacheKey, e);
        }
        localCache.put(id, vo);
        log.debug("L3 MySQL 命中, 回填L2+L1: hazardId={}", id);

        return vo;
    }

    private HazardVO toVO(Hazard hazard) {
        String statusText;
        if (hazard.getStatus() == null) {
            statusText = "未知";
        } else {
            statusText = switch (hazard.getStatus()) {
                case 0 -> "待处理";
                case 1 -> "已接单";
                case 2 -> "整改中";
                case 3 -> (hazard.getReviewed() != null && hazard.getReviewed() == 1) ? "已办结" : "待验收";
                case 4 -> "已驳回";
                case STATUS_WITHDRAWN -> "已撤回";
                default -> "未知";
            };
        }
        return new HazardVO(
                hazard.getId(), hazard.getUserId(), hazard.getImageUrl(),
                hazard.getHazardType(), hazard.getDescription(),
                hazard.getLongitude(), hazard.getLatitude(), hazard.getAddress(),
                hazard.getDistrict(), hazard.getReport(), hazard.getHandlerId(),
                hazard.getSeverity(), hazard.getStatus(), hazard.getReviewed(),
                statusText,
                hazard.getCreateTime(),
                hazard.getWithdrawnAt(),
                hazard.getWithdrawnBy());
    }

    @Override
    public HazardStatsVO getStats() {
        long withdrawn = hazardMapper.selectCount(
                new LambdaQueryWrapper<Hazard>().eq(Hazard::getStatus, STATUS_WITHDRAWN));
        long total = hazardMapper.selectCount(
                new LambdaQueryWrapper<Hazard>().ne(Hazard::getStatus, STATUS_WITHDRAWN));
        long processed = hazardMapper.selectCount(
                new LambdaQueryWrapper<Hazard>().eq(Hazard::getStatus, 3).eq(Hazard::getReviewed, 1));
        long processing = hazardMapper.selectCount(
                new LambdaQueryWrapper<Hazard>().in(Hazard::getStatus, 1, 2));
        String rate = total == 0 ? "0.0%"
                : String.format("%.1f%%", processed * 100.0 / total);
        return HazardStatsVO.builder()
                .total(total).processed(processed).processing(processing)
                .withdrawn(withdrawn).rate(rate)
                .build();
    }
}
