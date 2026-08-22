import boto3
from botocore.exceptions import ClientError
from django.conf import settings
from .base import StorageBackend


class R2StorageBackend(StorageBackend):
    def __init__(self):
        cfg = settings.CLOUDFLARE_R2
        self._bucket = cfg['BUCKET_NAME']
        self._public_domain = cfg['PUBLIC_DOMAIN']
        self._client = boto3.client(
            's3',
            region_name=cfg['REGION'],
            endpoint_url=cfg['ENDPOINT'],
            aws_access_key_id=cfg['ACCESS_KEY_ID'],
            aws_secret_access_key=cfg['SECRET_ACCESS_KEY'],
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as e:
            if e.response.get('Error', {}).get('Code') in ('404', 'NoSuchKey'):
                return False
            raise

    def public_url(self, key: str) -> str:
        return f"{self._public_domain.rstrip('/')}/{key}"
