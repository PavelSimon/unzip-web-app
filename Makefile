.PHONY: run setup

setup:
	uv venv .venv
	uv pip install -r requirements.txt

run:
	uv run python main.py
