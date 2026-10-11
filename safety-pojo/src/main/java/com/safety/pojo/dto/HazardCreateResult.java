package com.safety.pojo.dto;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/** 建单回执（Java 生产，Python 消费）。 */
@Data
@NoArgsConstructor
@AllArgsConstructor
public class HazardCreateResult {
    private String requestId;
    /** SUCCESS / FAILED */
    private String status;
    private Long hazardId;
    private String message;
}