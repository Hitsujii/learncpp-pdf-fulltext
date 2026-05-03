PIXI_PATH ?= $(HOME)/.pixi/bin/pixi

install:
	curl -fsSL https://pixi.sh/install.sh | bash
	$(PIXI_PATH) install
	$(PIXI_PATH) run python -m playwright install chromium

run:
	$(PIXI_PATH) run python -m book

clean:
	rm -rf .tmp
	rm -f learncpp.pdf

.PHONY: book
book:
	$(MAKE) install
	$(MAKE) run