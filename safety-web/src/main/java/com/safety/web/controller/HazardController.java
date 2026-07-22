package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.result.R;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.service.HazardService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/hazard")
@RequiredArgsConstructor
public class HazardController {

    private final HazardService hazardService;

    @PostMapping
    public R<HazardVO> create(@Valid @RequestBody HazardDTO dto, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        return R.ok(hazardService.create(userId, dto));
    }

    @GetMapping
    public R<Page<HazardVO>> page(
            @RequestParam(defaultValue = "1") int current,
            @RequestParam(defaultValue = "10") int size) {
        return R.ok(hazardService.page(current, size));
    }

    @GetMapping("/stats")
    public R<HazardStatsVO> stats() {
        return R.ok(hazardService.getStats());
    }

    @GetMapping("/{id:\\d+}")
    public R<HazardVO> getById(@PathVariable Long id) {
        return R.ok(hazardService.getById(id));
    }
}
