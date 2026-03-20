"""
Model download functionality.
"""
import asyncio
import logging
from pathlib import Path
from typing import Optional
import aiohttp
from tqdm import tqdm

logger = logging.getLogger(__name__)


class ModelDownloader:
    """Handle model downloads from HuggingFace."""

    def __init__(self, models_dir: Path):
        self.models_dir = models_dir
        self.downloads = {}  # Track active downloads

    async def download_model(
        self,
        model_id: str,
        download_url: str,
        local_dir: str,
        filename: str,
        progress_callback: Optional[callable] = None,
    ) -> dict:
        """
        Download a model from HuggingFace with retry logic.

        Args:
            model_id: Unique model identifier
            download_url: Direct download URL
            local_dir: Directory name under models_dir
            filename: Model filename
            progress_callback: Optional callback for progress updates

        Returns:
            dict with download status
        """
        target_dir = self.models_dir / local_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename

        # Check if already downloaded
        if target_path.exists():
            return {
                "model_id": model_id,
                "status": "already_exists",
                "path": str(target_path),
                "message": "Model already downloaded",
            }

        # Check if download in progress
        if model_id in self.downloads:
            return {
                "model_id": model_id,
                "status": "in_progress",
                "progress": self.downloads[model_id].get("progress", 0),
                "message": "Download already in progress",
            }

        # Initialize download tracking
        self.downloads[model_id] = {
            "status": "downloading",
            "progress": 0,
            "downloaded_bytes": 0,
            "total_bytes": 0,
        }

        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                logger.info(f"Starting download: {model_id} from {download_url} (attempt {retry_count + 1}/{max_retries})")

                # Use larger timeout for large file downloads
                timeout = aiohttp.ClientTimeout(total=None, connect=60, sock_read=300)

                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(download_url) as response:
                        if response.status != 200:
                            raise Exception(f"Download failed with status {response.status}")

                        total_size = int(response.headers.get("content-length", 0))
                        self.downloads[model_id]["total_bytes"] = total_size

                        # Download with progress tracking
                        downloaded = 0
                        chunk_size = 8 * 1024 * 1024  # 8MB chunks for better performance

                        with open(target_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)

                                # Update progress
                                progress = (downloaded / total_size * 100) if total_size > 0 else 0
                                self.downloads[model_id].update({
                                    "progress": progress,
                                    "downloaded_bytes": downloaded,
                                })

                                # Call progress callback if provided
                                if progress_callback:
                                    await progress_callback(model_id, progress, downloaded, total_size)

                # Download complete
                self.downloads[model_id]["status"] = "completed"
                logger.info(f"Download completed: {model_id} -> {target_path}")

                return {
                    "model_id": model_id,
                    "status": "completed",
                    "path": str(target_path),
                    "size_bytes": downloaded,
                    "message": "Download completed successfully",
                }

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                retry_count += 1
                logger.warning(f"Download attempt {retry_count} failed for {model_id}: {e}")

                if retry_count < max_retries:
                    # Wait before retrying (exponential backoff)
                    wait_time = 2 ** retry_count
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)

                    # Clean up partial download
                    if target_path.exists():
                        target_path.unlink()
                else:
                    # Max retries exceeded
                    logger.error(f"Download failed for {model_id} after {max_retries} attempts: {e}")
                    self.downloads[model_id]["status"] = "failed"
                    self.downloads[model_id]["error"] = f"Failed after {max_retries} attempts: {str(e)}"

                    # Clean up partial download
                    if target_path.exists():
                        target_path.unlink()

                    return {
                        "model_id": model_id,
                        "status": "failed",
                        "error": f"Failed after {max_retries} attempts: {str(e)}",
                        "message": f"Download failed after {max_retries} attempts. Please try again or download manually.",
                    }

            except Exception as e:
                logger.error(f"Download failed for {model_id}: {e}")
                self.downloads[model_id]["status"] = "failed"
                self.downloads[model_id]["error"] = str(e)

                # Clean up partial download
                if target_path.exists():
                    target_path.unlink()

                return {
                    "model_id": model_id,
                    "status": "failed",
                    "error": str(e),
                    "message": f"Download failed: {e}",
                }

    def get_download_status(self, model_id: str) -> Optional[dict]:
        """Get status of a download."""
        return self.downloads.get(model_id)

    def get_all_downloads(self) -> dict:
        """Get status of all downloads."""
        return self.downloads.copy()

    def cancel_download(self, model_id: str) -> bool:
        """Cancel an in-progress download."""
        if model_id in self.downloads:
            self.downloads[model_id]["status"] = "cancelled"
            return True
        return False
