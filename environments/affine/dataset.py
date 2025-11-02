import logging
import os
import json
import random
import aiohttp
from botocore.config import Config
from aiobotocore.session import get_session
from typing import Any, Optional, Dict, List

# R2 Storage Configuration
FOLDER = os.getenv("R2_FOLDER", "affine")
BUCKET = os.getenv("R2_BUCKET_ID", "00523074f51300584834607253cae0fa")
ACCESS = os.getenv("R2_WRITE_ACCESS_KEY_ID", "")
SECRET = os.getenv("R2_WRITE_SECRET_ACCESS_KEY", "")
ENDPOINT = f"https://{BUCKET}.r2.cloudflarestorage.com"

# Public read configuration
PUBLIC_READ = os.getenv("R2_PUBLIC_READ", "true").lower() == "true"
R2_PUBLIC_BASE = os.getenv("R2_PUBLIC_BASE", "https://pub-bf429ea7a5694b99adaf3d444cbbe64d.r2.dev")

# Logger
logger = logging.getLogger("affine")

# Shared HTTP client session
_http_client: Optional[aiohttp.ClientSession] = None


async def _get_http_client() -> aiohttp.ClientSession:
    """Get or create shared HTTP client session"""
    global _http_client
    if _http_client is None or _http_client.closed:
        _http_client = aiohttp.ClientSession()
    return _http_client


class R2Dataset:
    """
    Simple R2 dataset with true random sampling.
    
    Each call to get() randomly selects a file from the dataset,
    then randomly selects a sample from that file.
    """
    
    def __init__(
        self,
        dataset_name: str,
        seed: Optional[int] = None,
    ):
        """
        Initialize R2 dataset.
        
        Args:
            dataset_name: Name of the dataset (e.g., "satpalsr/rl-python")
            seed: Random seed for reproducibility (optional)
        """
        self.dataset_name = dataset_name
        self._rng = random.Random(seed)
        
        # Build dataset paths
        self._dataset_folder = f"affine/datasets/{dataset_name}/"
        self._index_key = self._dataset_folder + "index.json"
        
        # R2 credentials
        self._endpoint_url = ENDPOINT
        self._access_key = ACCESS
        self._secret_key = SECRET
        self._public_read = PUBLIC_READ
        self._public_base = R2_PUBLIC_BASE
        
        # Dataset metadata (loaded lazily)
        self._index: Optional[Dict[str, Any]] = None
        self._files: List[Dict[str, Any]] = []
        self.total_size: int = 0
    
    def _get_s3_client(self):
        """Create S3 client context for private R2 access"""
        if not self._endpoint_url:
            raise RuntimeError("R2 endpoint is not configured (missing R2_BUCKET_ID)")
        
        session = get_session()
        return session.create_client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            config=Config(max_pool_connections=256),
        )
    
    async def _load_index(self) -> None:
        """Load dataset index from R2"""
        if self._index is not None:
            return
        
        try:
            if self._public_read:
                url = f"{self._public_base}/{self._index_key}"
                logger.debug(f"Loading public R2 index: {url}")
                
                client = await _get_http_client()
                async with client.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    resp.raise_for_status()
                    self._index = await resp.json()
            else:
                logger.debug(f"Loading R2 index: s3://{FOLDER}/{self._index_key}")
                
                async with self._get_s3_client() as s3:
                    resp = await s3.get_object(Bucket=FOLDER, Key=self._index_key)
                    body = await resp["Body"].read()
                    self._index = json.loads(body.decode())
            
            # Extract file list and metadata
            self._files = list(self._index.get("files", []))
            self.total_size = int(self._index.get("total_rows", 0))
            
            if not self._files:
                raise RuntimeError(f"Dataset '{self.dataset_name}' contains no files")
            
            logger.info(f"Loaded dataset '{self.dataset_name}': {len(self._files)} files, {self.total_size} total samples")
            
        except Exception as e:
            logger.error(f"Failed to load dataset index: {e}")
            raise RuntimeError(f"Failed to load dataset '{self.dataset_name}': {e}") from e
    
    async def _read_file(self, file_info: Dict[str, Any]) -> List[Any]:
        """
        Read a single data file from R2.
        
        Args:
            file_info: File metadata dictionary
            
        Returns:
            List of samples from the file
        """
        # Determine file key
        key = file_info.get("key") or (self._dataset_folder + file_info.get("filename", ""))
        if not key:
            logger.warning(f"Invalid file info: {file_info}")
            return []
        
        try:
            if self._public_read:
                url = f"{self._public_base}/{key}"
                logger.debug(f"Downloading public R2 file: {url}")
                
                client = await _get_http_client()
                async with client.get(url, timeout=aiohttp.ClientTimeout(total=100)) as resp:
                    resp.raise_for_status()
                    body = await resp.read()
            else:
                logger.debug(f"Downloading R2 file: s3://{FOLDER}/{key}")
                
                async with self._get_s3_client() as s3:
                    resp = await s3.get_object(Bucket=FOLDER, Key=key)
                    body = await resp["Body"].read()
            
            # Parse JSON data
            data = json.loads(body.decode())
            
            if not isinstance(data, list):
                logger.warning(f"File {key} does not contain a list")
                return []
            
            return data
            
        except Exception as e:
            logger.warning(f"Failed to read file {key}: {e}")
            return []
    
    async def get(self) -> Any:
        """
        Get a random sample from the dataset.
        
        Returns:
            A randomly selected sample
            
        Raises:
            RuntimeError: If dataset is empty or cannot be loaded
        """
        # Ensure index is loaded
        await self._load_index()
        
        if not self._files:
            raise RuntimeError(f"Dataset '{self.dataset_name}' is empty")
        
        # Randomly select a file
        file_info = self._rng.choice(self._files)
        
        # Load file contents
        samples = await self._read_file(file_info)
        
        if not samples:
            # Retry with another file if this one is empty
            logger.warning(f"Selected file is empty, retrying...")
            return await self.get()
        
        # Randomly select a sample from the file
        sample = self._rng.choice(samples)
        
        logger.debug(f"Retrieved random sample from dataset '{self.dataset_name}'")
        return sample
    
    def __aiter__(self):
        """Support async iteration"""
        return self
    
    async def __anext__(self) -> Any:
        """Get next random sample"""
        return await self.get()