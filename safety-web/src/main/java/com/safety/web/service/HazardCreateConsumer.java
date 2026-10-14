package com.safety.web.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.dto.HazardCreateMessage;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.service.HazardService;
import io.micrometer.core.instrument.MeterRegistry;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;

/**
 * 消费 AI 建单消息，幂等写 tb_hazard，成功后回执。
 *
 * 失败处理：抛 RuntimeException -> listener 重试（max-attempts=3）-> 耗尽后
 * MessageRecoverer 回 FAILED + 丢 DLQ。重复消息不报错（createAi 按 request_id 幂等）。
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class HazardCreateConsumer {

    private final HazardService hazardService;
    private final HazardCreateResultPublisher publisher;
    private final ObjectMapper objectMapper;
    private final MeterRegistry meterRegistry;

    @RabbitListener(queues = "${hazard.create.queue}")
    public void onMessage(Message message) {
        HazardCreateMessage msg;
        try {
            String body = new String(message.getBody(), StandardCharsets.UTF_8);
            msg = objectMapper.readValue(body, HazardCreateMessage.class);
        } catch (Exception e) {
            // body 不合法：重试也没有意义，直接进 DLQ
            throw fail("invalid hazard create payload", e);
        }
        if (msg.getRequestId() == null || msg.getRequestId().isBlank()) {
            throw fail("missing requestId", null);
        }
        if (msg.getUserId() == null) {
            throw fail("missing userId", null);
        }
        if (msg.getCategory() == null || msg.getCategory().isBlank()) {
            throw fail("missing category", null);
        }

        AiHazardDTO dto = new AiHazardDTO();
        dto.setRequestId(msg.getRequestId());
        dto.setUserId(msg.getUserId());
        dto.setCategory(msg.getCategory());
        dto.setCategoryList(msg.getCategoryList());
        dto.setAddress(msg.getAddress());
        dto.setDistrict(msg.getDistrict());
        dto.setLongitude(msg.getLongitude());
        dto.setLatitude(msg.getLatitude());
        dto.setDescription(msg.getDescription());
        dto.setSeverity(msg.getSeverity());
        dto.setImageUrl(msg.getImageUrl());
        dto.setReport(msg.getReport());

        try {
            // 写库失败 -> 抛 RuntimeException -> 交给重试/DLQ
            HazardVO vo = hazardService.createAi(dto);
            publisher.succeeded(msg.getRequestId(), vo == null ? null : vo.getId());
            meterRegistry.counter("hazard_create_consume_success_total").increment();
            log.info("hazard created from MQ request_id={} hazard_id={}",
                    msg.getRequestId(), vo == null ? null : vo.getId());
        } catch (RuntimeException e) {
            meterRegistry.counter("hazard_create_consume_failure_total").increment();
            throw e;
        }
    }

    private RuntimeException fail(String message, Throwable cause) {
        meterRegistry.counter("hazard_create_consume_failure_total").increment();
        return new AmqpRejectAndDontRequeueException(message, cause);
    }
}
