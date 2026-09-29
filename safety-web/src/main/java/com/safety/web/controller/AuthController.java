package com.safety.web.controller;

import com.safety.common.result.R;
import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.pojo.dto.SendCodeDTO;
import com.safety.pojo.vo.LoginVO;
import com.safety.service.service.MailService;
import com.safety.service.service.UserService;
import com.safety.web.annotation.RateLimit;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/auth")
@RequiredArgsConstructor
public class AuthController {

    private final UserService userService;
    private final MailService mailService;

    @RateLimit(key = "'send_code:' + #dto.email", count = 1, time = 60)
    @PostMapping(value = {"/send-code", "/code"})
    public R<Void> sendCode(@Valid @RequestBody SendCodeDTO dto) {
        mailService.sendCode(dto.getEmail());
        return R.ok();
    }

    @PostMapping("/login")
    public R<LoginVO> login(@Valid @RequestBody LoginDTO dto) {
        return R.ok(userService.login(dto));
    }

    @PostMapping("/register")
    public R<LoginVO> register(@Valid @RequestBody RegisterDTO dto) {
        return R.ok(userService.register(dto));
    }
}
