.PHONY: help setup install test clean example build deploy-test deploy-prod deploy-both check

help:
	@echo "Excloud SDK - Simple Development Commands:"
	@echo "  setup      - Create virtual environment and install dependencies"
	@echo "  install    - Install package in development mode"
	@echo "  example    - Run the example script"
	@echo "  test       - Run tests"
	@echo "  clean      - Clean build artifacts and virtual environment"
	@echo ""
	@echo "PyPI Deployment Commands:"
	@echo "  build      - Build the package for distribution"
	@echo "  check      - Check the built package"
	@echo "  deploy-test - Deploy to Test PyPI"
	@echo "  deploy-prod - Deploy to production PyPI"
	@echo "  deploy-both - Deploy to both Test PyPI and production PyPI"

setup:
	@python3 setup_dev.py

install:
	pip install -e .

example:
	@if [ ! -f .venv/bin/python ]; then \
		echo "❌ Virtual environment not found. Run 'make setup' first."; \
		exit 1; \
	fi
	@if [ -z "$$EXCLOUD_API_KEY" ]; then \
		echo "❌ EXCLOUD_API_KEY environment variable not set."; \
		echo "💡 Set it with: export EXCLOUD_API_KEY=your_api_key"; \
		exit 1; \
	fi
	@echo "🚀 Running example..."
	.venv/bin/python example.py

test:
	python -m pytest tests/ -v

clean:
	@echo "🧹 Cleaning up..."
	rm -rf build/ dist/ *.egg-info/
	rm -rf .venv/
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
	@echo "✅ Clean complete!"

build:
	@echo "🔨 Building package..."
	python scripts/deploy.py --build-only --clean

check: build
	@echo "✅ Package built and checked successfully!"

deploy-test:
	@echo "🚀 Deploying to Test PyPI..."
	python scripts/deploy.py --target test --clean

deploy-prod:
	@echo "🚀 Deploying to production PyPI..."
	@read -p "Are you sure you want to deploy to production PyPI? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		python scripts/deploy.py --target prod --clean; \
	else \
		echo "❌ Deployment cancelled"; \
	fi

deploy-both:
	@echo "🚀 Deploying to both Test PyPI and production PyPI..."
	@read -p "Are you sure you want to deploy to BOTH Test PyPI and production PyPI? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		python scripts/deploy.py --target both --clean; \
	else \
		echo "❌ Deployment cancelled"; \
	fi
