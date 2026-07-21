package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.vo.FileUploadVO;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
public class FileUploadService {

    private static final Set<String> ALLOWED_TYPES = Set.of(
            "image/jpeg", "image/png", "image/gif", "image/webp");
    private static final long MAX_SIZE = 10 * 1024 * 1024; // 10MB

    private final MinioClient minioClient;

    @Value("${minio.bucket}")
    private String bucket;

    @Value("${minio.base-url}")
    private String baseUrl;

    public FileUploadService(
            @Value("${minio.endpoint}") String endpoint,
            @Value("${minio.access-key}") String accessKey,
            @Value("${minio.secret-key}") String secretKey) {
        this.minioClient = MinioClient.builder()
                .endpoint(endpoint)
                .credentials(accessKey, secretKey)
                .build();
    }

    public FileUploadVO upload(MultipartFile file) {
        if (file.isEmpty()) {
            throw new BusinessException("文件不能为空");
        }
        if (file.getSize() > MAX_SIZE) {
            throw new BusinessException("文件大小不能超过10MB");
        }
        String contentType = file.getContentType();
        if (contentType == null || !ALLOWED_TYPES.contains(contentType)) {
            throw new BusinessException("仅支持 jpg/png/gif/webp 格式");
        }

        String originalName = file.getOriginalFilename();
        String suffix = "";
        if (originalName != null && originalName.contains(".")) {
            suffix = originalName.substring(originalName.lastIndexOf("."));
        }
        String filename = UUID.randomUUID().toString().replace("-", "") + suffix;

        try {
            minioClient.putObject(PutObjectArgs.builder()
                    .bucket(bucket)
                    .object(filename)
                    .stream(file.getInputStream(), file.getSize(), -1)
                    .contentType(contentType)
                    .build());
        } catch (Exception e) {
            log.error("MinIO上传失败", e);
            throw new BusinessException("文件上传失败，请重试");
        }

        String url = baseUrl + "/" + bucket + "/" + filename;
        return FileUploadVO.builder()
                .url(url)
                .filename(filename)
                .build();
    }
}
