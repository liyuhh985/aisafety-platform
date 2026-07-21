package com.safety.service.mapper;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.safety.pojo.entity.User;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface UserMapper extends BaseMapper<User> {
}
