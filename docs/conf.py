"""
Sphinx configuration file for Brain Platform Documentation.

This provides professional, standards-compliant documentation generation
with support for:
- API documentation
- Code examples
- Interactive documentation
- Multi-format output (HTML, PDF, ePub)
"""

import os
import sys
from datetime import datetime

# Add brain module to path
sys.path.insert(0, os.path.abspath('..'))

# Project information
project = 'Brain Platform'
copyright = f'{datetime.now().year}, Brain Team'
author = 'Brain Development Team'
release = '1.0.0'
version = '1.0'

# General configuration
extensions = [
    'sphinx.ext.autodoc',           # Auto-generate documentation from docstrings
    'sphinx.ext.napoleon',           # Support Google/NumPy docstrings
    'sphinx.ext.viewcode',           # Add source code links
    'sphinx.ext.intersphinx',        # Link to other project docs
    'sphinx.ext.todo',               # Support TODO directives
    'sphinx.ext.coverage',           # Check documentation coverage
    'sphinx.ext.githubpages',        # GitHub Pages support
    'sphinx_rtd_theme',              # Read the Docs theme
    'sphinx_copybutton',             # Copy button for code blocks
    'sphinx_autodoc_typehints',      # Type hints in documentation
    'myst_parser',                   # Markdown support
    'sphinxcontrib.openapi',         # OpenAPI/Swagger documentation
    'sphinxcontrib.mermaid',         # Diagrams support
]

# Add any paths that contain templates
templates_path = ['_templates']

# List of patterns to exclude
exclude_patterns = ['_build', 'Thumbs.db', '.DS_Store']

# The theme to use
html_theme = 'sphinx_rtd_theme'

# Theme options
html_theme_options = {
    'logo_only': False,
    'display_version': True,
    'prev_next_buttons_location': 'bottom',
    'style_external_links': True,
    'collapse_navigation': False,
    'sticky_navigation': True,
    'navigation_depth': 4,
    'includehidden': True,
    'titles_only': False,
    'analytics_id': '',  # Add Google Analytics ID if needed
    'analytics_anonymize_ip': False,
}

# Add any paths that contain custom static files
html_static_path = ['_static']

# Custom sidebar templates
html_sidebars = {
    '**': [
        'globaltoc.html',
        'relations.html',
        'sourcelink.html',
        'searchbox.html',
    ]
}

# Output file base name for HTML
html_baseurl = 'https://brain.test/docs/'

# Autodoc settings
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__',
    'show-inheritance': True,
}

# Napoleon settings (for Google/NumPy docstrings)
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = False
napoleon_include_special_with_doc = True
napoleon_use_admonition_for_examples = True
napoleon_use_admonition_for_notes = True
napoleon_use_admonition_for_references = False
napoleon_use_ivar = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_type_aliases = None

# Intersphinx mapping
intersphinx_mapping = {
    'python': ('https://docs.python.org/3', None),
    'fastapi': ('https://fastapi.tiangolo.com', None),
    'pydantic': ('https://docs.pydantic.dev', None),
    'sqlalchemy': ('https://docs.sqlalchemy.org/en/latest/', None),
}

# MyST parser settings (for Markdown)
myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'dollarmath',
    'html_image',
    'substitution',
    'tasklist',
]

# Copy button settings
copybutton_prompt_text = r">>> |\.\.\. |\$ |In \[\d*\]: | {2,5}\.\.\.: | {5,8}: "
copybutton_prompt_is_regexp = True

# TODO extension settings
todo_include_todos = True

# Coverage extension settings
coverage_ignore_modules = []
coverage_ignore_functions = []
coverage_ignore_classes = []
coverage_show_missing_items = True

# LaTeX output settings (for PDF generation)
latex_engine = 'pdflatex'
latex_elements = {
    'papersize': 'a4paper',
    'pointsize': '11pt',
    'preamble': r'''
        \usepackage{charter}
        \usepackage[defaultsans]{lato}
        \usepackage{inconsolata}
    ''',
}

# Epub output settings
epub_title = project
epub_author = author
epub_publisher = author
epub_copyright = copyright

# A list of files that should not be packed into the epub file
epub_exclude_files = ['search.html']