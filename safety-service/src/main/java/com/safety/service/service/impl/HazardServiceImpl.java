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
import com.safety.pojo.dto.HazardLocationUpdateDTO;
import com.safety.pojo.entity.FileAsset;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.entity.HazardAction;
import com.safety.pojo.entity.User;
import com.safety.pojo.vo.HazardMapVO;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.mapper.HazardActionMapper;
import com.safety.service.mapper.HazardMapper;
import com.safety.service.mapper.UserMapper;
import com.safety.service.service.FileAssetService;
import com.safety.service.service.HazardService;
import jakarta.annotation.PostConstruct;
import lombok.extern.slf4j.Slf4j;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.time.Duration;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
public class HazardServiceImpl implements HazardService {

    private final HazardMapper hazardMapper;
    private final HazardActionMapper hazardActionMapper;
    private final UserMapper userMapper;
    private final StringRedisTemplate redisTemplate;
    private final RedissonClient redissonClient;
    private final FileAssetService fileAssetService;
    /** 已撤回：仅创建人本人、仅 status=0 时可达；普通用户与处理人不可见，管理员可见可统计 */
    private static final int STATUS_WITHDRAWN = 5;
    private static final ObjectMapper objectMapper = new ObjectMapper()
            .registerModule(new JavaTimeModule());

    private Cache<Long, HazardVO> localCache;

    public HazardServiceImpl(HazardMapper hazardMapper,
                             HazardActionMapper hazardActionMapper,
                             StringRedisTemplate redisTemplate,
                             RedissonClient redissonClient) {
        this(hazardMapper, hazardActionMapper, null, redisTemplate, redissonClient, null);
    }

    @Autowired
    public HazardServiceImpl(HazardMapper hazardMapper,
                             HazardActionMapper hazardActionMapper,
                             UserMapper userMapper,
                             StringRedisTemplate redisTemplate,
                             RedissonClient redissonClient,
                             FileAssetService fileAssetService) {
        this.hazardMapper = hazardMapper;
        this.hazardActionMapper = hazardActionMapper;
        this.userMapper = userMapper;
        this.redisTemplate = redisTemplate;
        this.redissonClient = redissonClient;
        this.fileAssetService = fileAssetService;
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
    @Transactional(rollbackFor = Exception.class)
    public HazardVO create(Long userId, HazardDTO dto) {
        FileAsset imageAsset = resolveClientImage(dto, userId);
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
            hazard.setImageUrl(imageAsset == null ? null : fileAssetService.accessPath(imageAsset));
            hazard.setUserId(userId);
            hazard.setStatus(0);
            if (hazard.getSeverity() == null) {
                hazard.setSeverity(1);
            }
            hazardMapper.insert(hazard);
            if (imageAsset != null) {
                fileAssetService.markAttached(imageAsset.getId(), userId);
            }
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
    @Transactional
    public HazardVO createAi(AiHazardDTO dto) {
        if (dto.getUserId() == null) {
            throw new BusinessException("missing user id");
        }
        // 幂等：MQ 重复消费不能建两条。requestId 非空时先查已有。
        String requestId = dto.getRequestId();
        boolean hasRequestId = requestId != null && !requestId.isBlank();
        if (hasRequestId) {
            Hazard existing = hazardMapper.selectByRequestId(requestId);
            if (existing != null) {
                return toVO(existing);
            }
        }
        FileAsset imageAsset = null;
        if (dto.getImageFileId() == null
                && dto.getImageUrl() != null && !dto.getImageUrl().isBlank()) {
            throw new BusinessException(400, "AI 图片缺少受控 fileId");
        }
        if (dto.getImageFileId() != null) {
            if (fileAssetService == null) {
                throw new BusinessException(500, "file asset service unavailable");
            }
            imageAsset = fileAssetService.requireOwned(dto.getImageFileId(), dto.getUserId());
            if (!FileAssetService.STATUS_TEMP.equals(imageAsset.getStatus())) {
                throw new BusinessException(409, "image file already used");
            }
            dto.setImageUrl(fileAssetService.accessPath(imageAsset));
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
            // 多类别：hazard_types 存去空白、去重、保序后的英文逗号串；无有效项时回退主类别
            LinkedHashSet<String> hazardTypes = new LinkedHashSet<>();
            if (dto.getCategoryList() != null) {
                for (String item : dto.getCategoryList()) {
                    if (item != null && !item.isBlank()) {
                        hazardTypes.add(item.trim());
                    }
                }
            }
            if (hazardTypes.isEmpty()) {
                if (dto.getCategory() != null && !dto.getCategory().isBlank()) {
                    hazard.setHazardTypes(dto.getCategory().trim());
                }
            } else {
                hazard.setHazardTypes(String.join(",", hazardTypes));
            }
            try {
                hazardMapper.insert(hazard);
            } catch (DuplicateKeyException e) {
                // 唯一索引冲突 = 并发/重复消费：回查已有记录直接返回
                if (hasRequestId) {
                    Hazard existing = hazardMapper.selectByRequestId(requestId);
                    if (existing != null) {
                        return toVO(existing);
                    }
                }
                throw e;
            }
            hazard = hazardMapper.selectById(hazard.getId());
            if (imageAsset != null) {
                fileAssetService.markAttached(imageAsset.getId(), dto.getUserId());
            }
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
    @Transactional
    public HazardVO assign(Long id, Long adminId, Long handlerId) {
        requireHandlerUser(handlerId);
        int rows = hazardMapper.assign(id, handlerId);
        if (rows == 0) {
            Hazard current = requireHazard(id);
            if (current.getStatus() == null || (current.getStatus() != 0 && current.getStatus() != 4)) {
                throw new BusinessException(409, "仅待处理或已驳回任务可指派责任人");
            }
            throw new BusinessException(409, "工单状态已变化，请刷新后重试");
        }
        saveAction(id, adminId, "ASSIGN", "status -> 1 (handler=" + handlerId + ")");
        invalidateDetailCacheAfterCommit(id);
        invalidateListCache();
        return toVO(requireHazard(id));
    }

    @Override
    @Transactional
    public HazardVO start(Long id, Long userId, Integer role) {
        return transition(id, 1, 2, "START", userId, role);
    }

    @Override
    @Transactional
    public HazardVO complete(Long id, Long userId, Integer role) {
        return transition(id, 2, 3, "COMPLETE", userId, role);
    }

    @Override
    @Transactional
    public HazardVO review(Long id, Long adminId, boolean pass, String remark) {
        int toStatus = pass ? 3 : 4;
        int rows = hazardMapper.review(id, toStatus, 1);
        if (rows == 0) {
            Hazard current = requireHazard(id);
            Integer status = current.getStatus();
            Integer reviewed = current.getReviewed();
            if (status != null && status == 3 && reviewed != null && reviewed == 1) {
                throw new BusinessException(409, "该工单已办结归档，不可重复审核");
            }
            if (status != null && status == 4) {
                throw new BusinessException(409, "该工单已驳回，不可重复审核");
            }
            if (status == null || status != 3) {
                throw new BusinessException(409, "仅处于待验收状态的工单可执行终审");
            }
            throw new BusinessException(409, "审核状态已变化，请刷新后重试");
        }
        saveAction(id, adminId, pass ? "REVIEW_PASS" : "REVIEW_REJECT",
                (pass ? "验收通过; " : "审查驳回; ") + (remark == null ? "" : remark));
        invalidateDetailCacheAfterCommit(id);
        invalidateListCache();
        return toVO(requireHazard(id));
    }

    @Override
    @Transactional
    public java.util.List<HazardVO> batchReview(java.util.List<Long> ids, Long adminId, boolean pass, String remark) {
        if (ids == null || ids.isEmpty()) {
            return java.util.Collections.emptyList();
        }
        java.util.List<HazardVO> results = new java.util.ArrayList<>();
        for (Long id : ids) {
            try {
                results.add(review(id, adminId, pass, remark));
            } catch (BusinessException e) {
                log.warn("批量审批工单跳过, id={}, error={}", id, e.getMessage());
            }
        }
        return results;
    }

    private HazardVO transition(Long id, int from, int to, String actionType, Long userId, Integer role) {
        boolean isAdmin = (role != null && role == 1);
        if (!isAdmin) {
            requireHandlerUser(userId);
        }
        int rows = isAdmin
                ? hazardMapper.transitionAsAdmin(id, from, to)
                : hazardMapper.transitionForHandler(id, from, to, userId);
        if (rows == 0) {
            Hazard current = requireHazard(id);
            Integer status = current.getStatus();
            if (status == null || status != from) {
                throw new BusinessException(409, "当前状态不允许流转到该状态");
            }
            if (!isAdmin && !Objects.equals(current.getHandlerId(), userId)) {
                throw new BusinessException(403, "只能处理分配给自己的任务");
            }
            throw new BusinessException(409, "工单状态已变化，请刷新后重试");
        }
        saveAction(id, userId, actionType, "status " + from + " -> " + to);
        invalidateDetailCacheAfterCommit(id);
        invalidateListCache();
        return toVO(requireHazard(id));
    }

    @Override
    @Transactional
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
        invalidateDetailCacheAfterCommit(id);
        invalidateListCache();
        return toVO(hazardMapper.selectById(id));
    }

    @Override
    @Transactional
    public HazardVO adminWithdraw(Long id, Long adminId, String reason) {
        int rows = hazardMapper.adminWithdraw(id, adminId, reason);
        if (rows == 0) {
            Hazard current = hazardMapper.selectById(id);
            if (current == null) {
                throw new BusinessException(404, "隐患不存在");
            }
            if (Objects.equals(current.getStatus(), STATUS_WITHDRAWN)) {
                return toVO(current);
            }
            throw new BusinessException(409, "仅待处理、已接单或整改中的工单可撤回");
        }
        saveAction(id, adminId, "ADMIN_WITHDRAW", reason);
        invalidateDetailCacheAfterCommit(id);
        invalidateListCache();
        return toVO(hazardMapper.selectById(id));
    }

    @Override
    @Transactional
    public HazardVO updateLocation(Long id, Long userId, Integer role, HazardLocationUpdateDTO dto) {
        boolean isAdmin = (role != null && role == 1);
        int rows = isAdmin
                ? hazardMapper.updateLocationAsAdmin(id, dto.getLongitude(), dto.getLatitude(),
                        dto.getAddress(), dto.getDistrict())
                : hazardMapper.updateLocationByCreator(id, userId, dto.getLongitude(), dto.getLatitude(),
                        dto.getAddress(), dto.getDistrict());
        if (rows == 0) {
            Hazard current = requireHazard(id);
            if (current.getStatus() == null || current.getStatus() != 0) {
                throw new BusinessException(409, "仅待处理状态的隐患任务可修改定位");
            }
            if (!isAdmin && !Objects.equals(current.getUserId(), userId)) {
                throw new BusinessException(403, "只能修改自己创建的隐患任务定位");
            }
            throw new BusinessException(409, "工单状态已变化，请刷新后重试");
        }
        String remark = String.format("定位变更: [%s, %s], 地址: %s", dto.getLongitude(), dto.getLatitude(), dto.getAddress());
        saveAction(id, userId, "UPDATE_LOCATION", remark);
        invalidateDetailCacheAfterCommit(id);
        invalidateListCache();
        return toVO(requireHazard(id));
    }

    private void saveAction(Long hazardId, Long operatorId, String actionType, String remark) {
        HazardAction action = new HazardAction();
        action.setHazardId(hazardId);
        action.setOperatorId(operatorId);
        action.setActionType(actionType);
        action.setRemark(remark);
        hazardActionMapper.insert(action);
    }

    private Hazard requireHazard(Long id) {
        Hazard hazard = hazardMapper.selectById(id);
        if (hazard == null) {
            throw new BusinessException(404, "隐患不存在");
        }
        return hazard;
    }

    private User requireHandlerUser(Long userId) {
        User user = userMapper.selectByIdForUpdate(userId);
        if (user == null) {
            throw new BusinessException(404, "处理人员不存在");
        }
        if (!Objects.equals(user.getRole(), 2)) {
            throw new BusinessException(400, "目标用户不是处理人员");
        }
        return user;
    }

    @Override
    public Page<HazardVO> page(int current, int size, Long userId, Integer role) {
        int safeCurrent = Math.max(current, 1);
        int safeSize = Math.max(1, Math.min(size, 100));
        Page<Hazard> pg = new Page<>(safeCurrent, safeSize);
        LambdaQueryWrapper<Hazard> qw = new LambdaQueryWrapper<Hazard>()
                .orderByDesc(Hazard::getCreateTime);
        if (hidesWithdrawn(role)) {
            // 已撤回只对管理员可见（创建人自己、处理团队都看不到）
            qw.ne(Hazard::getStatus, STATUS_WITHDRAWN);
        }
        Page<Hazard> result = hazardMapper.selectPage(pg, qw);
        Page<HazardVO> voPage = new Page<>(safeCurrent, safeSize, result.getTotal());
        voPage.setRecords(result.getRecords().stream().map(this::toVO).toList());
        return voPage;
    }

    @Override
    public List<HazardMapVO> getMap(int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 100));
        return hazardMapper.selectMapPoints(safeLimit);
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

    private void invalidateDetailCacheAfterCommit(Long id) {
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    invalidateDetailCache(id);
                }
            });
            return;
        }
        invalidateDetailCache(id);
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
    public HazardVO getByRequestId(String requestId) {
        if (requestId == null || requestId.isBlank()) {
            return null;
        }
        Hazard hazard = hazardMapper.selectByRequestId(requestId);
        return hazard == null ? null : toVO(hazard);
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

    private FileAsset resolveClientImage(HazardDTO dto, Long userId) {
        if (dto.getImageUrl() != null && !dto.getImageUrl().isBlank()) {
            throw new BusinessException(400, "图片必须先上传并通过 fileId 绑定");
        }
        if (dto.getFileId() == null) {
            return null;
        }
        if (fileAssetService == null) {
            throw new BusinessException(500, "文件服务未就绪");
        }
        FileAsset asset = fileAssetService.requireOwned(dto.getFileId(), userId);
        if (!FileAssetService.STATUS_TEMP.equals(asset.getStatus())) {
            throw new BusinessException(409, "图片已使用或状态无效");
        }
        return asset;
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
                hazard.getHazardType(), hazard.getHazardTypes(), hazard.getDescription(),
                hazard.getLongitude(), hazard.getLatitude(), hazard.getAddress(),
                hazard.getDistrict(), hazard.getReport(), hazard.getHandlerId(),
                hazard.getSeverity(), hazard.getStatus(), hazard.getReviewed(),
                statusText,
                hazard.getCreateTime(),
                hazard.getWithdrawnAt(),
                hazard.getWithdrawnBy(),
                hazard.getWithdrawnReason());
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



