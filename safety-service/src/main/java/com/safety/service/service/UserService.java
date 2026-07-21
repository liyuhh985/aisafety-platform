package com.safety.service.service;

import com.safety.pojo.dto.LoginDTO;
import com.safety.pojo.dto.RegisterDTO;
import com.safety.pojo.vo.LoginVO;
import com.safety.pojo.vo.UserVO;

public interface UserService {
    LoginVO login(LoginDTO dto);
    LoginVO register(RegisterDTO dto);
    UserVO getUserById(Long id);
}
