package com.safety.service.service.impl;

import com.safety.pojo.dto.LoginDTO;
import com.safety.service.mapper.UserMapper;
import org.apache.ibatis.annotations.Select;
import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

import java.lang.reflect.Method;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UserAuthConcurrencySqlTest {

    @Test
    void loginReadsUserRowUnderDatabaseLock() throws Exception {
        Method mapperMethod = UserMapper.class.getMethod("selectByEmailForUpdate", String.class);
        String sql = String.join(" ", mapperMethod.getAnnotation(Select.class).value());

        assertTrue(sql.contains("FOR UPDATE"));
        assertNotNull(UserServiceImpl.class.getMethod("login", LoginDTO.class)
                .getAnnotation(Transactional.class));
    }

    @Test
    void roleUpdateReadsUserRowUnderDatabaseLock() throws Exception {
        Method mapperMethod = UserMapper.class.getMethod("selectByIdForUpdate", Long.class);
        String sql = String.join(" ", mapperMethod.getAnnotation(Select.class).value());

        assertTrue(sql.contains("FOR UPDATE"));
    }
}
