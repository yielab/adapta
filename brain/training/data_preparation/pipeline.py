"""
Complete data preparation pipeline orchestrator
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional, Type
import logging
import json
from datetime import datetime

from .base import DataCollector, DataFormatter, DataPreprocessor, DataSource, ProcessedData
from .collectors import WebScraper, DocumentationCrawler, APIDocScraper, ChangeRecordCollector
from .formatters import JSONLFormatter, InstructionFormatter, ConversationFormatter, DeltaTrainingFormatter
from .preprocessors import DrupalPreprocessor, CodebasePreprocessor, MarkdownPreprocessor

logger = logging.getLogger(__name__)


class DataPreparationPipeline:
    """
    Orchestrates the complete data preparation workflow.
    Modular design allows for easy extension and customization.
    """

    # Registry of available components
    COLLECTORS = {
        'web': WebScraper,
        'documentation': DocumentationCrawler,
        'api': APIDocScraper,
        'changes': ChangeRecordCollector
    }

    PREPROCESSORS = {
        'drupal': DrupalPreprocessor,
        'code': CodebasePreprocessor,
        'markdown': MarkdownPreprocessor,
        'default': DataPreprocessor
    }

    FORMATTERS = {
        'jsonl': JSONLFormatter,
        'instruction': InstructionFormatter,
        'conversation': ConversationFormatter,
        'delta': DeltaTrainingFormatter
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.output_dir = Path(self.config.get('output_dir', '/tmp/training_data'))
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Component instances
        self.collector = None
        self.preprocessor = None
        self.formatter = None

        # Pipeline statistics
        self.stats = {
            'sources_processed': 0,
            'items_collected': 0,
            'items_preprocessed': 0,
            'items_formatted': 0,
            'errors': [],
            'start_time': None,
            'end_time': None
        }

    def configure(
        self,
        collector_type: str = 'web',
        preprocessor_type: str = 'default',
        formatter_type: str = 'jsonl',
        **kwargs
    ):
        """
        Configure pipeline components.

        Args:
            collector_type: Type of data collector to use
            preprocessor_type: Type of preprocessor for domain-specific handling
            formatter_type: Output format for training data
            **kwargs: Additional configuration for components
        """
        # Merge with existing config
        component_config = {**self.config, **kwargs}

        # Initialize collector
        collector_class = self.COLLECTORS.get(collector_type, WebScraper)
        self.collector = collector_class(component_config)

        # Initialize preprocessor
        preprocessor_class = self.PREPROCESSORS.get(preprocessor_type)
        if preprocessor_class:
            self.preprocessor = preprocessor_class(component_config)
        else:
            logger.warning(f"Unknown preprocessor type: {preprocessor_type}, using default")
            self.preprocessor = MarkdownPreprocessor(component_config)

        # Initialize formatter
        formatter_class = self.FORMATTERS.get(formatter_type, JSONLFormatter)
        self.formatter = formatter_class(component_config)

        logger.info(f"Pipeline configured: {collector_type} -> {preprocessor_type} -> {formatter_type}")

    async def prepare_data(
        self,
        sources: List[DataSource],
        output_file: Optional[Path] = None
    ) -> Path:
        """
        Run the complete data preparation pipeline.

        Args:
            sources: List of data sources to process
            output_file: Path to save the prepared data

        Returns:
            Path to the output file containing prepared training data
        """
        if not all([self.collector, self.preprocessor, self.formatter]):
            raise RuntimeError("Pipeline not configured. Call configure() first.")

        self.stats['start_time'] = datetime.now()
        self.stats['sources_processed'] = len(sources)

        try:
            # Step 1: Collect data from all sources
            logger.info(f"Collecting data from {len(sources)} sources")
            raw_data = await self._collect_phase(sources)
            self.stats['items_collected'] = len(raw_data)

            # Step 2: Preprocess collected data
            logger.info(f"Preprocessing {len(raw_data)} items")
            processed_data = await self._preprocess_phase(raw_data)
            self.stats['items_preprocessed'] = len(processed_data)

            # Step 3: Format for training
            logger.info(f"Formatting {len(processed_data)} items")
            formatted_data = self._format_phase(processed_data)
            self.stats['items_formatted'] = len(formatted_data)

            # Step 4: Save to file
            if not output_file:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = self.output_dir / f"training_data_{timestamp}.jsonl"

            self.formatter.save_to_jsonl(formatted_data, output_file)

            # Save pipeline statistics
            self._save_stats(output_file)

            logger.info(f"Data preparation complete. Output: {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            self.stats['errors'].append(str(e))
            raise

        finally:
            self.stats['end_time'] = datetime.now()

    async def _collect_phase(self, sources: List[DataSource]) -> List[Dict[str, Any]]:
        """Collection phase of the pipeline"""
        all_data = []

        for source in sources:
            try:
                data = await self.collector.collect(source)
                all_data.extend(data)
                logger.info(f"Collected {len(data)} items from {source.location}")
            except Exception as e:
                logger.error(f"Collection error for {source.location}: {e}")
                self.stats['errors'].append(f"Collection: {source.location}: {e}")

        return all_data

    async def _preprocess_phase(self, raw_data: List[Dict[str, Any]]) -> List[ProcessedData]:
        """Preprocessing phase of the pipeline"""
        processed = []

        for item in raw_data:
            try:
                processed_item = self.preprocessor.preprocess(item)
                if processed_item:
                    processed.append(processed_item)
            except Exception as e:
                logger.error(f"Preprocessing error: {e}")
                self.stats['errors'].append(f"Preprocessing: {e}")

        return processed

    def _format_phase(self, processed_data: List[ProcessedData]) -> List[Dict[str, Any]]:
        """Formatting phase of the pipeline"""
        formatted = []

        for item in processed_data:
            try:
                formatted_item = self.formatter.format(item)
                if formatted_item and self.formatter.validate_format(formatted_item):
                    formatted.append(formatted_item)
            except Exception as e:
                logger.error(f"Formatting error: {e}")
                self.stats['errors'].append(f"Formatting: {e}")

        return formatted

    def _save_stats(self, output_file: Path):
        """Save pipeline statistics"""
        stats_file = output_file.with_suffix('.stats.json')

        # Calculate duration
        if self.stats['start_time'] and self.stats['end_time']:
            duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
            self.stats['duration_seconds'] = duration

        # Convert datetime objects to strings
        stats_copy = self.stats.copy()
        if stats_copy['start_time']:
            stats_copy['start_time'] = stats_copy['start_time'].isoformat()
        if stats_copy['end_time']:
            stats_copy['end_time'] = stats_copy['end_time'].isoformat()

        with open(stats_file, 'w') as f:
            json.dump(stats_copy, f, indent=2)

        logger.info(f"Pipeline statistics saved to {stats_file}")

    async def prepare_drupal_training_data(
        self,
        target_version: str = "11",
        include_change_records: bool = True
    ) -> Path:
        """
        Specialized method for preparing Drupal training data.

        Args:
            target_version: Target Drupal version to train for
            include_change_records: Whether to include migration/change records

        Returns:
            Path to prepared training data
        """
        # Configure for Drupal
        self.configure(
            collector_type='documentation',
            preprocessor_type='drupal',
            formatter_type='delta',
            target_version=target_version,
            enable_versioning=True
        )

        # Define Drupal data sources
        sources = [
            # Main documentation
            DataSource(
                type='documentation',
                location='https://www.drupal.org/docs/user_guide/en',
                metadata={'category': 'user_guide'}
            ),
            # API documentation
            DataSource(
                type='api_doc',
                location=f'https://api.drupal.org/api/drupal/{target_version}',
                metadata={'category': 'api_reference'}
            ),
        ]

        # Add change records if requested
        if include_change_records:
            sources.append(
                DataSource(
                    type='changes',
                    location='https://www.drupal.org/list-changes/drupal',
                    metadata={'category': 'change_records', 'priority': 'high'}
                )
            )

        # Check for llms.txt if available
        sources.append(
            DataSource(
                type='url',
                location='https://www.drupal.org/llms.txt',
                metadata={'category': 'llms_curated'}
            )
        )

        # Run pipeline
        output_file = self.output_dir / f"drupal_{target_version}_training.jsonl"
        return await self.prepare_data(sources, output_file)

    async def prepare_custom_domain_data(
        self,
        domain: str,
        sources: List[Dict[str, str]],
        **config
    ) -> Path:
        """
        Prepare training data for a custom domain.

        Args:
            domain: Name of the domain (e.g., 'react', 'tensorflow')
            sources: List of source configurations
            **config: Additional configuration options

        Returns:
            Path to prepared training data
        """
        # Determine appropriate preprocessor
        preprocessor_type = config.get('preprocessor_type', 'markdown')
        if domain in ['react', 'vue', 'angular']:
            preprocessor_type = 'code'
            config['language'] = 'javascript'
            config['framework'] = domain

        # Configure pipeline
        self.configure(
            collector_type=config.get('collector_type', 'web'),
            preprocessor_type=preprocessor_type,
            formatter_type=config.get('formatter_type', 'jsonl'),
            **config
        )

        # Convert source dicts to DataSource objects
        data_sources = []
        for source in sources:
            data_sources.append(
                DataSource(
                    type=source.get('type', 'url'),
                    location=source['location'],
                    metadata=source.get('metadata', {}),
                    version=source.get('version')
                )
            )

        # Run pipeline
        output_file = self.output_dir / f"{domain}_training.jsonl"
        return await self.prepare_data(data_sources, output_file)


class BatchProcessor:
    """
    Handles batch processing of multiple domains or large datasets.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.max_concurrent = self.config.get('max_concurrent', 3)
        self.pipelines = []

    async def process_batch(
        self,
        batch_configs: List[Dict[str, Any]]
    ) -> List[Path]:
        """
        Process multiple domain configurations in parallel.

        Args:
            batch_configs: List of pipeline configurations

        Returns:
            List of paths to generated training files
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results = []

        async def process_single(config):
            async with semaphore:
                pipeline = DataPreparationPipeline(self.config)

                if config.get('domain') == 'drupal':
                    return await pipeline.prepare_drupal_training_data(
                        target_version=config.get('version', '11')
                    )
                else:
                    return await pipeline.prepare_custom_domain_data(
                        domain=config['domain'],
                        sources=config['sources'],
                        **config.get('options', {})
                    )

        tasks = [process_single(config) for config in batch_configs]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out errors
        successful = [r for r in results if isinstance(r, Path)]
        errors = [r for r in results if isinstance(r, Exception)]

        if errors:
            logger.error(f"Batch processing had {len(errors)} errors")
            for error in errors:
                logger.error(f"Error: {error}")

        return successful