package com.safety.web.controller;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.FileAsset;
import com.safety.service.service.FileAssetService;
import com.safety.service.service.FileUploadService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import java.io.InputStream;
import java.util.concurrent.TimeUnit;

@RestController
@RequestMapping("/api/files")
@RequiredArgsConstructor
public class FileController {

    private final FileAssetService fileAssetService;
    private final FileUploadService fileUploadService;

    @GetMapping("/{id:\\d+}")
    public ResponseEntity<StreamingResponseBody> read(
            @PathVariable Long id, Authentication authentication) {
        Long userId = (Long) authentication.getPrincipal();
        boolean admin = authentication.getAuthorities().stream()
                .anyMatch(authority -> "ROLE_ADMIN".equals(authority.getAuthority()));
        FileAsset asset;
        try {
            asset = fileAssetService.requireReadable(id, userId, admin);
        } catch (BusinessException e) {
            HttpStatus status = HttpStatus.resolve(e.getCode());
            return ResponseEntity.status(status == null ? HttpStatus.NOT_FOUND : status).build();
        }
        StreamingResponseBody body = output -> {
            try (InputStream input = fileUploadService.openObject(
                    asset.getBucket(), asset.getObjectKey())) {
                input.transferTo(output);
            }
        };
        return ResponseEntity.ok()
                .contentType(contentType(asset.getContentType()))
                .contentLength(asset.getSizeBytes() != null && asset.getSizeBytes() > 0
                        ? asset.getSizeBytes() : -1)
                .cacheControl(CacheControl.noStore())
                .header("X-Content-Type-Options", "nosniff")
                .header("Vary", "Authorization")
                .body(body);
    }

    private static MediaType contentType(String value) {
        try {
            return value == null || value.isBlank()
                    ? MediaType.APPLICATION_OCTET_STREAM
                    : MediaType.parseMediaType(value);
        } catch (IllegalArgumentException e) {
            return MediaType.APPLICATION_OCTET_STREAM;
        }
    }
}






