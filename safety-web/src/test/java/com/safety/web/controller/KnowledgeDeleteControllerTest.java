package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.service.service.CaseService;
import com.safety.service.service.KnowledgeService;
import com.safety.service.service.RegulationService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class KnowledgeDeleteControllerTest {

    @Mock
    private CaseService caseService;
    @Mock
    private KnowledgeService knowledgeService;
    @Mock
    private RegulationService regulationService;

    @Test
    void successfulDeletesReturnHttpOk() {
        when(caseService.delete(42L)).thenReturn(true);
        when(knowledgeService.delete(43L)).thenReturn(true);
        when(regulationService.delete(44L)).thenReturn(true);

        assertOk(new CaseController(caseService).delete(42L));
        assertOk(new KnowledgeController(knowledgeService).delete(43L));
        assertOk(new RegulationController(regulationService).delete(44L));
    }

    @Test
    void missingRecordsReturnHttpNotFound() {
        when(caseService.delete(999L)).thenReturn(false);

        ResponseEntity<R<Void>> response =
                new CaseController(caseService).delete(999L);

        assertEquals(404, response.getStatusCode().value());
        assertEquals(404, response.getBody().getCode());
    }

    private static void assertOk(ResponseEntity<R<Void>> response) {
        assertEquals(200, response.getStatusCode().value());
        assertEquals(200, response.getBody().getCode());
    }
}
