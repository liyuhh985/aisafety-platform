package com.safety.web.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.extern.slf4j.Slf4j;
import com.safety.web.service.HazardCreateResultPublisher;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.core.QueueBuilder;
import org.springframework.amqp.core.TopicExchange;
import org.springframework.amqp.rabbit.retry.MessageRecoverer;
import org.springframework.amqp.support.converter.Jackson2JsonMessageConverter;
import org.springframework.amqp.support.converter.MessageConverter;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * AI 建任务 MQ 拓扑。与 Python tools/hazard_create_queue.RabbitPublisher._declare_topology
 * 声明完全一致（幂等；两边参数不一致会 406）。
 *
 * MQ 是唯一建单路径，Rabbit 配置总是加载（旧同步链路已删除）。
 */
@Slf4j
@Configuration
public class RabbitConfig {

    @Bean
    public TopicExchange hazardCreateExchange(@Value("${hazard.create.exchange}") String name) {
        return new TopicExchange(name, true, false);
    }

    @Bean
    public TopicExchange hazardCreateDlx(@Value("${hazard.create.dlx}") String name) {
        return new TopicExchange(name, true, false);
    }

    @Bean
    public Queue hazardCreateQueue(@Value("${hazard.create.queue}") String name,
                                   @Value("${hazard.create.dlx}") String dlx) {
        return QueueBuilder.durable(name)
                .withArgument("x-dead-letter-exchange", dlx)
                .build();
    }

    @Bean
    public Binding hazardCreateBinding(Queue hazardCreateQueue, TopicExchange hazardCreateExchange,
                                       @Value("${hazard.create.routing-key}") String routingKey) {
        return BindingBuilder.bind(hazardCreateQueue).to(hazardCreateExchange).with(routingKey);
    }

    @Bean
    public Queue hazardCreateDlq(@Value("${hazard.create.dlq}") String name) {
        return QueueBuilder.durable(name).build();
    }

    @Bean
    public Binding hazardCreateDlqBinding(Queue hazardCreateDlq, TopicExchange hazardCreateDlx) {
        return BindingBuilder.bind(hazardCreateDlq).to(hazardCreateDlx).with("#");
    }

    @Bean
    public Queue hazardResultQueue(@Value("${hazard.create.result-queue}") String name,
                                   @Value("${hazard.create.dlx}") String dlx) {
        return QueueBuilder.durable(name)
                .withArgument("x-dead-letter-exchange", dlx)
                .build();
    }

    @Bean
    public Binding hazardResultBinding(Queue hazardResultQueue, TopicExchange hazardCreateExchange,
                                       @Value("${hazard.create.result-routing-key}") String routingKey) {
        return BindingBuilder.bind(hazardResultQueue).to(hazardCreateExchange).with(routingKey);
    }

    /** 只给 RabbitTemplate 发布用；消费端拿原始 Message 自己解析（Python 发的 body 无 content_type）。 */
    @Bean
    public MessageConverter jsonMessageConverter() {
        return new Jackson2JsonMessageConverter();
    }

    /**
     * 重试耗尽后的兜底：回一条 FAILED 给 Python，再把消息丢进 DLQ。
     * 抛 AmqpRejectAndDontRequeueException 与内置 RejectAndDontRequeueRecoverer 同语义。
     */
    @Bean
    public MessageRecoverer hazardCreateMessageRecoverer(
            HazardCreateResultPublisher publisher, ObjectMapper objectMapper) {
        return (message, cause) -> {
            String requestId = null;
            try {
                requestId = objectMapper.readTree(message.getBody()).path("requestId").asText(null);
            } catch (Exception ignored) {
                // body 不是合法 JSON，requestId 取不到 → 只丢 DLQ
            }
            try {
                publisher.failed(requestId, cause == null ? "unknown" : cause.getMessage());
            } catch (RuntimeException publishError) {
                // 回执失败不能阻止原消息进 DLQ；request 由超时对账兜底。
                log.error("[ALERT] hazard create failed-result publish failed request_id={}", requestId, publishError);
            }
            throw new AmqpRejectAndDontRequeueException("hazard create exhausted retries", cause);
        };
    }
}


