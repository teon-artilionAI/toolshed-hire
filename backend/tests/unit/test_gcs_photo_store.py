"""The bucket adapter writes once, signs through IAM, and the switched off store refuses.

The Google client is replaced by a fake bucket that records what it was asked,
so these prove the arguments the adapter hands the client. An upload carries
`if_generation_match=0`, so it can never replace an object and a retry is safe.
A link is V4, five minutes long, a GET, served as an attachment, and signed with
the service account's address and a current token, which is the IAM signBlob
route Cloud Run needs because its credentials hold no private key.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Final

import pytest

from app.domain.damage_photo import PHOTO_LINK_LIFETIME
from app.domain.errors import FeatureSwitchedOff
from app.infrastructure.photo_store import (
    NO_EXISTING_OBJECT,
    UPLOAD_TIMEOUT,
    BlobHandle,
    BucketConnection,
    GcsPhotoStore,
    SigningIdentity,
    SwitchedOffPhotoStore,
    _MetadataSigner,
    build_photo_store,
)
from tests.support.log_capture import LogCapture

BUCKET: Final[str] = "toolshed-test-photos"
KEY: Final[str] = "damage/report/photo.jpg"
RUNTIME_ACCOUNT: Final[str] = "toolshed-api@example-project.iam.gserviceaccount.com"
TOKEN: Final[str] = "ya29.test-token"
SIGNED: Final[str] = f"https://storage.googleapis.com/{BUCKET}/{KEY}?X-Goog-Signature=test"
FILE_NAME: Final[str] = "TSH-D-26-00031-0a1b2c3d.jpg"
RETRY_POLICY: Final[object] = object()


@dataclass
class FakeBlob:
    """One object of the fake bucket, recording every call made on it."""

    name: str
    uploads: list[dict[str, object]] = field(default_factory=list)
    signings: list[dict[str, object]] = field(default_factory=list)
    fail_with: Exception | None = None

    def upload_from_string(
        self,
        data: bytes,
        content_type: str,
        *,
        if_generation_match: int,
        timeout: tuple[float, float],
        retry: object,
    ) -> None:
        """Record the upload, or fail the way the test asked."""
        if self.fail_with is not None:
            raise self.fail_with
        self.uploads.append(
            {
                "data": data,
                "content_type": content_type,
                "if_generation_match": if_generation_match,
                "timeout": timeout,
                "retry": retry,
            }
        )

    def generate_signed_url(
        self,
        *,
        version: str,
        expiration: timedelta,
        method: str,
        response_disposition: str,
        service_account_email: str,
        access_token: str,
    ) -> str:
        """Record the signing and return a fixed URL."""
        self.signings.append(
            {
                "version": version,
                "expiration": expiration,
                "method": method,
                "response_disposition": response_disposition,
                "service_account_email": service_account_email,
                "access_token": access_token,
            }
        )
        return SIGNED


@dataclass
class FakeBucket:
    """A bucket that hands out one recording blob per name."""

    blobs: dict[str, FakeBlob] = field(default_factory=dict)
    fail_with: Exception | None = None

    def blob(self, blob_name: str) -> BlobHandle:
        """Return the recording blob of that name."""
        return self.blobs.setdefault(blob_name, FakeBlob(blob_name, fail_with=self.fail_with))


class FixedSigner:
    """A signer that always hands out the same identity."""

    def current(self) -> SigningIdentity:
        """Return the runtime account and a token."""
        return SigningIdentity(service_account_email=RUNTIME_ACCOUNT, access_token=TOKEN)


@dataclass
class Opener:
    """Opens the fake bucket and counts how often it was asked to."""

    bucket: FakeBucket = field(default_factory=FakeBucket)
    opened: list[str] = field(default_factory=list)

    def __call__(self, bucket_name: str) -> BucketConnection:
        """Return the fake bucket, recording the name it was opened by."""
        self.opened.append(bucket_name)
        return BucketConnection(bucket=self.bucket, signer=FixedSigner(), upload_retry=RETRY_POLICY)


@dataclass
class FakeCredentials:
    """Credentials like those of the metadata server, with a token that runs out."""

    valid: bool = False
    token: str | None = None
    service_account_email: str = "default"
    refreshes: int = 0

    def refresh(self, request: object) -> None:
        """Fetch a token and learn the account's real address, as the metadata server does."""
        self.refreshes += 1
        self.valid = True
        self.token = TOKEN
        self.service_account_email = RUNTIME_ACCOUNT


class TestStoringAPhotograph:
    """Written once, under its own name, bounded in time."""

    def test_the_upload_may_never_replace_an_object(self) -> None:
        opener = Opener()
        store = GcsPhotoStore(BUCKET, open_bucket=opener)

        store.put(KEY, b"pixels", "image/jpeg")

        (upload,) = opener.bucket.blobs[KEY].uploads
        assert upload == {
            "data": b"pixels",
            "content_type": "image/jpeg",
            "if_generation_match": NO_EXISTING_OBJECT,
            "timeout": UPLOAD_TIMEOUT,
            "retry": RETRY_POLICY,
        }
        assert NO_EXISTING_OBJECT == 0

    def test_the_bucket_is_opened_once_and_only_when_first_needed(self) -> None:
        opener = Opener()
        store = GcsPhotoStore(BUCKET, open_bucket=opener)
        assert opener.opened == []

        store.put(KEY, b"one", "image/jpeg")
        store.put("damage/report/other.png", b"two", "image/png")

        assert opener.opened == [BUCKET]
        assert store.switched_on

    def test_a_failed_upload_is_logged_with_its_key_and_raised(
        self, application_log: LogCapture
    ) -> None:
        opener = Opener(bucket=FakeBucket(fail_with=ConnectionError("network unreachable")))
        store = GcsPhotoStore(BUCKET, open_bucket=opener)

        with pytest.raises(ConnectionError):
            store.put(KEY, b"pixels", "image/jpeg")

        failure = application_log.only("damage_photo.store_failed")
        assert failure["object_key"] == KEY
        assert failure["cause"] == "ConnectionError"


class TestSigningALink:
    """V4, five minutes, a download, signed as the runtime account."""

    def test_the_link_is_signed_through_iam_as_the_runtime_account(self) -> None:
        opener = Opener()
        store = GcsPhotoStore(BUCKET, open_bucket=opener)

        url = store.download_link(KEY, file_name=FILE_NAME, lifetime=PHOTO_LINK_LIFETIME)

        assert url == SIGNED
        (signing,) = opener.bucket.blobs[KEY].signings
        assert signing == {
            "version": "v4",
            "expiration": timedelta(minutes=5),
            "method": "GET",
            "response_disposition": f'attachment; filename="{FILE_NAME}"',
            "service_account_email": RUNTIME_ACCOUNT,
            "access_token": TOKEN,
        }

    def test_the_token_is_refreshed_only_when_it_has_expired(self) -> None:
        credentials = FakeCredentials()
        signer = _MetadataSigner(credentials, object)

        first = signer.current()
        second = signer.current()

        assert first == second == SigningIdentity(RUNTIME_ACCOUNT, TOKEN)
        assert credentials.refreshes == 1
        credentials.valid = False
        signer.current()
        assert credentials.refreshes == 2

    def test_credentials_with_no_service_account_cannot_sign(self) -> None:
        credentials = FakeCredentials(valid=True, token=TOKEN, service_account_email="")
        with pytest.raises(RuntimeError, match="no service account"):
            _MetadataSigner(credentials, object).current()


class TestPhotographsSwitchedOff:
    """No bucket, one warning, and every call refused."""

    def test_no_bucket_gives_the_switched_off_store_and_one_warning(
        self, application_log: LogCapture
    ) -> None:
        store = build_photo_store(None)

        assert isinstance(store, SwitchedOffPhotoStore)
        assert not store.switched_on
        warning = application_log.only("damage_photo.storage_not_configured")
        assert warning["severity"] == "WARNING"

    def test_a_bucket_gives_the_google_store_without_opening_it(self) -> None:
        store = build_photo_store(BUCKET)
        assert isinstance(store, GcsPhotoStore)
        assert store.switched_on

    def test_the_switched_off_store_refuses_both_calls(self) -> None:
        store = SwitchedOffPhotoStore()
        with pytest.raises(FeatureSwitchedOff):
            store.put(KEY, b"pixels", "image/jpeg")
        with pytest.raises(FeatureSwitchedOff):
            store.download_link(KEY, file_name="a.jpg", lifetime=PHOTO_LINK_LIFETIME)
