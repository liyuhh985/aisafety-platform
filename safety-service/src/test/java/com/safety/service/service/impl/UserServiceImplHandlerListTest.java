package com.safety.service.service.impl;

import com.safety.pojo.entity.User;
import com.safety.pojo.vo.UserVO;
import com.safety.service.mapper.UserMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class UserServiceImplHandlerListTest {

    @Test
    void listHandlersReturnsRoleTwoUsers() {
        UserMapper userMapper = mock(UserMapper.class);
        User handler = new User();
        handler.setId(4L);
        handler.setEmail("handler@example.com");
        handler.setNickname("处理员");
        handler.setRole(2);
        when(userMapper.selectList(any())).thenReturn(List.of(handler));
        UserServiceImpl service = new UserServiceImpl(
                userMapper, null, null, null, null);

        List<UserVO> result = service.listHandlers();

        assertEquals(1, result.size());
        assertEquals(4L, result.get(0).getId());
        assertEquals("handler@example.com", result.get(0).getEmail());
        assertEquals(2, result.get(0).getRole());
        verify(userMapper).selectList(any());
    }
}
