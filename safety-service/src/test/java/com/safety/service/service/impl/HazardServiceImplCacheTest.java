package com.safety.service.service.impl;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.mapper.HazardActionMapper;
import com.safety.service.mapper.HazardMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.redisson.api.RLock;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import com.safety.common.exception.BusinessException;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class HazardServiceImplCacheTest {

    @Mock
    private HazardMapper hazardMapper;
    @Mock
    private HazardActionMapper hazardActionMapper;
    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private ValueOperations<String, String> valueOperations;
    @Mock
    private RedissonClient redissonClient;
    @Mock
    private RLock lock;

    private HazardServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new HazardServiceImpl(hazardMapper, hazardActionMapper, redisTemplate, redissonClient);
        service.init();
    }

    @Test
    void pageReadsDatabaseDirectlyWithoutListCache() {
        Hazard hazard = new Hazard();
        hazard.setId(1L);
        hazard.setStatus(0);
        Page<Hazard> databasePage = new Page<>(1, 10, 1);
        databasePage.setRecords(List.of(hazard));
        // 列表已改为轻量直接查库（不再有 Redis 列表缓存），因此这里不再 stub Redis
        when(hazardMapper.selectPage(any(Page.class), any())).thenReturn(databasePage);

        Page<HazardVO> result = service.page(1, 10, null, null);

        assertEquals(1, result.getTotal());
        assertEquals(1, result.getRecords().size());
    }

    @Test
    void keepsCreatedHazardSuccessfulWhenCacheInvalidationFails() throws Exception {
        Hazard hazard = new Hazard();
        hazard.setId(1L);
        hazard.setStatus(0);
        doAnswer(invocation -> {
            Hazard inserted = invocation.getArgument(0);
            inserted.setId(1L);
            return 1;
        }).when(hazardMapper).insert(any(Hazard.class));
        when(hazardMapper.selectById(1L)).thenReturn(hazard);
        when(redissonClient.getLock(anyString())).thenReturn(lock);
        when(lock.tryLock(3, 10, TimeUnit.SECONDS)).thenReturn(true);
        when(lock.isHeldByCurrentThread()).thenReturn(true);
        doThrow(new RuntimeException("redis down")).when(redisTemplate).delete(anyString());

        HazardDTO dto = new HazardDTO();
        dto.setCategoryList(List.of("fire/fire_lane_blocked"));
        HazardVO result = service.create(7L, dto);

        assertNotNull(result);
        assertEquals(1L, result.getId());
    }

    @Test
    void createWritesNormalizedChineseHazardTypes() throws Exception {
        AtomicReference<Hazard> inserted = stubSuccessfulInsert();

        HazardDTO dto = new HazardDTO();
        dto.setCategoryList(List.of("fire/fire_lane_blocked", "市政设施/井盖缺失/破损"));
        service.create(7L, dto);

        assertEquals("消防安全/消防通道占用,市政设施/井盖缺失/破损",
                inserted.get().getHazardTypes());
    }

    @Test
    void createAiUsesCategoryFallbackAndWritesChineseHazardTypes() throws Exception {
        AtomicReference<Hazard> inserted = stubSuccessfulInsert();

        AiHazardDTO dto = new AiHazardDTO();
        dto.setUserId(7L);
        dto.setCategory("utility/gas_leak");
        dto.setCategoryList(List.of());
        service.createAi(dto);

        assertEquals("电气与燃气/燃气泄漏", inserted.get().getHazardTypes());
    }

    @Test
    void createRejectsInvalidCategoryBeforeInsert() throws Exception {
        when(redissonClient.getLock(anyString())).thenReturn(lock);
        when(lock.tryLock(3, 10, TimeUnit.SECONDS)).thenReturn(true);
        when(lock.isHeldByCurrentThread()).thenReturn(false);

        HazardDTO dto = new HazardDTO();
        dto.setCategoryList(List.of("fire/not_real"));
        BusinessException raised = assertThrows(BusinessException.class, () -> service.create(7L, dto));

        assertEquals(400, raised.getCode());
        verify(hazardMapper, never()).insert(any(Hazard.class));
    }

    private AtomicReference<Hazard> stubSuccessfulInsert() throws InterruptedException {
        when(redissonClient.getLock(anyString())).thenReturn(lock);
        when(lock.tryLock(3, 10, TimeUnit.SECONDS)).thenReturn(true);
        when(lock.isHeldByCurrentThread()).thenReturn(false);
        AtomicReference<Hazard> inserted = new AtomicReference<>();
        doAnswer(invocation -> {
            Hazard hazard = invocation.getArgument(0);
            hazard.setId(1L);
            hazard.setStatus(0);
            inserted.set(hazard);
            return 1;
        }).when(hazardMapper).insert(any(Hazard.class));
        when(hazardMapper.selectById(1L)).thenAnswer(invocation -> inserted.get());
        return inserted;
    }

    @Test
    void returnsBusinessFailureWhenDistributedLockIsUnavailable() {
        when(redissonClient.getLock(anyString())).thenThrow(new RuntimeException("redis down"));

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.create(7L, new HazardDTO()));

        assertEquals(500, raised.getCode());
    }
    @Test
    void rejectsClientSuppliedImageUrlWithoutControlledFileId() {
        HazardDTO dto = new HazardDTO();
        dto.setImageUrl("https://evil.example/tracker.png");

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.create(7L, dto));

        assertEquals(400, raised.getCode());
    }}

