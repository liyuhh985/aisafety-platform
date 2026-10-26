package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.pojo.dto.UpdateUserRoleDTO;
import com.safety.service.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/users")
@RequiredArgsConstructor
public class UserController {

    private final UserService userService;

    @PutMapping("/{id:\\d+}/role")
    @PreAuthorize("hasRole('ADMIN')")
    public R<Void> updateRole(@PathVariable Long id,
                              @Valid @RequestBody UpdateUserRoleDTO dto) {
        userService.updateRole(id, dto.getRole());
        return R.ok();
    }
}
