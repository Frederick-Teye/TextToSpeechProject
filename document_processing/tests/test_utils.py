from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from document_processing.utils import upload_to_s3


class UploadToS3Tests(TestCase):

    @patch("storages.backends.s3boto3.S3Boto3Storage.save")
    def test_upload_success_uses_uuid(self, mock_save):
        mock_save.return_value = "uploads/1/some-uuid_foo.txt"

        dummy = SimpleUploadedFile("foo.txt", b"bar")
        path = upload_to_s3(dummy, user_id=1, file_name="foo.txt")

        self.assertEqual(path, "media/uploads/1/some-uuid_foo.txt")
        mock_save.assert_called_once()

    @patch("storages.backends.s3boto3.S3Boto3Storage.save")
    def test_upload_failure_raises_exception(self, mock_save):
        dummy = SimpleUploadedFile("foo.txt", b"bar")
        # Configure the mock to raise an exception when called
        mock_save.side_effect = Exception("Failed to upload file to S3")

        # Assert that calling the function raises an exception
        with self.assertRaises(Exception):
            upload_to_s3(dummy, user_id=1, file_name="foo.txt")
