package com.safety.web;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(scanBasePackages = "com.safety")
@MapperScan("com.safety.**.mapper")
public class SafetyApplication {
    public static void main(String[] args) {
        SpringApplication.run(SafetyApplication.class, args);
    }
}
