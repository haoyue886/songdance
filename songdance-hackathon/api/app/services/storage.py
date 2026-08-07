from pathlib import Path
from shutil import copyfile
from typing import Protocol

import boto3
from botocore.exceptions import ClientError

from app.settings import Settings


class ObjectStorage(Protocol):
    def put_file(self, key: str, source: Path, content_type: str) -> None: ...

    def download_file(self, key: str, destination: Path) -> None: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ValueError("storage key escapes the configured root") from error
        return path

    def put_file(self, key: str, source: Path, content_type: str) -> None:
        del content_type
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(source, destination)

    def download_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        copyfile(self._path(key), destination)

    def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)
        parent = path.parent
        while parent != self.root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        secret = settings.s3_secret_key
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=secret.get_secret_value() if secret else None,
        )

    def ensure_ready(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code not in {"404", "NoSuchBucket", "NotFound"}:
                raise
            self.client.create_bucket(Bucket=self.bucket)

    def put_file(self, key: str, source: Path, content_type: str) -> None:
        self.client.upload_file(
            str(source), self.bucket, key, ExtraArgs={"ContentType": content_type}
        )

    def download_file(self, key: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        self.client.download_file(self.bucket, key, str(destination))

    def delete(self, key: str) -> None:
        paginator = self.client.get_paginator("list_multipart_uploads")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=key):
            for upload in page.get("Uploads", []):
                if upload.get("Key") != key:
                    continue
                try:
                    self.client.abort_multipart_upload(
                        Bucket=self.bucket,
                        Key=key,
                        UploadId=upload["UploadId"],
                    )
                except ClientError as error:
                    code = str(error.response.get("Error", {}).get("Code", ""))
                    if code not in {"404", "NoSuchUpload", "NotFound"}:
                        raise
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as error:
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise
        return True


def create_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.local_storage_path)
    storage = S3ObjectStorage(settings)
    storage.ensure_ready()
    return storage
