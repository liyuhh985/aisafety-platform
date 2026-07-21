package com.safety.pojo.vo;

import lombok.Builder;
import lombok.Data;

import java.time.LocalDateTime;

@Data
@Builder
public class UserVO {
    private Long id;
    private String email;
    private String nickname;
    private String avatar;
    private Integer role;
    private LocalDateTime createTime;
}
