package com.safety.web.service;

import com.safety.pojo.dto.HazardCreateResult;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;

class HazardCreateResultPublisherTest {

    @Test
    void sendFailurePropagates() {
        RabbitTemplate template = mock(RabbitTemplate.class);
        doThrow(new RuntimeException("rabbit down"))
                .when(template)
                .convertAndSend(eq("safety.hazard"), eq("hazard.create.result"),
                        any(HazardCreateResult.class));

        HazardCreateResultPublisher publisher = new HazardCreateResultPublisher(template, new SimpleMeterRegistry());
        ReflectionTestUtils.setField(publisher, "exchange", "safety.hazard");
        ReflectionTestUtils.setField(publisher, "routingKey", "hazard.create.result");

        assertThrows(RuntimeException.class, () -> publisher.succeeded("req-1", 61L));
    }
}

