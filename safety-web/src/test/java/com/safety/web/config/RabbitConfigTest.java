package com.safety.web.config;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Queue;

import static org.junit.jupiter.api.Assertions.assertEquals;

class RabbitConfigTest {

    @Test
    void resultQueueCarriesDeadLetterExchange() {
        Queue queue = new RabbitConfig()
                .hazardResultQueue("hazard.create.result.q", "safety.hazard.dlx");

        assertEquals("safety.hazard.dlx", queue.getArguments().get("x-dead-letter-exchange"));
    }
}
