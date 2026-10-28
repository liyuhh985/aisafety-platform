package com.safety.service.service.impl;

import com.baomidou.mybatisplus.core.conditions.Wrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.exception.BusinessException;
import com.safety.pojo.dto.HazardLocationUpdateDTO;
import com.safety.pojo.entity.Hazard;
import com.safety.pojo.entity.HazardAction;
import com.safety.pojo.entity.User;
import com.safety.pojo.vo.HazardMapVO;
import com.safety.service.mapper.HazardActionMapper;
import com.safety.service.mapper.HazardMapper;
import com.safety.service.mapper.UserMapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.redisson.api.RedissonClient;
import org.springframework.data.redis.core.StringRedisTemplate;

import java.lang.reflect.Method;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class HazardStateTransitionTest {

    private static final Long HAZARD_ID = 1L;
    private static final Long USER_ID = 7L;
    private static final Long HANDLER_ID = 8L;

    @Mock
    private HazardMapper hazardMapper;
    @Mock
    private HazardActionMapper hazardActionMapper;
    @Mock
    private UserMapper userMapper;
    @Mock
    private StringRedisTemplate redisTemplate;
    @Mock
    private RedissonClient redissonClient;

    private HazardServiceImpl service;

    @BeforeEach
    void setUp() {
        service = new HazardServiceImpl(hazardMapper, hazardActionMapper, userMapper,
                redisTemplate, redissonClient, null);
        service.init();
    }

    @Test
    void assignUsesConditionalUpdateAndLogsAction() {
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(handlerUser(HANDLER_ID));
        when(hazardMapper.assign(HAZARD_ID, HANDLER_ID)).thenReturn(1);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(1, USER_ID, HANDLER_ID));

        HazardMapVO unused = null;
        var result = service.assign(HAZARD_ID, USER_ID, HANDLER_ID);

        assertEquals(1, result.getStatus());
        assertEquals(HANDLER_ID, result.getHandlerId());
        verify(hazardMapper).assign(HAZARD_ID, HANDLER_ID);
        verify(hazardMapper, never()).updateById(any(Hazard.class));
        ArgumentCaptor<HazardAction> action = ArgumentCaptor.forClass(HazardAction.class);
        verify(hazardActionMapper).insert(action.capture());
        assertEquals("ASSIGN", action.getValue().getActionType());
    }

    @Test
    void reassignAcceptedHazardToAnotherHandler() {
        Long nextHandlerId = 9L;
        when(userMapper.selectByIdForUpdate(nextHandlerId)).thenReturn(handlerUser(nextHandlerId));
        when(hazardMapper.assign(HAZARD_ID, nextHandlerId)).thenReturn(1);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(1, USER_ID, nextHandlerId));

        var result = service.assign(HAZARD_ID, USER_ID, nextHandlerId);

        assertEquals(1, result.getStatus());
        assertEquals(nextHandlerId, result.getHandlerId());
        verify(hazardMapper).assign(HAZARD_ID, nextHandlerId);
    }

    @Test
    void assignRejectsMissingHandler() {
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(null);

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.assign(HAZARD_ID, USER_ID, HANDLER_ID));

        assertEquals(404, error.getCode());
        verify(hazardMapper, never()).assign(any(), any());
    }

    @Test
    void assignRejectsNonHandlerUser() {
        User ordinary = handlerUser(HANDLER_ID);
        ordinary.setRole(0);
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(ordinary);

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.assign(HAZARD_ID, USER_ID, HANDLER_ID));

        assertEquals(400, error.getCode());
        verify(hazardMapper, never()).assign(any(), any());
    }

    @Test
    void startRejectsNonHandlerAccount() {
        User ordinary = handlerUser(HANDLER_ID);
        ordinary.setRole(0);
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(ordinary);

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.start(HAZARD_ID, HANDLER_ID, 2));

        assertEquals(400, error.getCode());
        verify(hazardMapper, never()).transitionForHandler(any(), anyInt(), anyInt(), any());
    }

    @Test
    void repeatedAssignReturnsConflictWithoutSecondUpdate() {
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(handlerUser(HANDLER_ID));
        when(hazardMapper.assign(HAZARD_ID, HANDLER_ID)).thenReturn(0);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(1, USER_ID, HANDLER_ID));

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.assign(HAZARD_ID, USER_ID, HANDLER_ID));

        assertEquals(409, error.getCode());
        verify(hazardMapper, never()).updateById(any(Hazard.class));
    }

    @Test
    void startUsesHandlerScopedConditionalUpdate() {
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(handlerUser(HANDLER_ID));
        when(hazardMapper.transitionForHandler(HAZARD_ID, 1, 2, HANDLER_ID)).thenReturn(1);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(2, USER_ID, 2));

        var result = service.start(HAZARD_ID, HANDLER_ID, 2);

        assertEquals(2, result.getStatus());
        verify(hazardMapper).transitionForHandler(HAZARD_ID, 1, 2, HANDLER_ID);
        verify(hazardMapper, never()).updateById(any(Hazard.class));
    }

    @Test
    void completeSuccessMarksPendingReview() {
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(handlerUser(HANDLER_ID));
        when(hazardMapper.transitionForHandler(HAZARD_ID, 2, 3, HANDLER_ID)).thenReturn(1);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(3, USER_ID, HANDLER_ID));

        var result = service.complete(HAZARD_ID, HANDLER_ID, 2);

        assertEquals(3, result.getStatus());
        assertEquals(0, result.getReviewed());
        verify(hazardMapper).transitionForHandler(HAZARD_ID, 2, 3, HANDLER_ID);
        verify(hazardMapper, never()).updateById(any(Hazard.class));
    }
    @Test
    void staleStartStatusReturnsConflict() {
        when(userMapper.selectByIdForUpdate(HANDLER_ID)).thenReturn(handlerUser(HANDLER_ID));
        when(hazardMapper.transitionForHandler(HAZARD_ID, 1, 2, HANDLER_ID)).thenReturn(0);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(4, USER_ID, 4));

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.start(HAZARD_ID, HANDLER_ID, 2));

        assertEquals(409, error.getCode());
        verify(hazardMapper, never()).updateById(any(Hazard.class));
    }

    @Test
    void concurrentReviewLetsOnlyOneAdminWin() {
        when(hazardMapper.review(HAZARD_ID, 3, 1)).thenReturn(1, 0);
        Hazard reviewed = hazard(3, USER_ID, 3);
        reviewed.setReviewed(1);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(reviewed);

        var result = service.review(HAZARD_ID, USER_ID, true, "pass");

        assertEquals(3, result.getStatus());
        assertEquals(1, result.getReviewed());
        BusinessException error = assertThrows(BusinessException.class,
                () -> service.review(HAZARD_ID, USER_ID, false, "stale"));
        assertEquals(409, error.getCode());
        verify(hazardMapper, never()).updateById(any(Hazard.class));
    }

    @Test
    void locationUpdateCannotOverwriteConcurrentWithdrawal() {
        HazardLocationUpdateDTO dto = new HazardLocationUpdateDTO();
        dto.setLongitude(new BigDecimal("117.635"));
        dto.setLatitude(new BigDecimal("26.265"));
        dto.setAddress("new address");
        when(hazardMapper.updateLocationByCreator(HAZARD_ID, USER_ID, dto.getLongitude(),
                dto.getLatitude(), dto.getAddress(), dto.getDistrict())).thenReturn(0);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(5, USER_ID, 5));

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.updateLocation(HAZARD_ID, USER_ID, 0, dto));

        assertEquals(409, error.getCode());
        verify(hazardMapper, never()).updateById(any(Hazard.class));
    }

    @Test
    void locationUpdateSuccessUsesCascAndLogsAction() {
        HazardLocationUpdateDTO dto = new HazardLocationUpdateDTO();
        dto.setLongitude(new BigDecimal("117.635"));
        dto.setLatitude(new BigDecimal("26.265"));
        dto.setAddress("new address");
        dto.setDistrict("三元区");
        when(hazardMapper.updateLocationByCreator(HAZARD_ID, USER_ID, dto.getLongitude(),
                dto.getLatitude(), dto.getAddress(), dto.getDistrict())).thenReturn(1);
        when(hazardMapper.selectById(HAZARD_ID)).thenReturn(hazard(0, USER_ID, 0));

        service.updateLocation(HAZARD_ID, USER_ID, 0, dto);

        verify(hazardMapper).updateLocationByCreator(HAZARD_ID, USER_ID, dto.getLongitude(),
                dto.getLatitude(), dto.getAddress(), dto.getDistrict());
        ArgumentCaptor<HazardAction> action = ArgumentCaptor.forClass(HazardAction.class);
        verify(hazardActionMapper).insert(action.capture());
        assertEquals("UPDATE_LOCATION", action.getValue().getActionType());
    }

    @Test
    void ordinaryUserListDoesNotFilterByOwner() {
        Page<Hazard> empty = new Page<>(1, 100, 0);
        empty.setRecords(List.of());
        when(hazardMapper.selectPage(any(Page.class), any())).thenReturn(empty);
        ArgumentCaptor<Page<Hazard>> pageCaptor = ArgumentCaptor.forClass(Page.class);
        ArgumentCaptor<Wrapper<Hazard>> wrapper = ArgumentCaptor.forClass(Wrapper.class);

        service.page(1, 999, USER_ID, 0);

        verify(hazardMapper).selectPage(pageCaptor.capture(), wrapper.capture());
        assertEquals(100, pageCaptor.getValue().getSize());
        com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Hazard> query =
                (com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<Hazard>) wrapper.getValue();
        assertFalse(query.getParamNameValuePairs().containsValue(USER_ID));
    }

    @Test
    void mapQueryClampsLimitAndReturnsWhitelistProjection() {
        HazardMapVO point = HazardMapVO.builder()
                .id(HAZARD_ID).longitude(new BigDecimal("117.1")).latitude(new BigDecimal("26.2"))
                .hazardType("FIRE").status(0).district("三元区").build();
        when(hazardMapper.selectMapPoints(100)).thenReturn(List.of(point));

        List<HazardMapVO> result = service.getMap(999);

        assertEquals(1, result.size());
        verify(hazardMapper).selectMapPoints(100);
        Set<String> fields = new HashSet<>(Arrays.stream(HazardMapVO.class.getDeclaredFields())
                .map(java.lang.reflect.Field::getName).toList());
        assertEquals(Set.of("id", "longitude", "latitude", "hazardType", "status", "district"), fields);
    }

    @Test
    void mapMapperSelectsOnlyWhitelistedColumns() throws Exception {
        Method method = HazardMapper.class.getMethod("selectMapPoints", int.class);
        String sql = String.join(" ", method.getAnnotation(Select.class).value()).toLowerCase();

        assertTrue(sql.contains("id"));
        assertTrue(sql.contains("longitude"));
        assertTrue(sql.contains("latitude"));
        assertTrue(sql.contains("hazard_type"));
        assertTrue(sql.contains("status"));
        assertTrue(sql.contains("district"));
        assertFalse(sql.contains("user_id"));
        assertFalse(sql.contains("description"));
        assertFalse(sql.contains("address"));
        assertFalse(sql.contains("image_url"));
        assertFalse(sql.contains("report"));
    }

    @Test
    void stateUpdatesCarryExpectedStatusAndOwnershipPredicates() throws Exception {
        String assignSql = updateSql("assign", Long.class, Long.class).toLowerCase();
        String handlerSql = updateSql("transitionForHandler", Long.class, int.class, int.class, Long.class)
                .toLowerCase();
        String locationSql = updateSql("updateLocationByCreator", Long.class, Long.class,
                BigDecimal.class, BigDecimal.class, String.class, String.class).toLowerCase();
        String withdrawSql = updateSql("withdraw", Long.class, Long.class).toLowerCase();

        assertTrue(assignSql.contains("status in (0, 1, 4)"));
        assertTrue(assignSql.contains("handler_id"));
        assertTrue(handlerSql.contains("status = #{fromstatus}"));
        assertTrue(handlerSql.contains("handler_id = #{userid}"));
        assertTrue(locationSql.contains("status = 0"));
        assertTrue(locationSql.contains("user_id = #{userid}"));
        assertTrue(withdrawSql.contains("status = 0"));
    }

    private String updateSql(String name, Class<?>... parameterTypes) throws Exception {
        Method method = HazardMapper.class.getMethod(name, parameterTypes);
        return String.join(" ", method.getAnnotation(Update.class).value());
    }

    private User handlerUser(long id) {
        User user = new User();
        user.setId(id);
        user.setRole(2);
        return user;
    }

    private Hazard hazard(int status, long userId, long handlerId) {
        Hazard hazard = new Hazard();
        hazard.setId(HAZARD_ID);
        hazard.setUserId(userId);
        hazard.setHandlerId(handlerId);
        hazard.setStatus(status);
        hazard.setReviewed(status == 3 ? 0 : null);
        hazard.setCreateTime(LocalDateTime.now());
        return hazard;
    }
}