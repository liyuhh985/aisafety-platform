package com.safety.web.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.safety.pojo.dto.AiHazardDTO;
import com.safety.pojo.vo.HazardVO;
import com.safety.service.service.HazardService;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.AmqpRejectAndDontRequeueException;
import org.springframework.amqp.core.Message;

import java.nio.charset.StandardCharsets;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class HazardCreateConsumerTest {

    @Test
    void resultPublishFailureIsNotSwallowed() throws Exception {
        HazardService service = mock(HazardService.class);
        HazardCreateResultPublisher publisher = mock(HazardCreateResultPublisher.class);
        HazardVO vo = HazardVO.builder().id(61L).build();
        when(service.createAi(any(AiHazardDTO.class))).thenReturn(vo);
        doThrow(new RuntimeException("rabbit down")).when(publisher).succeeded("req-1", 61L);

        HazardCreateConsumer consumer = new HazardCreateConsumer(service, publisher, new ObjectMapper(), new SimpleMeterRegistry());
        String body = "{\"requestId\":\"req-1\",\"userId\":1,\"category\":\"fire/fire_lane_blocked\"}";
        Message message = new Message(body.getBytes(StandardCharsets.UTF_8));

        assertThrows(RuntimeException.class, () -> consumer.onMessage(message));
    }

    @Test
    void missingRequestIdIsRejectedWithoutRequeue() {
        HazardService service = mock(HazardService.class);
        HazardCreateResultPublisher publisher = mock(HazardCreateResultPublisher.class);
        HazardCreateConsumer consumer = new HazardCreateConsumer(service, publisher, new ObjectMapper(), new SimpleMeterRegistry());
        String body = "{\"userId\":1,\"category\":\"fire/fire_lane_blocked\"}";
        Message message = new Message(body.getBytes(StandardCharsets.UTF_8));

        assertThrows(AmqpRejectAndDontRequeueException.class, () -> consumer.onMessage(message));
    }

    @Test
    void duplicateMessagePublishesSameHazardId() {
        HazardService service = mock(HazardService.class);
        HazardCreateResultPublisher publisher = mock(HazardCreateResultPublisher.class);
        HazardVO vo = HazardVO.builder().id(61L).build();
        when(service.createAi(any(AiHazardDTO.class))).thenReturn(vo);

        HazardCreateConsumer consumer = new HazardCreateConsumer(service, publisher, new ObjectMapper(), new SimpleMeterRegistry());
        String body = "{\"requestId\":\"req-1\",\"userId\":1,\"category\":\"fire/fire_lane_blocked\"}";
        Message message = new Message(body.getBytes(StandardCharsets.UTF_8));

        consumer.onMessage(message);
        consumer.onMessage(message);

        verify(publisher, times(2)).succeeded("req-1", 61L);
    }
    @Test
    void imageFileIdIsForwardedToHazardCreation() {
        HazardService service = mock(HazardService.class);
        HazardCreateResultPublisher publisher = mock(HazardCreateResultPublisher.class);
        when(service.createAi(any(AiHazardDTO.class))).thenReturn(HazardVO.builder().id(61L).build());
        HazardCreateConsumer consumer = new HazardCreateConsumer(
                service, publisher, new ObjectMapper(), new SimpleMeterRegistry());
        String body = "{\"requestId\":\"req-img\",\"userId\":1,"
                + "\"category\":\"fire/fire_lane_blocked\",\"imageFileId\":88}";
        Message message = new Message(body.getBytes(StandardCharsets.UTF_8));

        consumer.onMessage(message);

        org.mockito.ArgumentCaptor<AiHazardDTO> captor =
                org.mockito.ArgumentCaptor.forClass(AiHazardDTO.class);
        verify(service).createAi(captor.capture());
        org.junit.jupiter.api.Assertions.assertEquals(88L, captor.getValue().getImageFileId());
    }}


