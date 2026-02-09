REMOTE_HOST := home.lab
REMOTE_PATH := /home/jack/projects/personal/tw-homedog

.PHONY: sync deploy down up sync-db

sync:
	rsync -avz --delete \
		--exclude='.venv/' \
		--exclude='__pycache__/' \
		--exclude='.pytest_cache/' \
		--exclude='*.egg-info/' \
		--exclude='data/*.db' \
		--exclude='data/*.db-wal' \
		--exclude='data/*.db-shm' \
		--exclude='data/map_cache/' \
		--exclude='.DS_Store' \
		--exclude='.env' \
		--exclude='config.yaml' \
		--exclude='.claude/' \
		--exclude='.agent/' \
		--exclude='.augment/' \
		--exclude='.codex/' \
		./ $(REMOTE_HOST):$(REMOTE_PATH)/

down:
	ssh $(REMOTE_HOST) "cd $(REMOTE_PATH) && docker compose down"

up:
	ssh $(REMOTE_HOST) "cd $(REMOTE_PATH) && docker compose up --build -d"

deploy: sync down up

sync-db:
	@mkdir -p data
	rsync -avz $(REMOTE_HOST):$(REMOTE_PATH)/data/homedog.db data/homedog.db
