.PHONY: test demo benchmark dashboard build
test:
	python -m pytest
	node --test sdk/typescript/test/*.test.ts
demo:
	pruefstand demo
benchmark:
	python scripts/reproduce.py
dashboard:
	python -m http.server 4173 --bind 127.0.0.1 --directory ratings/dist
build:
	python -m build
