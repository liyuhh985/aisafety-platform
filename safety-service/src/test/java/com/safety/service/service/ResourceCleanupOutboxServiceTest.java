package com.safety.service.service;

import com.safety.pojo.entity.ResourceCleanupOutbox;
import com.safety.service.mapper.ResourceCleanupOutboxMapper;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.regex.Pattern;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ResourceCleanupOutboxServiceTest {

    @Mock
    private ResourceCleanupOutboxMapper mapper;

    private ResourceCleanupOutboxService service;

    @BeforeEach
    void setUp() {
        service = new ResourceCleanupOutboxService(mapper);
    }

    @Test
    void enqueueObjectDeleteCreatesImmediatelyDueMinioTask() {
        LocalDateTime before = LocalDateTime.now();

        service.enqueueObjectDelete("safety-images", "abc123.png", "tb_hazard_report", 42L);

        ArgumentCaptor<ResourceCleanupOutbox> captor =
                ArgumentCaptor.forClass(ResourceCleanupOutbox.class);
        verify(mapper).insert(captor.capture());
        ResourceCleanupOutbox task = captor.getValue();
        assertEquals("MINIO", task.getTarget());
        assertEquals("safety-images", task.getBucket());
        assertEquals("abc123.png", task.getObjectKey());
        assertEquals("tb_hazard_report", task.getSourceTable());
        assertEquals(42L, task.getRefId());
        assertEquals("PENDING", task.getStatus());
        assertEquals(0, task.getClaimVersion());
        assertEquals(0, task.getRetryCount());
        assertTrue(!task.getNextRetryTime().isBefore(before));
        assertTrue(!task.getNextRetryTime().isAfter(LocalDateTime.now()));
    }

    @Test
    void enqueueRejectsBlankObjectKeyBeforeInsert() {
        assertThrows(IllegalArgumentException.class,
                () -> service.enqueueObjectDelete("safety-images", "  ", "tb_hazard_report", 42L));

        verifyNoInteractions(mapper);
    }

    @Test
    void claimReturnsNewLeaseVersionOnlyWhenConditionalUpdateWins() {
        ResourceCleanupOutbox won = task(7L, 3, 0);
        ResourceCleanupOutbox lost = task(8L, 5, 0);
        when(mapper.claim(7L, 3)).thenReturn(1);
        when(mapper.claim(8L, 5)).thenReturn(0);

        assertEquals(4, service.claim(won));
        assertNull(service.claim(lost));
    }

    @Test
    void retryIncrementsCountTruncatesErrorAndCapsDelayAtOneHour() {
        LocalDateTime earliest = LocalDateTime.now().plusSeconds(3599);
        String longError = "x".repeat(1200);

        service.markRetry(7L, 4, 20, longError);

        ArgumentCaptor<LocalDateTime> nextAttempt = ArgumentCaptor.forClass(LocalDateTime.class);
        ArgumentCaptor<String> error = ArgumentCaptor.forClass(String.class);
        verify(mapper).markRetry(eq(7L), eq(4), eq(21), nextAttempt.capture(), error.capture());
        assertTrue(!nextAttempt.getValue().isBefore(earliest));
        assertTrue(Duration.between(LocalDateTime.now(), nextAttempt.getValue()).getSeconds() <= 3600);
        assertEquals(1000, error.getValue().length());
    }

    @Test
    void retryCountReachingLimitIsPersisted() {
        service.markRetry(7L, 4, 9, "still failing");

        verify(mapper).markRetry(eq(7L), eq(4), eq(10), any(LocalDateTime.class), any(String.class));
    }

    @Test
    void successAndPermanentFailureUseTerminalStateTransitions() {
        service.markSucceeded(7L, 4);
        service.markFailed(8L, 6, "missing objectKey");

        verify(mapper).markSucceeded(7L, 4);
        verify(mapper).markFailed(8L, 6, "missing objectKey");
    }

    /**
     * 重试上限靠 SQL 兜底：findClaimable 与 claim 都必须带 retry_count < 10，
     * 否则重试到上限的任务会被无限领取（向量删除那条链现在就是这个毛病）。
     */
    @Test
    void claimableSqlRefusesTasksThatReachedRetryLimit() throws Exception {
        String select = String.join(" ",
                ResourceCleanupOutboxMapper.class
                        .getMethod("findClaimable", int.class)
                        .getAnnotation(Select.class).value());
        String claim = String.join(" ",
                ResourceCleanupOutboxMapper.class
                        .getMethod("claim", Long.class, int.class)
                        .getAnnotation(Update.class).value());

        assertHasExactRetryCap(select, "findClaimable");
        assertHasExactRetryCap(claim, "claim");
    }

    /**
     * 必须是"正好小于 10"，不能用 contains("retry_count<10") 之类的子串判断：
     * retry_count < 1000 也含这个子串，会让上限被悄悄放宽却测不出来（变异实验踩过）。
     */
    private static void assertHasExactRetryCap(String sql, String methodName) {
        boolean exact = Pattern.compile("retry_count<10(?![0-9])")
                .matcher(normalize(sql)).find();
        assertTrue(exact, methodName + " 缺少 retry_count < 10 上限: " + sql);
    }

    private static String normalize(String sql) {
        return sql.replaceAll("\\s+", "").toLowerCase();
    }

    private static ResourceCleanupOutbox task(Long id, int claimVersion, int retryCount) {
        ResourceCleanupOutbox task = new ResourceCleanupOutbox();
        task.setId(id);
        task.setClaimVersion(claimVersion);
        task.setRetryCount(retryCount);
        task.setObjectKey("abc123.png");
        return task;
    }
}
