help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS=":.*##"} {printf "%-16s %s\n", $$1, $$2}'

up: ## Start all services in detached mode
	docker compose up -d

down: ## Stop and remove services
	docker compose down

enter-%: ## Enter tmux in the named agent container (usage: make enter-<name>)
	docker exec -u agent -it agent-$* tmux new -As0
