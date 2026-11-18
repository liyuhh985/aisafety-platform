package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.result.R;
import com.safety.pojo.dto.ReportSaveDTO;
import com.safety.pojo.entity.HazardReport;
import com.safety.service.service.ReportService;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/report")
@RequiredArgsConstructor
public class ReportController {

    private final ReportService service;

    @PostMapping
    public R<HazardReport> save(@RequestBody ReportSaveDTO dto, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        return R.ok(service.save(userId, dto));
    }

    @GetMapping
    public R<Page<HazardReport>> list(
            @RequestParam(defaultValue = "1") int current,
            @RequestParam(defaultValue = "10") int size,
            Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        boolean isAdmin = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
        Long queryUserId = isAdmin ? null : userId;
        return R.ok(service.page(queryUserId, current, size));
    }

    @GetMapping("/{id:\\d+}")
    public R<HazardReport> detail(@PathVariable Long id, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        boolean isAdmin = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
        Long queryUserId = isAdmin ? null : userId;
        HazardReport r = service.getById(id, queryUserId);
        if (r == null) return R.fail(404, "报告不存在");
        return R.ok(r);
    }

    @DeleteMapping("/{id:\\d+}")
    public R<Void> delete(@PathVariable Long id, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        boolean isAdmin = auth.getAuthorities().stream()
                .anyMatch(a -> "ROLE_ADMIN".equals(a.getAuthority()));
        Long queryUserId = isAdmin ? null : userId;
        service.delete(id, queryUserId);
        return R.ok();
    }
}
