package com.safety.web.controller;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.prepost.PreAuthorize;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class UserControllerAuthorizationTest {

    @Test
    void handlerDirectoryRequiresAdmin() throws Exception {
        PreAuthorize annotation = UserController.class
                .getMethod("handlers")
                .getAnnotation(PreAuthorize.class);
        assertNotNull(annotation);
        assertEquals("hasRole('ADMIN')", annotation.value());
    }
}
