.PHONY: install

install:
	python -m nuitka --standalone --onefile --no-deployment-flag=self-execution --output-filename=rf main.py
	mkdir -p ~/.local/bin/
	mkdir -p ~/.config/recipe-formatter/
	cp -r prompts/ ~/.config/recipe-formatter/
	mv -f rf ~/.local/bin/