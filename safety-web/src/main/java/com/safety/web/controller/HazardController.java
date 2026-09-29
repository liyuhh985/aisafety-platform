package com.safety.web.controller;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.safety.common.exception.BusinessException;
import com.safety.common.result.R;
import com.safety.pojo.dto.AiAssignDTO;
import com.safety.pojo.dto.AiBatchReviewDTO;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.AiReviewDTO;
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

    /** 管理员派单：指定处理人，0 待处理 -> 1 已接单 */
    @PostMapping("/{id:\\d+}/assign")
    @PreAuthorize("hasRole('ADMIN')")
    public R<HazardVO> assign(@PathVariable Long id, @Valid @RequestBody AiAssignDTO dto, Authentication auth) {
        return R.ok(hazardService.assign(id, (Long) auth.getPrincipal(), dto.getHandlerId()));
    }

    /** 处理人员认领接单：0 待处理 -> 1 已接单（仅限处突专员） */
    @PostMapping("/{id:\\d+}/accept")
    @PreAuthorize("hasRole('HANDLER')")
    public R<HazardVO> accept(@PathVariable Long id, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        return R.ok(hazardService.assign(id, userId, userId));
    }

    /** 处理人员开始整改：1 -> 2（仅限处突专员） */
    @PostMapping("/{id:\\d+}/start")
    @PreAuthorize("hasRole('HANDLER')")
    public R<HazardVO> start(@PathVariable Long id, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        return R.ok(hazardService.start(id, userId, roleOf(auth)));
    }

    /** 处理人员完成：2 -> 3（仅限处突专员） */
    @PostMapping("/{id:\\d+}/complete")
    @PreAuthorize("hasRole('HANDLER')")
    public R<HazardVO> complete(@PathVariable Long id, Authentication auth) {
        Long userId = (Long) auth.getPrincipal();
        return R.ok(hazardService.complete(id, userId, roleOf(auth)));
    }

    /** 管理员人工审核：通过/驳回 */
    @PostMapping("/{id:\\d+}/review")
    @PreAuthorize("hasRole('ADMIN')")
    public R<HazardVO> review(@PathVariable Long id, @RequestBody AiReviewDTO dto, Authentication auth) {
        return R.ok(hazardService.review(id, (Long) auth.getPrincipal(),
                Boolean.TRUE.equals(dto.getPass()), dto.getRemark()));
    }

    /** 管理员批量审核：通过/驳回 */
    @PostMapping("/batch-review")
    @PreAuthorize("hasRole('ADMIN')")
    public R<java.util.List<HazardVO>> batchReview(@Valid @RequestBody AiBatchReviewDTO dto, Authentication auth) {
        return R.ok(hazardService.batchReview(dto.getIds(), (Long) auth.getPrincipal(),
                Boolean.TRUE.equals(dto.getPass()), dto.getRemark()));
    }

    @GetMapping("/stats")
    public R<HazardStatsVO> stats() {
        return R.ok(hazardService.getStats());
    }

    @GetMapping("/{id:\\d+}")
    public R<HazardVO> getById(@PathVariable Long id, Authentication auth) {
        HazardVO vo = hazardService.getById(id);
        Integer role = roleOf(auth);
        boolean isAdmin = (role != null && role == 1);
        if (vo != null && vo.getStatus() != null && vo.getStatus() == 5 && !isAdmin) {
            // 已撤回只对管理员可见：对其他人等同于不存在
            throw new BusinessException(404, "隐患记录不存在");
        }
        return R.ok(vo);
    }

    /** 撤回：仅创建人本人、仅 status=0（未接单）可撤；不审核。 */
    @PostMapping("/{id:\\d+}/withdraw")
    public R<HazardVO> withdraw(@PathVariable Long id, Authentication auth) {
        if (auth == null) {
            throw new BusinessException(401, "未登录");
        }
        Long userId = (Long) auth.getPrincipal();
        return R.ok(hazardService.withdraw(id, userId));
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
