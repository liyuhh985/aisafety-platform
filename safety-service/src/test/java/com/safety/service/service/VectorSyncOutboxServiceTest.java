package com.safety.service.service;

import com.safety.pojo.entity.VectorSyncOutbox;
import com.safety.service.mapper.VectorSyncOutboxMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Duration;
import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class VectorSyncOutboxServiceTest {

    @Mock
    private VectorSyncOutboxMapper mapper;

    private VectorSyncOutboxService service;

    @BeforeEach
    void setUp() {
        service = new VectorSyncOutboxService(mapper);
    }

    @Test
    void enqueueDeleteCreatesImmediatelyDuePendingEvent() {
        LocalDateTime before = LocalDateTime.now();

        service.enqueueDelete("tb_hazard_case", 42L);

        ArgumentCaptor<VectorSyncOutbox> eventCaptor =
                ArgumentCaptor.forClass(VectorSyncOutbox.class);
        verify(mapper).insert(eventCaptor.capture());
        VectorSyncOutbox event = eventCaptor.getValue();
        assertEquals("tb_hazard_case", event.getSourceTable());
        assertEquals(42L, event.getDocId());
        assertEquals("DELETE", event.getOperation());
        assertEquals("PENDING", event.getStatus());
        assertEquals(0, event.getClaimVersion());
        assertEquals(0, event.getRetryCount());
        assertTrue(!event.getNextRetryTime().isBefore(before));
        assertTrue(!event.getNextRetryTime().isAfter(LocalDateTime.now()));
    }

    @Test
    void enqueueDeleteRejectsUnsupportedSourceBeforeInsert() {
        assertThrows(IllegalArgumentException.class,
                () -> service.enqueueDelete("tb_unknown", 42L));
    }

    @Test
    void claimReturnsNewLeaseVersionOnlyWhenConditionalUpdateWins() {
        VectorSyncOutbox won = new VectorSyncOutbox();
        won.setId(7L);
        won.setClaimVersion(3);
        VectorSyncOutbox lost = new VectorSyncOutbox();
        lost.setId(8L);
        lost.setClaimVersion(5);
        when(mapper.claim(7L, 3)).thenReturn(1);
        when(mapper.claim(8L, 5)).thenReturn(0);

        assertEquals(4, service.claim(won));
        assertNull(service.claim(lost));
    }

    @Test
    void retryIncrementsCountTruncatesErrorAndCapsDelayAtOneHour() {
        LocalDateTime before = LocalDateTime.now().plusSeconds(3599);
        String longError = "x".repeat(1200);

        service.markRetry(7L, 4, 7, longError);

        ArgumentCaptor<LocalDateTime> nextAttempt =
                ArgumentCaptor.forClass(LocalDateTime.class);
        ArgumentCaptor<String> error = ArgumentCaptor.forClass(String.class);
        verify(mapper).markRetry(
                org.mockito.ArgumentMatchers.eq(7L),
                org.mockito.ArgumentMatchers.eq(4),
                org.mockito.ArgumentMatchers.eq(8),
                nextAttempt.capture(),
                error.capture());
        assertTrue(!nextAttempt.getValue().isBefore(before));
        assertTrue(Duration.between(LocalDateTime.now(), nextAttempt.getValue())
                .getSeconds() <= 3600);
        assertEquals(1000, error.getValue().length());
    }

    @Test
    void retryAtCapMarksTerminalFailureInsteadOfRetryingForever() {
        service.markRetry(9L, 4, 9, "boom");

        verify(mapper).markFailed(
                org.mockito.ArgumentMatchers.eq(9L),
                org.mockito.ArgumentMatchers.eq(4),
                org.mockito.ArgumentMatchers.eq("boom"));
        verify(mapper, org.mockito.Mockito.never()).markRetry(
                org.mockito.ArgumentMatchers.anyLong(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.anyInt(),
                org.mockito.ArgumentMatchers.any(),
                org.mockito.ArgumentMatchers.any());
    }

    @Test
    void successAndPermanentFailureUseTerminalStateTransitions() {
        service.markSucceeded(7L, 4);
        service.markFailed(8L, 6, "bad token");

        verify(mapper).markSucceeded(7L, 4);
        verify(mapper).markFailed(8L, 6, "bad token");
    }
}
