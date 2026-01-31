SHELL := /bin/sh

.DEFAULT_GOAL := help

# Generic Makefile template.
# Projects can extend/override these targets.

.PHONY: help
help: ## Show targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

# =============================================================================
# Dependency install
# =============================================================================

.PHONY: install
install: ## Install project dependencies (project-specific)
	@echo "No install target defined for this project yet. Customize skel/Makefile." && exit 1

.PHONY: install-dev
install-dev: ## Install dev dependencies (project-specific)
	@echo "No install-dev target defined for this project yet. Customize skel/Makefile." && exit 1

# =============================================================================
# Quality
# =============================================================================

.PHONY: lint
lint: ## Run linters (project-specific)
	@echo "No lint target defined for this project yet. Customize skel/Makefile." && exit 1

.PHONY: format
format: ## Format code (project-specific)
	@echo "No format target defined for this project yet. Customize skel/Makefile." && exit 1

.PHONY: test
test: ## Run tests (project-specific)
	@echo "No test target defined for this project yet. Customize skel/Makefile." && exit 1

.PHONY: coverage
coverage: ## Run tests with coverage (project-specific)
	@echo "No coverage target defined for this project yet. Customize skel/Makefile." && exit 1

.PHONY: check
check: ## Run standard validation pipeline (project-specific)
	@$(MAKE) lint && $(MAKE) test

# =============================================================================
# Cleanup
# =============================================================================

.PHONY: clean
clean: ## Remove local build/test artifacts (project-specific)
	@echo "No clean target defined for this project yet. Customize skel/Makefile." && exit 1
