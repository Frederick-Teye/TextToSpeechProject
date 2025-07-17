from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from document_processing.utils import upload_to_s3


class UploadToS3Tests(TestCase):

    @patch("document_processing.utils.default_storage")
    def test_upload_success_uses_uuid(self, mock_storage):
        dummy = SimpleUploadedFile("foo.txt", b"bar")
        # We expect the function to return the value from `default_storage.save`
        mock_storage.save.return_value = "uploads/1/some-uuid_foo.txt"

        path = upload_to_s3(dummy, user_id=1, file_name="foo.txt")

        # Assert that the final path is what the mocked storage returned
        self.assertEqual(path, "uploads/1/some-uuid_foo.txt")
        # Assert that the save method was called once
        mock_storage.save.assert_called_once()

    @patch("document_processing.utils.default_storage")
    def test_upload_failure_raises_exception(self, mock_storage):
        dummy = SimpleUploadedFile("foo.txt", b"bar")
        # Configure the mock to raise an exception when called
        mock_storage.save.side_effect = Exception("S3 is down")

        # Assert that calling the function raises an exception
        with self.assertRaises(Exception):
            upload_to_s3(dummy, user_id=1, file_name="foo.txt")
