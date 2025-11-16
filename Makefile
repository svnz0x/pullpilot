.PHONY: validate-config build-ui sync-updater

FRONTEND_DIR := apps/frontend
BACKEND_UI_DIST := apps/backend/src/pullpilot/resources/ui/dist

validate-config:
	python3 apps/backend/scripts/validate_config.py

build-ui:
	npm --prefix $(FRONTEND_DIR) run build
	rm -rf $(BACKEND_UI_DIST)
	mkdir -p $(BACKEND_UI_DIST)
	cp -R $(FRONTEND_DIR)/dist/. $(BACKEND_UI_DIST)

sync-updater:
	python3 apps/backend/tools/sync_updater.py
