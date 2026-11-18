package com.safety.service.service;

import com.safety.service.mapper.HazardCaseMapper;
import com.safety.service.mapper.HazardKnowledgeMapper;
import com.safety.service.mapper.RegulationMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.transaction.annotation.Transactional;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class KnowledgeDeleteServiceTest {

    @Mock
    private HazardCaseMapper caseMapper;
    @Mock
    private HazardKnowledgeMapper knowledgeMapper;
    @Mock
    private RegulationMapper regulationMapper;
    @Mock
    private VectorSyncOutboxService outboxService;

    @Test
    void successfulDeletesEnqueueTheExactSourceTableAndId() {
        when(caseMapper.deleteById(42L)).thenReturn(1);
        when(knowledgeMapper.deleteById(43L)).thenReturn(1);
        when(regulationMapper.deleteById(44L)).thenReturn(1);

        assertTrue(new CaseService(caseMapper, outboxService).delete(42L));
        assertTrue(new KnowledgeService(knowledgeMapper, outboxService).delete(43L));
        assertTrue(new RegulationService(regulationMapper, outboxService).delete(44L));

        verify(outboxService).enqueueDelete("tb_hazard_case", 42L);
        verify(outboxService).enqueueDelete("tb_hazard_knowledge", 43L);
        verify(outboxService).enqueueDelete("tb_regulation", 44L);
    }

    @Test
    void missingRecordReturnsFalseWithoutCreatingOutboxEvent() {
        when(caseMapper.deleteById(999L)).thenReturn(0);

        boolean deleted = new CaseService(caseMapper, outboxService).delete(999L);

        assertEquals(false, deleted);
        verifyNoInteractions(outboxService);
    }

    @Test
    void outboxFailurePropagatesSoTransactionCanRollBack() {
        when(caseMapper.deleteById(42L)).thenReturn(1);
        doThrow(new IllegalStateException("outbox unavailable"))
                .when(outboxService).enqueueDelete("tb_hazard_case", 42L);

        assertThrows(IllegalStateException.class,
                () -> new CaseService(caseMapper, outboxService).delete(42L));
    }

    @Test
    void allDeleteMethodsDeclareRollbackTransactionBoundary() throws Exception {
        assertTransactional(CaseService.class.getMethod("delete", Long.class));
        assertTransactional(KnowledgeService.class.getMethod("delete", Long.class));
        assertTransactional(RegulationService.class.getMethod("delete", Long.class));
    }

    private static void assertTransactional(Method method) {
        Transactional transactional = method.getAnnotation(Transactional.class);
        assertTrue(transactional != null);
        assertEquals(Exception.class, transactional.rollbackFor()[0]);
    }
}
