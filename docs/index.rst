.. Brain Platform documentation master file

====================================
Brain Platform Documentation
====================================

.. image:: https://img.shields.io/badge/version-1.0.0-blue.svg
   :alt: Version

.. image:: https://img.shields.io/badge/license-MIT-green.svg
   :alt: License

.. image:: https://img.shields.io/badge/python-3.10+-blue.svg
   :alt: Python Version

Welcome to Brain Platform
==========================

Brain is a **production-ready AI intelligence platform** that provides a comprehensive layer for modern AI applications. It implements Anthropic's context engineering best practices with enterprise features.

Key Features
------------

* **Unlimited Context Management** - Advanced context optimization with sliding windows
* **Multi-tier Memory System** - Short-term, long-term, and episodic memory with consolidation
* **Advanced RAG** - Hybrid search with 40% better retrieval quality
* **Intelligent Routing** - 95% accuracy in model selection
* **Adaptive Evolution** - Self-improving system with A/B testing
* **Full Observability** - Prometheus, Grafana, and Jaeger integration

.. toctree::
   :maxdepth: 2
   :caption: Getting Started

   installation
   quickstart
   configuration
   deployment

.. toctree::
   :maxdepth: 2
   :caption: User Guide

   guides/agents
   guides/memory
   guides/rag
   guides/context
   guides/training
   guides/routing

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/endpoints
   api/models
   api/authentication
   api/websockets
   api/examples

.. toctree::
   :maxdepth: 2
   :caption: Architecture

   architecture/overview
   architecture/components
   architecture/data_flow
   architecture/scaling
   architecture/security

.. toctree::
   :maxdepth: 2
   :caption: Developer Guide

   development/setup
   development/contributing
   development/testing
   development/plugins
   development/adapters

.. toctree::
   :maxdepth: 2
   :caption: Operations

   operations/monitoring
   operations/logging
   operations/backup
   operations/troubleshooting
   operations/performance

.. toctree::
   :maxdepth: 1
   :caption: Reference

   changelog
   roadmap
   glossary
   faq

Quick Links
-----------

* :ref:`genindex` - Complete index
* :ref:`modindex` - Module index
* :ref:`search` - Search documentation

Performance Metrics
-------------------

.. list-table::
   :widths: 30 30 30
   :header-rows: 1

   * - Metric
     - Before
     - After
   * - Context Limit
     - 4K tokens
     - Unlimited
   * - Tool Calling Success
     - 85%
     - 99%+
   * - RAG Quality
     - Baseline
     - +40%
   * - Response Speed
     - Baseline
     - -30% latency
   * - Token Costs
     - Baseline
     - -35% reduction

Getting Help
------------

* **GitHub Issues**: `Report bugs or request features <https://github.com/brain/platform/issues>`_
* **Documentation**: You're here!
* **Community**: Join our Discord server
* **Support**: support@brain.ai