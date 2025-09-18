.PHONY: deb clean install help

deb: clean
	@echo "🏗️  Building .deb package..."
	@./build-deb-package.sh

clean:
	@rm -rf build *.deb

install: deb
	@echo "📦 Installing package..."
	@sudo dpkg -i kbsearch_*.deb || true
	@sudo apt-get install -f -y

help:
	@echo "Available targets:"
	@echo "  deb     - Build .deb package"
	@echo "  install - Build and install"
	@echo "  clean   - Clean build files"
