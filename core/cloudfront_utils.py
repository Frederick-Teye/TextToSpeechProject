"""
CloudFront signed URL generation utility.

Provides functions to generate time-limited, signed URLs for accessing
private content through CloudFront distributions. Signed URLs are secure,
time-limited URLs that allow temporary access to private S3 content
through CloudFront without requiring AWS credentials.

Security Features:
- URLs expire after specified time
- Cryptographically signed with CloudFront key pair
- IP restriction available (if needed)
- Policy-based access control
"""

import base64
import hashlib
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from django.conf import settings
from django.core.cache import cache
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.backends import default_backend
from botocore.signers import CloudFrontSigner

logger = logging.getLogger(__name__)


class CloudFrontSigningError(Exception):
    """Exception raised when CloudFront URL signing fails."""

    pass


def _load_private_key(private_key_str: str):
    """
    Load a CloudFront private key from PEM format string.
    Handles keys stored in environment variables with escaped newlines.

    Args:
        private_key_str: Private key in PEM format

    Returns:
        Loaded private key object

    Raises:
        CloudFrontSigningError: If key cannot be loaded
    """
    try:
        # Replace escaped newlines with actual newlines for PEM parsing
        # This is crucial for keys stored in .env files
        formatted_key = private_key_str.replace("\\n", "\n")

        if isinstance(formatted_key, str):
            formatted_key = formatted_key.encode()

        return load_pem_private_key(
            formatted_key, password=None, backend=default_backend()
        )
    except Exception as e:
        logger.error(f"Failed to load CloudFront private key: {str(e)}")
        raise CloudFrontSigningError(f"Invalid private key: {str(e)}")


def _create_policy(resource_url: str, expiration_seconds: int) -> str:
    """
    Create a CloudFront access control policy.

    Args:
        resource_url: Full URL to the resource (including CloudFront domain)
        expiration_seconds: How many seconds the URL is valid

    Returns:
        Base64-encoded policy string
    """
    expire_time = int(time.time()) + expiration_seconds

    policy = {
        "Statement": [
            {
                "Resource": resource_url,
                "Condition": {"DateLessThan": {"AWS:EpochTime": expire_time}},
            }
        ]
    }

    policy_json = json.dumps(policy, separators=(",", ":"))
    policy_b64 = base64.b64encode(policy_json.encode()).decode()

    return policy_b64


def _sign_policy(policy_b64: str, private_key_str: str) -> str:
    """
    Sign a policy with the CloudFront private key using RSA-SHA1.

    Args:
        policy_b64: Base64-encoded policy string
        private_key_str: Private key in PEM format

    Returns:
        Base64-encoded signature

    Raises:
        CloudFrontSigningError: If signing fails
    """
    try:
        private_key = _load_private_key(private_key_str)

        # Sign the policy with RSA-SHA1 (CloudFront requirement)
        signature = private_key.sign(
            policy_b64.encode(), padding.PKCS1v15(), hashes.SHA1()
        )

        # Encode signature to URL-safe base64
        signature_b64 = base64.urlsafe_b64encode(signature).decode()

        return signature_b64
    except CloudFrontSigningError:
        raise
    except Exception as e:
        logger.error(f"Failed to sign CloudFront policy: {str(e)}")
        raise CloudFrontSigningError(f"Policy signing failed: {str(e)}")


def _botocore_signed_url(
    resource_path: str, domain: str, expiration_seconds: int
) -> str:
    """Generate a CloudFront signed URL using botocore's CloudFrontSigner (canned policy)."""
    try:
        # Ensure there is always one slash between domain and path
        url = f"https://{domain}/{resource_path}"
        print(url)

        # Prepare the RSA signer from the PEM key
        private_key_obj = _load_private_key(settings.CLOUDFRONT_PRIVATE_KEY)

        def rsa_signer(message: bytes) -> bytes:
            return private_key_obj.sign(message, padding.PKCS1v15(), hashes.SHA1())

        signer = CloudFrontSigner(settings.CLOUDFRONT_KEY_ID, rsa_signer)
        expires = datetime.utcnow() + timedelta(seconds=expiration_seconds)
        return signer.generate_presigned_url(url, date_less_than=expires)
    except Exception as e:
        logger.error(f"Botocore signing failed: {e}")
        raise CloudFrontSigningError(f"Botocore signing failed: {e}")


def get_audio_signed_url(
    audio_object, expiration_seconds: Optional[int] = None, use_cache: bool = True
) -> str:
    """
    Get a signed CloudFront URL for an Audio object.

    Generates a secure, time-limited URL for accessing user-generated audio
    through CloudFront. Results are cached to reduce computational overhead.

    Args:
        audio_object: Audio model instance with s3_key attribute
        expiration_seconds: URL validity in seconds (default: from settings)
        use_cache: Whether to cache the URL (default: True)

    Returns:
        Signed CloudFront URL for the audio file

    Raises:
        CloudFrontSigningError: If URL generation fails
        AttributeError: If audio_object doesn't have s3_key attribute

    Example:
        >>> audio = Audio.objects.get(id=1)
        >>> signed_url = get_audio_signed_url(audio)
    """
    try:
        # Validate configuration
        if not all(
            [
                settings.CLOUDFRONT_DOMAIN,
                settings.CLOUDFRONT_KEY_ID,
                settings.CLOUDFRONT_PRIVATE_KEY,
            ]
        ):
            error_msg = "CloudFront configuration incomplete in settings"
            logger.error(error_msg)
            raise CloudFrontSigningError(error_msg)

        # Use default expiration if not specified
        if expiration_seconds is None:
            expiration_seconds = settings.CLOUDFRONT_EXPIRATION

        # Check cache first (if enabled)
        if use_cache:
            cache_key = f"audio_signed_url_{audio_object.id}_{expiration_seconds}"
            cached_url = cache.get(cache_key)
            if cached_url:
                logger.debug(f"Using cached signed URL for audio {audio_object.id}")
                return cached_url

        # Get the S3 key from the audio object
        if not hasattr(audio_object, "s3_key") or not audio_object.s3_key:
            raise CloudFrontSigningError(f"Audio {audio_object.id} has no S3 key")

        # The resource path is the S3 key, without any leading slash.
        resource_path = audio_object.s3_key

        # Generate signed URL via botocore (canned policy)
        signed_url = _botocore_signed_url(
            resource_path=resource_path,
            domain=settings.CLOUDFRONT_DOMAIN,
            expiration_seconds=expiration_seconds,
        )

        # Cache the URL (cache for a bit less than expiration time)
        if use_cache:
            cache_timeout = expiration_seconds - 60  # Refresh 1 min before expiry
            cache_key = f"audio_signed_url_{audio_object.id}_{expiration_seconds}"
            cache.set(cache_key, signed_url, cache_timeout)

        logger.info(f"Generated signed URL for audio {audio_object.id}")
        return signed_url

    except CloudFrontSigningError:
        raise
    except Exception as e:
        logger.error(
            f"Failed to create signed URL for audio {audio_object.id}: {str(e)}"
        )
        raise CloudFrontSigningError(f"Failed to generate audio URL: {str(e)}")


def invalidate_audio_cache(audio_id: int) -> None:
    """
    Invalidate cached signed URL for an audio object.

    Call this when an audio file is deleted or modified to ensure
    the URL doesn't remain cached incorrectly.

    Args:
        audio_id: ID of the audio object
    """
    try:
        # Clear all cached variants of this URL
        for expiration in [3600, 7200]:  # Common expiration times
            cache_key = f"audio_signed_url_{audio_id}_{expiration}"
            cache.delete(cache_key)
        logger.debug(f"Invalidated signed URL cache for audio {audio_id}")
    except Exception as e:
        logger.warning(f"Failed to invalidate audio cache: {str(e)}")
