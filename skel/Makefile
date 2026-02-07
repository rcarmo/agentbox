SHELL := /bin/sh

.DEFAULT_GOAL := help

# Generic Makefile template.
# Projects can extend/override these targets.

IMAGE ?= $(notdir $(CURDIR))
TAG ?= latest
FULL_IMAGE := $(IMAGE):$(TAG)
REGISTRY ?= ghcr.io
GHCR_OWNER ?= $(shell whoami)
GHCR_IMAGE := $(REGISTRY)/$(GHCR_OWNER)/$(IMAGE):$(TAG)

.PHONY: help
help: ## Show targets
	@grep -E '^[a-zA-Z0-9_.-]+:.*?##' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "%-18s %s\n", $$1, $$2}'

# =============================================================================
# Docker
# =============================================================================

.PHONY: build
docker-build: ## Build Docker image
	docker build -t $(FULL_IMAGE) .

.PHONY: dual-tag
dual-tag: docker-build ## Tag image as ghcr.io/<user>/<image>:<tag>
	docker tag $(FULL_IMAGE) $(GHCR_IMAGE)

.PHONY: tag-ghcr
tag-ghcr: dual-tag ## Convenience alias for dual-tag

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
# Release
# =============================================================================

.PHONY: bump-patch
bump-patch: ## Bump patch version in VERSION and create git tag
	@if [ ! -f VERSION ]; then echo "VERSION file not found"; exit 1; fi
	@OLD=$$(cat VERSION); \
	MAJOR=$$(echo $$OLD | cut -d. -f1); \
	MINOR=$$(echo $$OLD | cut -d. -f2); \
	PATCH=$$(echo $$OLD | cut -d. -f3); \
	NEW="$$MAJOR.$$MINOR.$$((PATCH + 1))"; \
	echo $$NEW > VERSION; \
	git add VERSION; \
	git commit -m "Bump version to $$NEW"; \
	git tag "v$$NEW"; \
	echo "Bumped version: $$OLD -> $$NEW (tagged v$$NEW)"

.PHONY: push
push: ## Push commits and current tag to origin
	@TAG=$$(git describe --tags --exact-match 2>/dev/null); \
	git push origin main; \
	if [ -n "$$TAG" ]; then \
		echo "Pushing tag $$TAG..."; \
		git push origin "$$TAG"; \
	else \
		echo "No tag on current commit"; \
	fi

# =============================================================================
# Cleanup
# =============================================================================

.PHONY: clean
clean: ## Remove local build/test artifacts (project-specific)
	@echo "No clean target defined for this project yet. Customize skel/Makefile." && exit 1
