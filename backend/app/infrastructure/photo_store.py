"""The private bucket damage photographs are kept in, and the choice of store (C-31).

`GcsPhotoStore` is the only module that imports the Google Cloud Storage
client. It writes each photograph once, with `if_generation_match=0`, so an
upload can never replace an object that is already there. That condition is
also what makes a retried upload safe, so the client's own retry is used,
bounded well inside the request timeout of Cloud Run.

A link is a V4 signed URL that works for five minutes and asks the bucket to
serve the photograph as an attachment. On Cloud Run the credentials come from
the metadata server and hold no private key, so the URL cannot be signed
locally. It is signed through the IAM signBlob call instead, by handing the
client the service account's address and a current access token, as Google's
documentation describes. That needs roles/iam.serviceAccountTokenCreator for
the runtime account on itself, which infra/scripts/create-photo-bucket.sh
grants. The token is refreshed when it has expired, under a lock, so two
requests do not refresh it at once.

The client is built on first use and not at start-up, so an instance that
never handles a photograph never reaches the metadata server for it.

`SwitchedOffPhotoStore` is what the service runs with while PHOTO_BUCKET is
not set. It keeps nothing and refuses every call, and every photograph route
answers 503 because of it. `build_photo_store` picks one of the two when the
application is built, and logs one warning when photographs are switched off,
the way the email gateway does without its key.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter
from typing import Final, Protocol

from app.domain.errors import FeatureSwitchedOff

logger = logging.getLogger(__name__)

SIGNED_URL_VERSION: Final[str] = "v4"
DOWNLOAD_METHOD: Final[str] = "GET"
# Seconds to connect, and seconds to wait for each read, on one upload attempt.
UPLOAD_TIMEOUT: Final[tuple[float, float]] = (5.0, 20.0)
# Every attempt of one upload has to finish inside this, well short of the 60
# second request timeout of the Cloud Run service.
UPLOAD_RETRY_DEADLINE_SECONDS: Final[float] = 30.0
# The upload succeeds only when no object of that name exists yet.
NO_EXISTING_OBJECT: Final[int] = 0
CLOUD_PLATFORM_SCOPE: Final[str] = "https://www.googleapis.com/auth/cloud-platform"
MILLISECONDS: Final[int] = 1000
SWITCHED_OFF_MESSAGE: Final[str] = "Photographs are not switched on yet."


class BlobHandle(Protocol):
    """The two calls this store makes on one object of the bucket."""

    def upload_from_string(
        self,
        data: bytes,
        content_type: str,
        *,
        if_generation_match: int,
        timeout: tuple[float, float],
        retry: object,
    ) -> None:
        """Write the object."""
        ...

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
        """Return a signed URL for the object."""
        ...


class BucketHandle(Protocol):
    """The one call this store makes on the bucket."""

    def blob(self, blob_name: str) -> BlobHandle:
        """Return a handle on one object of the bucket."""
        ...


@dataclass(frozen=True, slots=True)
class SigningIdentity:
    """Who signs a link, and the token that lets the IAM API sign as them.

    Attributes:
        service_account_email: The runtime service account.
        access_token: A current access token of that account. Never logged.

    """

    service_account_email: str
    access_token: str


class SigningIdentitySource(Protocol):
    """Hands out a signing identity whose token has not expired."""

    def current(self) -> SigningIdentity:
        """Return the identity, refreshing its token first when it has expired."""
        ...


@dataclass(frozen=True, slots=True)
class BucketConnection:
    """A bucket and the identity that signs links to its objects."""

    bucket: BucketHandle
    signer: SigningIdentitySource
    upload_retry: object


type BucketOpener = Callable[[str], BucketConnection]


class GcsPhotoStore:
    """The private Google Cloud Storage bucket the photographs are kept in."""

    def __init__(self, bucket_name: str, *, open_bucket: BucketOpener | None = None) -> None:
        """Remember the bucket. Nothing is opened until the first photograph needs it.

        Args:
            bucket_name: The bucket, as PHOTO_BUCKET names it.
            open_bucket: Opens the bucket. The real Google client by default,
                and a fake in the tests of this adapter.

        """
        self._bucket_name = bucket_name
        self._open_bucket = open_bucket or open_google_bucket
        self._connection: BucketConnection | None = None
        self._lock = threading.Lock()

    @property
    def switched_on(self) -> bool:
        """Return True, because a bucket is configured."""
        return True

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        """Store one photograph under a name that is not in use yet.

        Raises:
            Exception: Whatever the client raises once its retries are spent.
                It is logged here with the object key and raised unchanged.

        """
        connection = self._connected()
        started = perf_counter()
        logger.info(
            "damage_photo.store_started",
            extra={"object_key": object_key, "size_bytes": len(content)},
        )
        try:
            connection.bucket.blob(object_key).upload_from_string(
                content,
                content_type,
                if_generation_match=NO_EXISTING_OBJECT,
                timeout=UPLOAD_TIMEOUT,
                retry=connection.upload_retry,
            )
        except Exception as failure:
            logger.error(
                "damage_photo.store_failed",
                extra={
                    "object_key": object_key,
                    "cause": type(failure).__name__,
                    "duration_ms": _elapsed_ms(started),
                },
            )
            raise
        logger.info(
            "damage_photo.stored",
            extra={"object_key": object_key, "duration_ms": _elapsed_ms(started)},
        )

    def download_link(self, object_key: str, *, file_name: str, lifetime: timedelta) -> str:
        """Return a V4 signed link to one photograph, served as a download under `file_name`."""
        connection = self._connected()
        identity = connection.signer.current()
        url = connection.bucket.blob(object_key).generate_signed_url(
            version=SIGNED_URL_VERSION,
            expiration=lifetime,
            method=DOWNLOAD_METHOD,
            response_disposition=f'attachment; filename="{file_name}"',
            service_account_email=identity.service_account_email,
            access_token=identity.access_token,
        )
        logger.debug(
            "damage_photo.link_signed",
            extra={"object_key": object_key, "lifetime_seconds": lifetime.total_seconds()},
        )
        return str(url)

    def _connected(self) -> BucketConnection:
        """Return the bucket, opening it on first use."""
        with self._lock:
            if self._connection is None:
                logger.info("damage_photo.bucket_opening")
                self._connection = self._open_bucket(self._bucket_name)
            return self._connection


class SwitchedOffPhotoStore:
    """The store a deployment with no bucket runs with. It keeps nothing."""

    @property
    def switched_on(self) -> bool:
        """Return False, because no bucket is configured."""
        return False

    def put(self, object_key: str, content: bytes, content_type: str) -> None:
        """Refuse, because there is nowhere to keep a photograph.

        Raises:
            FeatureSwitchedOff: Always.

        """
        raise FeatureSwitchedOff(SWITCHED_OFF_MESSAGE, {"feature": "damage_photos"})

    def download_link(self, object_key: str, *, file_name: str, lifetime: timedelta) -> str:
        """Refuse, because no photograph is kept.

        Raises:
            FeatureSwitchedOff: Always.

        """
        raise FeatureSwitchedOff(SWITCHED_OFF_MESSAGE, {"feature": "damage_photos"})


def build_photo_store(bucket_name: str | None) -> GcsPhotoStore | SwitchedOffPhotoStore:
    """Return the store a configuration calls for, warning once when it is switched off."""
    if bucket_name is None:
        logger.warning(
            "damage_photo.storage_not_configured",
            extra={
                "consequence": "every damage photograph route answers 503",
                "remedy": "set PHOTO_BUCKET to the bucket made by create-photo-bucket.sh",
            },
        )
        return SwitchedOffPhotoStore()
    logger.info("damage_photo.storage_configured", extra={"provider": "google-cloud-storage"})
    return GcsPhotoStore(bucket_name)


def open_google_bucket(bucket_name: str) -> BucketConnection:
    """Open the bucket through the official client, with the runtime's own credentials.

    The client library is imported here and not at the top of the module. It is
    large, and a cold start of an instance that never handles a photograph, or
    of a deployment with photographs switched off, does not pay for loading it.
    """
    import google.auth
    from google.auth.transport.requests import Request
    from google.cloud import storage
    from google.cloud.storage.retry import DEFAULT_RETRY

    credentials, project = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
    client = storage.Client(project=project, credentials=credentials)
    signer = _MetadataSigner(credentials, Request)
    logger.info("damage_photo.bucket_opened", extra={"project_known": project is not None})
    return BucketConnection(
        bucket=client.bucket(bucket_name),
        signer=signer,
        upload_retry=DEFAULT_RETRY.with_timeout(UPLOAD_RETRY_DEADLINE_SECONDS),
    )


class _RefreshableCredentials(Protocol):
    """The parts of a google.auth credential the signer reads."""

    @property
    def valid(self) -> bool:
        """Return True while the token has not expired."""
        ...

    @property
    def token(self) -> str | None:
        """Return the current access token."""
        ...

    def refresh(self, request: object) -> None:
        """Fetch a new token."""
        ...


class _MetadataSigner:
    """Signs as the runtime service account, through its access token and IAM signBlob."""

    def __init__(
        self, credentials: _RefreshableCredentials, request_factory: Callable[[], object]
    ) -> None:
        """Keep the credentials and how to build the request that refreshes them."""
        self._credentials = credentials
        self._request_factory = request_factory
        self._lock = threading.Lock()

    def current(self) -> SigningIdentity:
        """Return the account and a token that has not expired.

        Raises:
            RuntimeError: If the credentials name no service account, which is
                the case for a person's own credentials on a laptop.

        """
        with self._lock:
            if not self._credentials.valid:
                self._credentials.refresh(self._request_factory())
                logger.info("damage_photo.signing_token_refreshed")
            email = getattr(self._credentials, "service_account_email", None)
            token = self._credentials.token
        if not isinstance(email, str) or not email or token is None:
            raise RuntimeError(
                "Attempted to sign a link to a damage photograph, and the credentials name no "
                "service account to sign as. Run the service as its runtime service account, "
                "which create-photo-bucket.sh lets sign for itself."
            )
        return SigningIdentity(service_account_email=email, access_token=token)


def _elapsed_ms(started: float) -> int:
    """Return the milliseconds since `started`, from the performance counter."""
    return round((perf_counter() - started) * MILLISECONDS)
