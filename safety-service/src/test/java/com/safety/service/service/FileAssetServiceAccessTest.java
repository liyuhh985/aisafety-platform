package com.safety.service.service;

import com.safety.common.exception.BusinessException;
import com.safety.pojo.entity.FileAsset;
import com.safety.service.mapper.FileAssetMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class FileAssetServiceAccessTest {

    @Mock
    private FileAssetMapper mapper;

    @Test
    void attachedFileCanBeReadByAnyAuthenticatedUser() {
        FileAsset asset = new FileAsset();
        asset.setId(9L);
        asset.setUserId(1L);
        asset.setStatus(FileAssetService.STATUS_ATTACHED);
        when(mapper.selectById(9L)).thenReturn(asset);

        FileAssetService service = new FileAssetService(mapper);

        assertEquals(9L, service.requireReadable(9L, 2L).getId());
    }

    @Test
    void temporaryFileCannotBeReadByAnotherUser() {
        FileAsset asset = new FileAsset();
        asset.setId(9L);
        asset.setUserId(1L);
        asset.setStatus(FileAssetService.STATUS_TEMP);
        when(mapper.selectById(9L)).thenReturn(asset);

        FileAssetService service = new FileAssetService(mapper);

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.requireReadable(9L, 2L));
        assertEquals(404, error.getCode());
    }
    @Test
    void privateAttachedFileIsNotReadableByAnotherOrdinaryUser() {
        FileAsset asset = new FileAsset();
        asset.setId(9L);
        asset.setUserId(1L);
        asset.setStatus(FileAssetService.STATUS_ATTACHED);
        asset.setVisibility(FileAssetService.VISIBILITY_PRIVATE);
        when(mapper.selectById(9L)).thenReturn(asset);

        FileAssetService service = new FileAssetService(mapper);

        BusinessException error = assertThrows(BusinessException.class,
                () -> service.requireReadable(9L, 2L, false));
        assertEquals(404, error.getCode());
    }

    @Test
    void privateAttachedFileIsReadableByOwnerOrAdmin() {
        FileAsset asset = new FileAsset();
        asset.setId(9L);
        asset.setUserId(1L);
        asset.setStatus(FileAssetService.STATUS_ATTACHED);
        asset.setVisibility(FileAssetService.VISIBILITY_PRIVATE);
        when(mapper.selectById(9L)).thenReturn(asset);

        FileAssetService service = new FileAssetService(mapper);

        assertEquals(9L, service.requireReadable(9L, 1L, false).getId());
        assertEquals(9L, service.requireReadable(9L, 2L, true).getId());
    }}

