# Wavetwin development commands

# Clean build artifacts
clean:
	rm -rf dist/ build/ *.egg-info/

# Install locally in development mode
install-local:
	uv pip install -e .

# Run the tool locally
run:
	uv run python -m wavetwin.cli

# Test uvx command from git repo
test-uvx:
	uvx https://github.com/paperbenni/wavetwin.git --help

# Show git remote info
git-info:
	@echo "Git remote: $(shell git remote get-url origin 2>/dev/null || echo 'No remote set')"

# View current version
version:
	uv version

# Update README with correct git URL
update-readme:
	@echo "Updating README with correct git URL..."
	@sed -i 's|uvx git@github.com:.*wavetwin.git|uvx git@github.com:paperbenni/wavetwin.git|' README.md

# Format code with ruff
format:
	ruff format .

# Lint code with ruff
lint:
	ruff check .

# Fix linting issues
fix:
	ruff check --fix .

# Default target
default:
	@echo "Available commands:"
	@echo "  clean         - Clean build artifacts"
	@echo "  install-local - Install locally in dev mode"
	@echo "  run           - Run locally"
	@echo "  format        - Format code with ruff"
	@echo "  lint          - Lint code with ruff"
	@echo "  fix           - Fix linting issues with ruff"
	@echo "  test-uvx      - Test uvx command from git repo"
	@echo "  git-info      - Show git remote URL"
	@echo "  version       - View current version"
	@echo "  update-readme - Update README with git URL"