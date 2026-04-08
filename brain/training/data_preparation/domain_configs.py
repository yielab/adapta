"""
Domain-Specific Configurations for Data Collection
==================================================

Defines quality thresholds, validation rules, and collection
parameters for different domains (Drupal, React, Rust, Custom).
"""

from typing import Dict, List, Any
from dataclasses import dataclass, asdict


@dataclass
class DomainConfig:
    """Configuration for domain-specific data collection"""
    name: str
    min_examples: int
    min_tokens: int
    quality_threshold: float
    required_keywords: List[str]
    technical_terms: List[str]
    code_identifiers: List[str]

    # Collection settings
    max_pages: int = 300
    max_depth: int = 5
    rate_limit: float = 1.0

    # Validation weights
    technical_depth_weight: float = 0.30
    completeness_weight: float = 0.25
    relevance_weight: float = 0.20
    base_score_weight: float = 0.25

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Domain-specific configurations
DRUPAL_CONFIG = DomainConfig(
    name="drupal",
    min_examples=50,
    min_tokens=5000,
    quality_threshold=0.75,
    required_keywords=[
        "drupal", "module", "hook", "api", "function",
        "theme", "entity", "node", "field", "form"
    ],
    technical_terms=[
        "hook_", "drupal_", "entity_", "field_", "form_",
        "render array", "alter", "preprocess", "callback",
        "dependency injection", "service", "plugin", "annotation"
    ],
    code_identifiers=[
        "hook_", "function ", "class ", "interface ", "trait ",
        "namespace ", "use ", "implements ", "extends ",
        "$", "->", "::", "<?php"
    ],
    max_pages=300,
    max_depth=5,
    rate_limit=1.0
)

REACT_CONFIG = DomainConfig(
    name="react",
    min_examples=30,
    min_tokens=3000,
    quality_threshold=0.75,
    required_keywords=[
        "react", "component", "jsx", "hook", "props",
        "state", "render", "useeffect", "usestate", "context"
    ],
    technical_terms=[
        "useState", "useEffect", "useContext", "useReducer",
        "component", "props", "state", "lifecycle", "virtual dom",
        "jsx", "tsx", "functional component", "class component",
        "hooks", "context api", "redux", "provider"
    ],
    code_identifiers=[
        "function ", "const ", "let ", "var ",
        "return ", "=>", "useState", "useEffect",
        "import ", "export ", "React.", "Component",
        "{", "}", "(", ")"
    ],
    max_pages=250,
    max_depth=4,
    rate_limit=1.0
)

RUST_CONFIG = DomainConfig(
    name="rust",
    min_examples=40,
    min_tokens=4000,
    quality_threshold=0.75,
    required_keywords=[
        "rust", "trait", "impl", "cargo", "crate",
        "struct", "enum", "lifetime", "borrow", "ownership"
    ],
    technical_terms=[
        "trait", "impl", "struct", "enum", "lifetime",
        "borrowing", "ownership", "reference", "mutable",
        "immutable", "cargo", "crate", "module", "macro",
        "async", "await", "future", "result", "option"
    ],
    code_identifiers=[
        "fn ", "pub ", "impl ", "trait ", "struct ",
        "enum ", "let ", "mut ", "match ", "use ",
        "&", "&mut", "::", "->", "<", ">"
    ],
    max_pages=300,
    max_depth=5,
    rate_limit=1.0
)

CUSTOM_CONFIG = DomainConfig(
    name="custom",
    min_examples=20,
    min_tokens=2000,
    quality_threshold=0.70,
    required_keywords=[],  # No specific keywords required
    technical_terms=[],
    code_identifiers=[
        "function", "class", "def", "fn", "func",
        "const", "var", "let", "import", "export"
    ],
    max_pages=200,
    max_depth=4,
    rate_limit=1.0
)


# Registry of all domain configs
DOMAIN_CONFIGS: Dict[str, DomainConfig] = {
    "drupal": DRUPAL_CONFIG,
    "react": REACT_CONFIG,
    "rust": RUST_CONFIG,
    "custom": CUSTOM_CONFIG,
}


def get_domain_config(domain: str) -> DomainConfig:
    """
    Get configuration for a specific domain.

    Args:
        domain: Domain name (drupal, react, rust, custom)

    Returns:
        DomainConfig for the specified domain

    Raises:
        ValueError if domain is not recognized
    """
    domain_lower = domain.lower()
    if domain_lower not in DOMAIN_CONFIGS:
        raise ValueError(
            f"Unknown domain: {domain}. "
            f"Available domains: {', '.join(DOMAIN_CONFIGS.keys())}"
        )
    return DOMAIN_CONFIGS[domain_lower]


def list_domains() -> List[str]:
    """Get list of available domain names"""
    return list(DOMAIN_CONFIGS.keys())


def create_collector_config(domain: str, **overrides) -> Dict[str, Any]:
    """
    Create a collector configuration dict for a specific domain.

    Args:
        domain: Domain name (drupal, react, rust, custom)
        **overrides: Override specific config values

    Returns:
        Dict with collector configuration
    """
    config = get_domain_config(domain)
    collector_config = config.to_dict()

    # Apply overrides
    collector_config.update(overrides)

    return collector_config


def validate_data_for_domain(
    domain: str,
    num_examples: int,
    total_tokens: int
) -> tuple[bool, str]:
    """
    Validate if collected data meets domain requirements.

    Args:
        domain: Domain name
        num_examples: Number of examples collected
        total_tokens: Total tokens in collected data

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        config = get_domain_config(domain)
    except ValueError as e:
        return False, str(e)

    if num_examples < config.min_examples:
        return False, (
            f"Insufficient examples for {domain}: "
            f"got {num_examples}, need {config.min_examples}"
        )

    if total_tokens < config.min_tokens:
        return False, (
            f"Insufficient tokens for {domain}: "
            f"got {total_tokens}, need {config.min_tokens}"
        )

    return True, ""
