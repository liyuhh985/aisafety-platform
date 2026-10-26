package com.safety.web.controller;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.vo.HazardMapVO;
import com.safety.service.service.HazardService;
import com.safety.web.service.AiService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mock;
import org.mockito.MockitoAnnotations;
import org.springframework.security.core.Authentication;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class HazardControllerAuthorizationTest {

    @Mock
    private HazardService hazardService;
    @Mock
    private AiService aiService;
    @Mock
    private Authentication authentication;

    private HazardController controller;

    @BeforeEach
    void setUp() {
        MockitoAnnotations.openMocks(this);
        controller = new HazardController(hazardService, aiService);
    }

    @Test
    void hazardListDefensivelyRejectsAnonymousCaller() {
        BusinessException error = assertThrows(BusinessException.class,
                () -> controller.page(1, 10, null));
        assertEquals(401, error.getCode());
    }

    @Test
    void hazardDetailDefensivelyRejectsAnonymousCaller() {
        BusinessException error = assertThrows(BusinessException.class,
                () -> controller.getById(1L, null));
        assertEquals(401, error.getCode());
    }

    @Test
    void mapEndpointIsAnonymousAndReturnsOnlyMapProjection() {
        HazardMapVO point = HazardMapVO.builder().id(1L).status(0).build();
        when(hazardService.getMap(100)).thenReturn(List.of(point));

        var response = controller.map(100);

        assertEquals(1, response.getData().size());
        verify(hazardService).getMap(100);
    }
}