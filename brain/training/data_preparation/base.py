"""
Base classes for data preparation components
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from pathlib import Path
import logging
from dataclasses import dataclass
from datetime import datetime
import json

logger = logging.getLogger(__name__)


@dataclass
class DataSource:
    """Represents a data source configuration"""
    type: str  # 'url', 'file', 'api', 'sitemap'
    location: str  # URL, file path, or API endpoint
    metadata: Dict[str, Any] = None
    version: Optional[str] = None
    timestamp: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class ProcessedData:
    """Represents processed training data"""
    content: str
    source: DataSource
    format: str  # 'instruction', 'conversation', 'raw'
    metadata: Dict[str, Any] = None
    version_info: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "content": self.content,
            "source": {
                "type": self.source.type,
                "location": self.source.location,
                "metadata": self.source.metadata,
                "version": self.source.version
            },
            "format": self.format,
            "metadata": self.metadata or {},
            "version_info": self.version_info
        }


class DataCollector(ABC):
    """
    Base class for data collection strategies.
    Implement this for different data sources (web, APIs, files, etc.)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.cache_dir = Path(self.config.get('cache_dir', '/tmp/brain_data_cache'))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        """
        Collect data from the source.

        Args:
            source: Data source configuration

        Returns:
            List of collected data items
        """
        pass

    async def collect_batch(self, sources: List[DataSource]) -> List[Dict[str, Any]]:
        """Collect from multiple sources"""
        all_data = []
        for source in sources:
            try:
                data = await self.collect(source)
                all_data.extend(data)
                logger.info(f"Collected {len(data)} items from {source.location}")
            except Exception as e:
                logger.error(f"Failed to collect from {source.location}: {e}")
        return all_data

    def cache_data(self, source: DataSource, data: Any):
        """Cache collected data for reuse"""
        cache_file = self.cache_dir / f"{source.type}_{source.location.replace('/', '_')}.json"
        with open(cache_file, 'w') as f:
            json.dump({
                "timestamp": datetime.now().isoformat(),
                "source": source.__dict__,
                "data": data
            }, f, default=str)

    def get_cached_data(self, source: DataSource, max_age_hours: int = 24) -> Optional[Any]:
        """Retrieve cached data if fresh enough"""
        cache_file = self.cache_dir / f"{source.type}_{source.location.replace('/', '_')}.json"
        if cache_file.exists():
            with open(cache_file) as f:
                cached = json.load(f)
                cached_time = datetime.fromisoformat(cached['timestamp'])
                age_hours = (datetime.now() - cached_time).total_seconds() / 3600
                if age_hours <= max_age_hours:
                    return cached['data']
        return None


class DataFormatter(ABC):
    """
    Base class for formatting data into training-ready format.
    Implement this for different training formats (JSONL, instruction-tuning, etc.)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.max_length = self.config.get('max_length', 2048)
        self.include_metadata = self.config.get('include_metadata', True)

    @abstractmethod
    def format(self, data: ProcessedData) -> Dict[str, Any]:
        """
        Format processed data into training format.

        Args:
            data: Processed data item

        Returns:
            Formatted data ready for training
        """
        pass

    def format_batch(self, data_list: List[ProcessedData]) -> List[Dict[str, Any]]:
        """Format multiple data items"""
        formatted = []
        for data in data_list:
            try:
                formatted_item = self.format(data)
                if formatted_item:
                    formatted.append(formatted_item)
            except Exception as e:
                logger.error(f"Failed to format data: {e}")
        return formatted

    def validate_format(self, formatted_data: Dict[str, Any]) -> bool:
        """Validate that formatted data meets requirements"""
        # Override in subclasses for specific validation
        return True

    def save_to_jsonl(self, formatted_data: List[Dict[str, Any]], output_path: Path):
        """Save formatted data to JSONL file"""
        with open(output_path, 'w') as f:
            for item in formatted_data:
                f.write(json.dumps(item) + '\n')
        logger.info(f"Saved {len(formatted_data)} items to {output_path}")


class DataPreprocessor(ABC):
    """
    Base class for domain-specific preprocessing.
    Implement this for different domains (Drupal, React, etc.)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.domain = self.config.get('domain', 'general')
        self.version = self.config.get('version')
        self.enable_versioning = self.config.get('enable_versioning', True)

    @abstractmethod
    def preprocess(self, raw_data: Dict[str, Any]) -> ProcessedData:
        """
        Preprocess raw data into structured format.

        Args:
            raw_data: Raw collected data

        Returns:
            Processed data ready for formatting
        """
        pass

    def preprocess_batch(self, raw_data_list: List[Dict[str, Any]]) -> List[ProcessedData]:
        """Preprocess multiple data items"""
        processed = []
        for raw_data in raw_data_list:
            try:
                processed_item = self.preprocess(raw_data)
                if processed_item:
                    processed.append(processed_item)
            except Exception as e:
                logger.error(f"Failed to preprocess data: {e}")
        return processed

    def extract_version_info(self, content: str) -> Optional[Dict[str, Any]]:
        """Extract version information from content"""
        # Override in subclasses for domain-specific version extraction
        return None

    def apply_delta_strategy(self, data: ProcessedData, base_version: str, target_version: str) -> ProcessedData:
        """Apply delta training strategy for version-specific content"""
        if not self.enable_versioning:
            return data

        # Add version metadata
        if data.version_info is None:
            data.version_info = {}

        data.version_info.update({
            'base_version': base_version,
            'target_version': target_version,
            'is_delta': True,
            'weight': 1.5 if 'deprecated' not in data.content.lower() else 0.5
        })

        return data

    def clean_content(self, content: str) -> str:
        """Clean and normalize content"""
        # Remove excess whitespace
        content = ' '.join(content.split())
        # Remove HTML entities
        import html
        content = html.unescape(content)
        return content

    def chunk_content(self, content: str, chunk_size: int = 1024, overlap: int = 128) -> List[str]:
        """Split long content into overlapping chunks"""
        if len(content) <= chunk_size:
            return [content]

        chunks = []
        start = 0
        while start < len(content):
            end = min(start + chunk_size, len(content))
            chunk = content[start:end]
            chunks.append(chunk)
            start += chunk_size - overlap

        return chunks