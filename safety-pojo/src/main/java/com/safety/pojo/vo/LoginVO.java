package com.safety.pojo.vo;

import lombok.Builder;
import lombok.Data;

@Data
@Builder
public class LoginVO {
    private String token;
    private Long userId;
    private String nickname;
    private String avatar;
    private Integer role;  // 0=普通用户, 1=管理员
}
