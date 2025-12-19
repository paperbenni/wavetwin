# Wavetwin publishing commands

# Build the package
build:
	python -m build

# Upload to PyPI (requires authentication)
publish: build
	twine upload dist/*

# Upload to test PyPI for testing
publish-test: build
	twine upload --repository testpypi dist/*

# Install from test PyPI for testing
install-test:
	uv tool install --index-url https://test.pypi.org/simple/ wavetwin

# Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info/

# Check package with twine
check:
	twine check dist/*

# Install locally in development mode
install-dev:
	pip install -e .

# Run the tool
run:
	python -m wavetwin.cli

# Default target
default:
	@echo "Available commands:"
	@echo "  build         - Build the package"
	@echo "  publish       - Upload to PyPI"
	@echo "  publish-test  - Upload to test PyPI"
	@echo "  install-test  - Install from test PyPI"
	@echo "  clean         - Clean build artifacts"
	@echo "  check         - Check package with twine"
	@echo "  install-dev   - Install in development mode"
	@echo "  run           - Run the tool locally"