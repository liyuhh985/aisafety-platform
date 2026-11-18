package com.safety.web.service;

import com.safety.pojo.dto.HazardCreateResult;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/** 建单结果回执：Java -> RabbitMQ -> Python 更新 ai_hazard_create_request.status。 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HazardCreateResultPublisher {

    private final RabbitTemplate rabbitTemplate;
    private final MeterRegistry meterRegistry;

    @Value("${hazard.create.exchange}")
    private String exchange;

    @Value("${hazard.create.result-routing-key}")
    private String routingKey;

    public void succeeded(String requestId, Long hazardId) {
        send(new HazardCreateResult(requestId, "SUCCESS", hazardId, "创建成功"));
    }

    public void failed(String requestId, String message) {
        send(new HazardCreateResult(requestId, "FAILED", null, message));
    }

    private void send(HazardCreateResult result) {
        try {
            rabbitTemplate.convertAndSend(exchange, routingKey, result);
            meterRegistry.counter("hazard_create_result_publish_success_total").increment();
        } catch (RuntimeException e) {
            // 不能吞：消费者必须重试，否则 request 会永远停在 PUBLISHED。
            meterRegistry.counter("hazard_create_result_publish_failure_total").increment();
            log.error("[ALERT] hazard create result publish failed: {}", result, e);
            throw e;
        }
    }
}

