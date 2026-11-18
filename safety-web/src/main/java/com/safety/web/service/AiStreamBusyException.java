package com.safety.web.service;

public class AiStreamBusyException extends RuntimeException {

    public AiStreamBusyException() {
        super("当前服务繁忙，请稍后重试");
    }

    public AiStreamBusyException(Throwable cause) {
        super("当前服务繁忙，请稍后重试", cause);
    }
}
