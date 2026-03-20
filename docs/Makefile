# Makefile for Brain Platform Documentation

SPHINXOPTS    ?= -W --keep-going
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Colors for output
YELLOW := \033[1;33m
GREEN := \033[1;32m
RED := \033[1;31m
RESET := \033[0m

.PHONY: help clean html pdf api test serve install

help:
	@echo "$(GREEN)Brain Platform Documentation Build System$(RESET)"
	@echo ""
	@echo "Available targets:"
	@echo "  $(YELLOW)install$(RESET)   - Install documentation dependencies"
	@echo "  $(YELLOW)html$(RESET)      - Build HTML documentation"
	@echo "  $(YELLOW)pdf$(RESET)       - Build PDF documentation"
	@echo "  $(YELLOW)api$(RESET)       - Generate API documentation"
	@echo "  $(YELLOW)serve$(RESET)     - Serve documentation locally"
	@echo "  $(YELLOW)test$(RESET)      - Test documentation build"
	@echo "  $(YELLOW)clean$(RESET)     - Clean build directory"
	@echo "  $(YELLOW)all$(RESET)       - Build everything"

install:
	@echo "$(YELLOW)Installing documentation dependencies...$(RESET)"
	pip install sphinx sphinx_rtd_theme sphinx-copybutton sphinx-autodoc-typehints myst-parser sphinxcontrib-openapi sphinxcontrib-mermaid

clean:
	@echo "$(YELLOW)Cleaning build directory...$(RESET)"
	rm -rf $(BUILDDIR)
	rm -rf api/modules/*.rst
	rm -f api/openapi.json

api:
	@echo "$(YELLOW)Generating API documentation...$(RESET)"
	python generate_api_docs.py

html: api
	@echo "$(YELLOW)Building HTML documentation...$(RESET)"
	@$(SPHINXBUILD) -b html $(SOURCEDIR) $(BUILDDIR)/html $(SPHINXOPTS)
	@echo "$(GREEN)✅ HTML documentation built in $(BUILDDIR)/html$(RESET)"

pdf:
	@echo "$(YELLOW)Building PDF documentation...$(RESET)"
	@$(SPHINXBUILD) -b latex $(SOURCEDIR) $(BUILDDIR)/latex $(SPHINXOPTS)
	@echo "$(YELLOW)Running LaTeX...$(RESET)"
	@make -C $(BUILDDIR)/latex all-pdf
	@echo "$(GREEN)✅ PDF documentation built in $(BUILDDIR)/latex$(RESET)"

serve: html
	@echo "$(GREEN)Serving documentation at http://localhost:8080$(RESET)"
	@echo "$(YELLOW)Press Ctrl+C to stop$(RESET)"
	@cd $(BUILDDIR)/html && python3 -m http.server 8080

test:
	@echo "$(YELLOW)Testing documentation build...$(RESET)"
	@$(SPHINXBUILD) -b doctest $(SOURCEDIR) $(BUILDDIR)/doctest
	@$(SPHINXBUILD) -b linkcheck $(SOURCEDIR) $(BUILDDIR)/linkcheck
	@echo "$(GREEN)✅ All tests passed$(RESET)"

all: clean html pdf
	@echo "$(GREEN)✅ All documentation built successfully$(RESET)"

# Watch for changes and rebuild
watch:
	@echo "$(YELLOW)Watching for changes...$(RESET)"
	@while true; do \
		$(MAKE) html; \
		inotifywait -qre close_write .; \
	done

.PHONY: deploy
deploy: html
	@echo "$(YELLOW)Deploying documentation...$(RESET)"
	# Add your deployment commands here
	# Example: rsync -avz _build/html/ user@server:/var/www/docs/
	@echo "$(GREEN)✅ Documentation deployed$(RESET)"