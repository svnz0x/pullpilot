.PHONY: validate-config build-ui

validate-config:
python3 scripts/validate_config.py

build-ui:
npm run build
