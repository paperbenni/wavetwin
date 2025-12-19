# Wavetwin publishing commands (UV-native 2025)

# Build the package
build:
	uv build

# Publish to PyPI (native uv publish)
publish: build
	uv publish

# Publish to test PyPI
publish-test: build
	uv publish --index testpypi

# Add test PyPI index to pyproject.toml
setup-test-index:
	@echo "Adding testpypi index to pyproject.toml..."
	@echo '[[tool.uv.index]]' >> pyproject.toml
	@echo 'name = "testpypi"' >> pyproject.toml
	@echo 'url = "https://test.pypi.org/simple/"' >> pyproject.toml
	@echo 'publish-url = "https://test.pypi.org/legacy/"' >> pyproject.toml
	@echo 'explicit = true' >> pyproject.toml

# Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info/

# Test installation locally
install-local:
	uv pip install -e .

# Run the tool locally
run:
	uv run python -m wavetwin.cli

# Test installation from test PyPI
install-test:
	uv tool install --index-url https://test.pypi.org/simple/ wavetwin

# Test installation from PyPI
install-pypi:
	uv tool install wavetwin

# Bump version (patch/minor/major)
bump-patch:
	uv version --bump patch

bump-minor:
	uv version --bump minor

bump-major:
	uv version --bump major

# Preview version bump
bump-dry:
	uv version --dry-run --bump patch

# View current version
version:
	uv version

# Default target
default:
	@echo "Available commands:"
	@echo "  build         - Build with uv"
	@echo "  publish       - Upload to PyPI (uv publish)"
	@echo "  publish-test  - Upload to test PyPI"
	@echo "  setup-test-index - Add test PyPI config"
	@echo "  clean         - Clean build artifacts"
	@echo "  install-local - Install locally in dev mode"
	@echo "  run           - Run locally"
	@echo "  install-test  - Install from test PyPI"
	@echo "  install-pypi  - Install from PyPI"
	@echo "  bump-patch    - Bump patch version"
	@echo "  bump-minor    - Bump minor version"
	@echo "  bump-major    - Bump major version"
	@echo "  bump-dry      - Preview version bump"
	@echo "  version       - View current version"

# Authentication help
auth-help:
	@echo "Set PyPI token with:"
	@echo "  export UV_PUBLISH_TOKEN=pypi-xxxxx"
	@echo "Or use --token flag:"
	@echo "  uv publish --token pypi-xxxxx"