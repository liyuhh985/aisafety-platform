package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.result.R;
import com.safety.pojo.entity.Regulation;
import com.safety.service.service.RegulationService;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/regulation")
@RequiredArgsConstructor
public class RegulationController {

    private final RegulationService regulationService;

    @GetMapping
    public R<Page<Regulation>> list(
            @RequestParam(defaultValue = "1") int current,
            @RequestParam(defaultValue = "20") int size,
            @RequestParam(required = false) String category) {
        return R.ok(regulationService.page(current, size, category));
    }

    @GetMapping("/{id:\\d+}")
    public R<Regulation> detail(@PathVariable Long id) {
        Regulation r = regulationService.getById(id);
        if (r == null) return R.fail("法规不存在");
        return R.ok(r);
    }
}
