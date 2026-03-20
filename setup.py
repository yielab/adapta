"""
Setup configuration for Brain SDK.

Install with: pip install brain-sdk
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read version from __init__.py
version_file = this_directory / "brain" / "__init__.py"
version = "1.0.0"
for line in version_file.read_text().split("\n"):
    if line.startswith("__version__"):
        version = line.split("=")[1].strip().strip('"')
        break

setup(
    name="brain-sdk",
    version=version,
    author="Brain Team",
    author_email="team@brain.ai",
    description="Production-ready local AI intelligence layer with framework integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/brain",
    project_urls={
        "Documentation": "https://docs.brain.ai",
        "Source": "https://github.com/yourusername/brain",
        "Tracker": "https://github.com/yourusername/brain/issues",
    },
    packages=find_packages(exclude=["tests", "tests.*", "docs", "examples"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.8",
    install_requires=[
        "fastapi>=0.100.0",
        "uvicorn>=0.23.0",
        "pydantic>=2.0.0",
        "httpx>=0.24.0",
        "transformers>=4.30.0",
        "torch>=2.0.0",
        "numpy>=1.24.0",
        "tiktoken>=0.4.0",
        "opentelemetry-api>=1.20.0",
        "opentelemetry-sdk>=1.20.0",
        "opentelemetry-exporter-jaeger>=1.20.0",
        "opentelemetry-exporter-zipkin>=1.20.0",
        "chromadb>=0.4.0",
        "sentence-transformers>=2.2.0",
        "rank-bm25>=0.2.0",
        "aiofiles>=23.0.0",
        "python-multipart>=0.0.6",
        "redis>=4.5.0",
        "sqlalchemy>=2.0.0",
        "alembic>=1.11.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.3.0",
            "pytest-asyncio>=0.21.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.3.0",
            "pre-commit>=3.3.0",
        ],
        "langchain": [
            "langchain>=0.1.0",
            "langchain-community>=0.1.0",
        ],
        "langgraph": [
            "langgraph>=0.0.20",
        ],
        "vision": [
            "pillow>=10.0.0",
            "opencv-python>=4.8.0",
        ],
        "all": [
            "langchain>=0.1.0",
            "langchain-community>=0.1.0",
            "langgraph>=0.0.20",
            "pillow>=10.0.0",
            "opencv-python>=4.8.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "brain=brain.cli:main",
            "brain-server=brain.server:main",
        ],
    },
    include_package_data=True,
    package_data={
        "brain": [
            "*.yaml",
            "*.yml",
            "*.json",
            "templates/*",
            "static/*",
        ],
    },
    keywords=[
        "ai",
        "llm",
        "machine-learning",
        "deep-learning",
        "neural-networks",
        "nlp",
        "rag",
        "langchain",
        "local-ai",
        "framework-integration",
        "agent",
        "memory",
        "context-management",
    ],
)