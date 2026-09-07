package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.exception.BusinessException;
import com.safety.common.result.R;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.HazardDTO;
import com.safety.pojo.vo.HazardStatsVO;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.service.HazardService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/hazard")
@RequiredArgsConstructor
public class HazardController {

    private final HazardService hazardService;

    @Value("${ai.internal-token:}")
    private String internalToken;

    @PostMapping
    public R<HazardVO> create(@Valid @RequestBody HazardDTO dto, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        return R.ok(hazardService.create(userId, dto));
    }

    /**
     * AI 上报专用入口：由 Python 模块（带 X-Internal-Token）调用，经用户确认后写入 tb_hazard，status=0。
     */
    @PostMapping("/ai")
    public R<HazardVO> createAi(@Valid @RequestBody AiHazardDTO dto,
                                @RequestHeader(value = "X-Internal-Token", required = false) String token) {
        if (internalToken == null || internalToken.isBlank()
                || !internalToken.equals(token)) {
            throw new BusinessException("unauthorized internal call");
        }
        return R.ok(hazardService.createAi(dto));
    }

    @GetMapping
    public R<Page<HazardVO>> page(
            @RequestParam(defaultValue = "1") int current,
            @RequestParam(defaultValue = "10") int size,
            Authentication auth) {
        Long userId = auth == null ? null : (Long) auth.getPrincipal();
        Integer role = roleOf(auth);
        return R.ok(hazardService.page(current, size, userId, role));
    }

    @PostMapping("/{id:\\d+}/accept")
    @PreAuthorize("hasAnyRole('HANDLER','ADMIN')")
    public R<HazardVO> accept(@PathVariable Long id, Authentication auth) {
        return R.ok(hazardService.accept(id, (Long) auth.getPrincipal()));
    }

    @PostMapping("/{id:\\d+}/start")
    @PreAuthorize("hasAnyRole('HANDLER','ADMIN')")
    public R<HazardVO> start(@PathVariable Long id, Authentication auth) {
        return R.ok(hazardService.start(id, (Long) auth.getPrincipal()));
    }

    @PostMapping("/{id:\\d+}/complete")
    @PreAuthorize("hasAnyRole('HANDLER','ADMIN')")
    public R<HazardVO> complete(@PathVariable Long id, Authentication auth) {
        return R.ok(hazardService.complete(id, (Long) auth.getPrincipal()));
    }

    @GetMapping("/stats")
    public R<HazardStatsVO> stats() {
        return R.ok(hazardService.getStats());
    }

    @GetMapping("/{id:\\d+}")
    public R<HazardVO> getById(@PathVariable Long id) {
        return R.ok(hazardService.getById(id));
    }

    /** 从 SecurityContext 推导角色数字：0 普通 / 1 管理员 / 2 处理人员 */
    private Integer roleOf(Authentication auth) {
        if (auth == null) {
            return null;
        }
        boolean admin = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority).anyMatch("ROLE_ADMIN"::equals);
        boolean handler = auth.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority).anyMatch("ROLE_HANDLER"::equals);
        if (admin) {
            return 1;
        }
        if (handler) {
            return 2;
        }
        return 0;
    }
}
