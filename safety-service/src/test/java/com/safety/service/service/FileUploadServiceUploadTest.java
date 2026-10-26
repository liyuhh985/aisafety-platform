package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.FileAsset;
import com.safety.pojo.vo.FileUploadVO;
import io.minio.MinioClient;
import io.minio.PutObjectArgs;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyLong;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class FileUploadServiceUploadTest {

    private static final Long USER_ID = 7L;
    private static final String BUCKET = "safety-images";

    @Mock
    private MinioClient minioClient;
    @Mock
    private FileAssetService fileAssetService;

    private FileUploadService service;

    @BeforeEach
    void setUp() {
        service = new FileUploadService(minioClient, BUCKET, fileAssetService);
    }

    @Test
    void uploadsDecodedImageAndRegistersOwnedMetadata() throws Exception {
        MockMultipartFile file = imageFile();
        FileAsset asset = new FileAsset();
        asset.setId(99L);
        asset.setBucket(BUCKET);
        asset.setObjectKey("generated.png");
        when(fileAssetService.register(eq(USER_ID), anyString(), eq("scene.png"),
                eq("image/png"), anyLong())).thenReturn(asset);
        when(fileAssetService.accessPath(asset))
                .thenReturn("/api/files/99");

        FileUploadVO result = service.upload(USER_ID, file);

        assertEquals(99L, result.getFileId());
        assertEquals("generated.png", result.getObjectKey());
        assertEquals("/api/files/99", result.getUrl());
        verify(minioClient).putObject(any(PutObjectArgs.class));
    }

    @Test
    void rejectsNonImageEvenIfClientContentTypeClaimsImage() {
        MockMultipartFile fake = new MockMultipartFile(
                "file", "fake.png", "image/png", "not-an-image".getBytes());

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.upload(USER_ID, fake));

        assertEquals(400, e.getCode());
    }

    @Test
    void rejectsOversizedPixelDimensions() throws Exception {
        BufferedImage image = new BufferedImage(8001, 1, BufferedImage.TYPE_INT_RGB);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(image, "png", out);
        MockMultipartFile file = new MockMultipartFile(
                "file", "wide.png", "image/png", out.toByteArray());

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.upload(USER_ID, file));

        assertEquals(400, e.getCode());
    }
    @Test
    void rejectsWebpContainerThatHasNoVerifiedDecoder() {
        byte[] fakeWebp = new byte[]{
                'R','I','F','F', 20,0,0,0, 'W','E','B','P', 'V','P','8',' ',
                1,2,3,4,5,6,7,8
        };
        MockMultipartFile file = new MockMultipartFile(
                "file", "fake.webp", "image/webp", fakeWebp);

        BusinessException e = assertThrows(BusinessException.class,
                () -> service.upload(USER_ID, file));

        assertEquals(400, e.getCode());
    }
    private static MockMultipartFile imageFile() throws Exception {
        BufferedImage image = new BufferedImage(2, 2, BufferedImage.TYPE_INT_RGB);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        ImageIO.write(image, "png", out);
        return new MockMultipartFile("file", "scene.png", "application/octet-stream", out.toByteArray());
    }
}



