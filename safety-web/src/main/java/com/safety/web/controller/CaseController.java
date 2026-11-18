package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.result.R;
import com.safety.pojo.entity.HazardCase;
import com.safety.service.service.CaseService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/case")
@RequiredArgsConstructor
public class CaseController {

    private final CaseService caseService;

    @GetMapping
    public R<Page<HazardCase>> list(
            @RequestParam(defaultValue = "1") int current,
            @RequestParam(defaultValue = "5") int size,
            @RequestParam(required = false) String city,
            @RequestParam(required = false) String category) {
        return R.ok(caseService.page(current, size, city, category));
    }

    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping("/{id:\\d+}")
    public ResponseEntity<R<Void>> delete(@PathVariable Long id) {
        if (!caseService.delete(id)) {
            return ResponseEntity.status(404).body(R.fail(404, "Case not found"));
        }
        return ResponseEntity.ok(R.ok());
    }
}
