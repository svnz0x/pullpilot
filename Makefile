.PHONY: validate-config build-ui

validate-config:
python3 apps/backend/scripts/validate_config.py

build-ui:
npm --prefix apps/frontend run build
