.PHONY: validate-config build-ui sync-updater

validate-config:
python3 apps/backend/scripts/validate_config.py

build-ui:
npm --prefix apps/frontend run build

sync-updater:
python3 apps/backend/tools/sync_updater.py
