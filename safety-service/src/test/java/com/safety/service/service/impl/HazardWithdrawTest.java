package com.safety.service.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.entity.HazardAction;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.mapper.HazardActionMapper;
import com.safety.service.mapper.HazardMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.time.LocalDateTime;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 隐患撤回（status 0 -> 5）的规格测试。
 *
 * 规则（spec: docs/superpowers/specs/2026-09-29-retract-and-image-hard-delete-design.md §2）：
 *   · 仅创建人本人可撤；非本人 → 404（视同不存在，不泄漏"这条存在但不属于你"）
 *   · 仅 status=0（未接单）可撤；已被受理 → 409
 *   · 不审核；重复撤 → 幂等
 *   · 已撤回：列表/详情只对管理员可见；统计单列 withdrawn，不计入 total
 */
@ExtendWith(MockitoExtension.class)
class HazardWithdrawTest {

    private static final Long ME = 7L;
    private static final Long OTHER = 9L;

    @Mock
    private HazardMapper hazardMapper;
    @Mock
    private HazardActionMapper hazardActionMapper;
    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private RedissonClient redissonClient;

    private HazardServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new HazardServiceImpl(hazardMapper, hazardActionMapper, redisTemplate, redissonClient);
        service.init();
    }

    private Hazard hazard(long id, long userId, int status) {
        Hazard h = new Hazard();
        h.setId(id);
        h.setUserId(userId);
        h.setStatus(status);
        h.setCreateTime(LocalDateTime.now());
        return h;
    }

    @Test
    void creatorCanWithdrawPendingHazard() {
        Hazard after = hazard(1L, ME, 5);
        after.setWithdrawnAt(LocalDateTime.now());
        after.setWithdrawnBy(ME);
        when(hazardMapper.withdraw(1L, ME)).thenReturn(1);
        when(hazardMapper.selectById(1L)).thenReturn(after);

        HazardVO vo = service.withdraw(1L, ME);

        assertEquals(5, vo.getStatus());
        assertEquals("已撤回", vo.getStatusText());
        assertEquals(ME, vo.getWithdrawnBy());
        assertNotNull(vo.getWithdrawnAt());
        ArgumentCaptor<HazardAction> action = ArgumentCaptor.forClass(HazardAction.class);
        verify(hazardActionMapper).insert(action.capture());
        assertEquals("WITHDRAW", action.getValue().getActionType());
    }

    @Test
    void cannotWithdrawSomeoneElsesHazard() {
        when(hazardMapper.withdraw(1L, ME)).thenReturn(0);
        when(hazardMapper.selectById(1L)).thenReturn(hazard(1L, OTHER, 0));

        BusinessException e = assertThrows(BusinessException.class, () -> service.withdraw(1L, ME));

        assertEquals(404, e.getCode());
    }

    @Test
    void cannotWithdrawAcceptedHazard() {
        when(hazardMapper.withdraw(1L, ME)).thenReturn(0);
        when(hazardMapper.selectById(1L)).thenReturn(hazard(1L, ME, 1));

        BusinessException e = assertThrows(BusinessException.class, () -> service.withdraw(1L, ME));

        assertEquals(409, e.getCode());
    }

    @Test
    void repeatedWithdrawIsIdempotent() {
        when(hazardMapper.withdraw(1L, ME)).thenReturn(0);
        when(hazardMapper.selectById(1L)).thenReturn(hazard(1L, ME, 5));

        HazardVO vo = service.withdraw(1L, ME);

        assertEquals(5, vo.getStatus());
    }

    @Test
    void withdrawnIsVisibleOnlyToAdmin() {
        // 规则：只有管理员(1) 能看到已撤回
        assertTrue(HazardServiceImpl.hidesWithdrawn(0), "普通用户应看不到");
        assertTrue(HazardServiceImpl.hidesWithdrawn(2), "处理人应看不到");
        assertTrue(HazardServiceImpl.hidesWithdrawn(null), "匿名/无角色应看不到");
        assertFalse(HazardServiceImpl.hidesWithdrawn(1), "管理员应能看到");
    }

    @Test
    void pageQueriesDatabaseForBothRoles() {
        Page<Hazard> empty = new Page<>(1, 10, 0);
        empty.setRecords(List.of());
        when(hazardMapper.selectPage(any(Page.class), any())).thenReturn(empty);

        service.page(1, 10, ME, 0);
        service.page(1, 10, null, 1);

        verify(hazardMapper, org.mockito.Mockito.times(2)).selectPage(any(Page.class), any());
    }

    @Test
    void statsReportsWithdrawnSeparatelyAndExcludesItFromTotal() {
        // 调用顺序：withdrawn -> total -> processed -> processing
        when(hazardMapper.selectCount(any())).thenReturn(2L, 20L, 18L, 0L);

        HazardStatsVO stats = service.getStats();

        assertEquals(2L, stats.getWithdrawn());
        assertEquals(20L, stats.getTotal());
        assertEquals(18L, stats.getProcessed());
        assertEquals(0L, stats.getProcessing());
        assertEquals("90.0%", stats.getRate());
    }
}
