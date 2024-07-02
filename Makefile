.PHONY: install

install:
	python -m nuitka --standalone --onefile --no-deployment-flag=self-execution --output-filename=rf main.py
	mv -f rf ~/.local/bin
