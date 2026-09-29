package com.safety.service.service.impl;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
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
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
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

        HazardVO result = service.create(7L, new HazardDTO());

        assertNotNull(result);
        assertEquals(1L, result.getId());
    }

    @Test
    void returnsBusinessFailureWhenDistributedLockIsUnavailable() {
        when(redissonClient.getLock(anyString())).thenThrow(new RuntimeException("redis down"));

        BusinessException raised = assertThrows(BusinessException.class,
                () -> service.create(7L, new HazardDTO()));

        assertEquals(500, raised.getCode());
    }
}
