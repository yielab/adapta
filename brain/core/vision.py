"""Vision model utilities for image processing"""

import base64
import io
import logging
from pathlib import Path
from typing import Union, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ImageData:
    """Processed image data ready for vision model"""

    image_bytes: bytes
    format: str  # 'png', 'jpeg', 'webp', etc.
    width: int
    height: int
    base64_data: Optional[str] = None

    def to_base64(self) -> str:
        """Convert image to base64 string"""
        if not self.base64_data:
            self.base64_data = base64.b64encode(self.image_bytes).decode('utf-8')
        return self.base64_data


class ImageProcessor:
    """
    Image processing for vision models.

    Handles:
    - Loading images from files or bytes
    - Resizing and preprocessing
    - Format conversion
    - Base64 encoding for API transport
    """

    def __init__(self, max_size: int = 512):
        """
        Initialize image processor.

        Args:
            max_size: Maximum dimension (width or height) for images
        """
        self.max_size = max_size
        self._check_dependencies()

    def _check_dependencies(self):
        """Check if PIL is available"""
        try:
            from PIL import Image
            self.pil_available = True
            logger.info("PIL (Pillow) available for image processing")
        except ImportError:
            self.pil_available = False
            logger.warning(
                "PIL (Pillow) not available. Install with: pip install Pillow\n"
                "Image processing will be limited."
            )

    def load_from_file(self, file_path: Union[str, Path]) -> ImageData:
        """
        Load and process image from file.

        Args:
            file_path: Path to image file

        Returns:
            ImageData with processed image
        """
        if not self.pil_available:
            raise RuntimeError("PIL (Pillow) required. Install with: pip install Pillow")

        from PIL import Image

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        logger.info(f"Loading image from {file_path}")

        # Open and process image
        with Image.open(file_path) as img:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Get original dimensions
            original_width, original_height = img.size

            # Resize if needed
            if max(original_width, original_height) > self.max_size:
                img = self._resize_image(img)

            width, height = img.size

            # Save to bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            image_bytes = buffer.getvalue()

        logger.info(f"Processed image: {width}x{height}, {len(image_bytes)} bytes")

        return ImageData(
            image_bytes=image_bytes,
            format='png',
            width=width,
            height=height,
        )

    def load_from_bytes(self, image_bytes: bytes, format: str = 'png') -> ImageData:
        """
        Load and process image from bytes.

        Args:
            image_bytes: Raw image bytes
            format: Image format (png, jpeg, etc.)

        Returns:
            ImageData with processed image
        """
        if not self.pil_available:
            raise RuntimeError("PIL (Pillow) required. Install with: pip install Pillow")

        from PIL import Image

        logger.info(f"Loading image from bytes ({len(image_bytes)} bytes)")

        # Open and process image
        buffer = io.BytesIO(image_bytes)
        with Image.open(buffer) as img:
            # Convert to RGB if needed
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Get original dimensions
            original_width, original_height = img.size

            # Resize if needed
            if max(original_width, original_height) > self.max_size:
                img = self._resize_image(img)

            width, height = img.size

            # Save to bytes
            output_buffer = io.BytesIO()
            img.save(output_buffer, format='PNG')
            processed_bytes = output_buffer.getvalue()

        logger.info(f"Processed image: {width}x{height}, {len(processed_bytes)} bytes")

        return ImageData(
            image_bytes=processed_bytes,
            format='png',
            width=width,
            height=height,
        )

    def load_from_base64(self, base64_str: str) -> ImageData:
        """
        Load and process image from base64 string.

        Args:
            base64_str: Base64-encoded image

        Returns:
            ImageData with processed image
        """
        # Decode base64
        image_bytes = base64.b64decode(base64_str)
        return self.load_from_bytes(image_bytes)

    def _resize_image(self, img) -> "Image":
        """
        Resize image maintaining aspect ratio.

        Args:
            img: PIL Image object

        Returns:
            Resized PIL Image
        """
        from PIL import Image

        width, height = img.size

        # Calculate new dimensions
        if width > height:
            new_width = self.max_size
            new_height = int(height * (self.max_size / width))
        else:
            new_height = self.max_size
            new_width = int(width * (self.max_size / height))

        logger.info(f"Resizing image from {width}x{height} to {new_width}x{new_height}")

        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def prepare_for_moondream(self, image_data: ImageData) -> dict:
        """
        Prepare image data for Moondream2 vision model.

        Args:
            image_data: Processed image data

        Returns:
            Dict with image data formatted for Moondream2
        """
        return {
            "image": image_data.to_base64(),
            "format": image_data.format,
            "width": image_data.width,
            "height": image_data.height,
        }


# Global image processor instance
image_processor = ImageProcessor(max_size=512)
