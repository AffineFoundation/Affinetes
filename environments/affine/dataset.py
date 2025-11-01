import random
import asyncio
import logging
import os
import json
import aiohttp
from botocore.config import Config
from aiobotocore.session import get_session
from collections import deque
from typing import Any, Deque, List, Optional, Dict

# R2 Storage Configuration
FOLDER  = os.getenv("R2_FOLDER", "affine")
BUCKET  = os.getenv("R2_BUCKET_ID", "00523074f51300584834607253cae0fa")
ACCESS  = os.getenv("R2_WRITE_ACCESS_KEY_ID", "")
SECRET  = os.getenv("R2_WRITE_SECRET_ACCESS_KEY", "")
ENDPOINT = f"https://{BUCKET}.r2.cloudflarestorage.com"

# Public read configuration
PUBLIC_READ = os.getenv("R2_PUBLIC_READ", "true").lower() == "true"
R2_PUBLIC_BASE = os.getenv("R2_PUBLIC_BASE", f"https://pub-bf429ea7a5694b99adaf3d444cbbe64d.r2.dev")

# Logger
logger = logging.getLogger("affine")

# Shared HTTP client session
_http_client: Optional[aiohttp.ClientSession] = None


async def _get_client() -> aiohttp.ClientSession:
    """Get or create shared HTTP client session"""
    global _http_client
    if _http_client is None or _http_client.closed:
        timeout = aiohttp.ClientTimeout(total=300, connect=60, sock_read=120)
        connector = aiohttp.TCPConnector(limit=100, limit_per_host=30, ttl_dns_cache=300)
        _http_client = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector
        )
    return _http_client

class R2BufferedDataset:
    def __init__(
        self,
        dataset_name: str,
        total_size: int = 0,
        buffer_size: int = 100,
        max_batch: int = 10,
        seed: Optional[int] = None,
    ):
        self.dataset_name   = dataset_name
        self.buffer_size    = buffer_size
        self.max_batch      = max_batch
        self._rng           = random.Random(seed)

        short_name          = dataset_name
        self._dataset_folder= f"affine/datasets/{short_name}/"
        self._index_key     = self._dataset_folder + "index.json"

        self._folder        = FOLDER
        bucket_id           = BUCKET
        endpoint            = ENDPOINT
        access_key          = ACCESS
        secret_key          = SECRET

        self._endpoint_url  = endpoint
        self._access_key    = access_key
        self._secret_key    = secret_key
        self._public_read   = PUBLIC_READ
        self._public_base   = R2_PUBLIC_BASE

        self._buffer: Deque[Any] = deque()
        self._lock   = asyncio.Lock()
        self._fill_task = None

        self._index: Optional[Dict[str, Any]] = None
        self._files: list[Dict[str, Any]] = []
        self._next_file_index: int = 0
        self.total_size = total_size

    def _client_ctx(self):
        if not self._endpoint_url:
            raise RuntimeError("R2 endpoint is not configured (missing R2_BUCKET_ID)")
        sess = get_session()
        return sess.create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=Config(max_pool_connections=256),
        )

    async def _ensure_index(self) -> None:
        if self._index is not None:
            return
        if self._public_read:
            url = f"{self._public_base}/{self._index_key}"
            sess = await _get_client()
            logger.debug(f"Loading public R2 index: {url}")
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                resp.raise_for_status()
                self._index = await resp.json()
        else:
            logger.debug(f"Loading R2 index: s3://{self._folder}/{self._index_key}")
            async with self._client_ctx() as c:
                resp = await c.get_object(Bucket=self._folder, Key=self._index_key)
                body = await resp["Body"].read()
                self._index = json.loads(body.decode())
        self._files = list(self._index.get("files", []))
        if not self.total_size:
            self.total_size = int(self._index.get("total_rows", 0))
        if not self._files:
            raise RuntimeError("R2 index contains no files")
        self._next_file_index = 0

    async def _read_next_file(self) -> list[Any]:
        await self._ensure_index()
        if not self._files:
            return []
        if self._next_file_index >= len(self._files):
            self._next_file_index = 0
        file_info = self._files[self._next_file_index]
        self._next_file_index += 1
        key = file_info.get("key") or (self._dataset_folder + file_info.get("filename", ""))
        if not key:
            return []
        if self._public_read:
            url = f"{self._public_base}/{key}"
            logger.debug(f"Downloading public R2 chunk: {url}")
            sess = await _get_client()
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                resp.raise_for_status()
                body = await resp.read()
        else:
            logger.debug(f"Downloading R2 chunk: s3://{self._folder}/{key}")
            async with self._client_ctx() as c:
                resp = await c.get_object(Bucket=self._folder, Key=key)
                body = await resp["Body"].read()
        try:
            data = json.loads(body.decode())
        except Exception as e:
            logger.warning(f"Failed to parse chunk {key}: {e!r}")
            return []
        if not isinstance(data, list):
            return []
        return data

    async def _fill_buffer(self) -> None:
        logger.debug("Starting R2 buffer fill")
        while len(self._buffer) < self.buffer_size:
            rows = await self._read_next_file()
            if not rows:
                break
            if self.max_batch and len(rows) > self.max_batch:
                start = self._rng.randint(0, max(0, len(rows) - self.max_batch))
                rows = rows[start:start + self.max_batch]
            for item in rows:
                self._buffer.append(item)
        logger.debug("R2 buffer fill complete")

    async def get(self) -> Any:
        async with self._lock:
            if not self._fill_task or self._fill_task.done():
                self._fill_task = asyncio.create_task(self._fill_buffer())
            if not self._buffer:
                await self._fill_task
            # Random sampling from buffer instead of sequential popleft
            if self._buffer:
                idx = self._rng.randint(0, len(self._buffer) - 1)
                item = self._buffer[idx]
                del self._buffer[idx]
            else:
                raise RuntimeError("Buffer is empty after fill")
            if self._fill_task.done():
                self._fill_task = asyncio.create_task(self._fill_buffer())
            return item

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.get()
