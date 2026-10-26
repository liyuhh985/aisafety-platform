package com.safety.web.controller;

import com.safety.pojo.entity.FileAsset;
import com.safety.service.service.FileAssetService;
import com.safety.service.service.FileUploadService;
import org.junit.jupiter.api.Test;
import org.springframework.http.ResponseEntity;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class FileControllerTest {

    @Test
    void unknownLegacySizeUsesChunkedResponseInsteadOfZeroContentLength() {
        FileAssetService assets = mock(FileAssetService.class);
        FileUploadService uploads = mock(FileUploadService.class);
        FileAsset asset = new FileAsset();
        asset.setId(9L);
        asset.setUserId(1L);
        asset.setBucket("safety-images");
        asset.setObjectKey("legacy.png");
        asset.setContentType("image/png");
        asset.setSizeBytes(0L);
        when(assets.requireReadable(9L, 2L, false)).thenReturn(asset);

        FileController controller = new FileController(assets, uploads);
        var auth = new UsernamePasswordAuthenticationToken(
                2L, null, List.of(new SimpleGrantedAuthority("ROLE_USER")));

        ResponseEntity<?> response = controller.read(9L, auth);

        assertEquals(-1, response.getHeaders().getContentLength());
    }
}
