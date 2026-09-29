import io
import unittest

from fastapi import HTTPException
from PIL import Image

import server


class Upload:
    def __init__(self, payload):
        self.file = io.BytesIO(payload)


class ServerUploadValidationTest(unittest.TestCase):
    def test_rejects_images_that_exceed_pixel_limit(self):
        image = Image.new("RGB", (4000, 4000), "white")
        payload = io.BytesIO()
        image.save(payload, format="JPEG", quality=1, optimize=True)

        with self.assertRaises(HTTPException) as raised:
            server._save_upload(Upload(payload.getvalue()))

        self.assertEqual(raised.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
