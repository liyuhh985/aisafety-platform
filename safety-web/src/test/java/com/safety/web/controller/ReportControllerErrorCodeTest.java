package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.pojo.entity.HazardReport;
import com.safety.service.service.ReportService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ReportControllerErrorCodeTest {

    @Mock
    private ReportService reportService;

    @Test
    void missingReportReturnsNotFoundCode() {
        when(reportService.getById(99L, 7L)).thenReturn(null);

        R<HazardReport> response =
                new ReportController(reportService).detail(99L, authentication(7L));

        assertEquals(404, response.getCode());
    }

    private static Authentication authentication(Long userId) {
        return new UsernamePasswordAuthenticationToken(userId, null, List.of());
    }
}
