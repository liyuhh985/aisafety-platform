package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.result.R;
import com.safety.pojo.entity.HazardKnowledge;
import com.safety.service.service.KnowledgeService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/knowledge")
@RequiredArgsConstructor
public class KnowledgeController {

    private final KnowledgeService knowledgeService;

    /** 政府文书列表（分页 + 地区筛选 + 类别筛选） */
    @GetMapping
    public R<Page<HazardKnowledge>> list(
            @RequestParam(defaultValue = "1") int current,
            @RequestParam(defaultValue = "10") int size,
            @RequestParam(required = false) String region,
            @RequestParam(required = false) String category) {
        return R.ok(knowledgeService.page(current, size, region, category));
    }

    /** 文书详情 */
    @GetMapping("/{id:\\d+}")
    public R<HazardKnowledge> detail(@PathVariable Long id) {
        HazardKnowledge k = knowledgeService.getById(id);
        if (k == null) return R.fail(404, "文书不存在");
        return R.ok(k);
    }

    @PreAuthorize("hasRole('ADMIN')")
    @DeleteMapping("/{id:\\d+}")
    public ResponseEntity<R<Void>> delete(@PathVariable Long id) {
        if (!knowledgeService.delete(id)) {
            return ResponseEntity.status(404).body(R.fail(404, "Knowledge not found"));
        }
        return ResponseEntity.ok(R.ok());
    }
}
