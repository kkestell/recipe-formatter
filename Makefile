.PHONY: install

install:
	python -m nuitka --standalone --onefile --no-deployment-flag=self-execution --output-filename=rf main.py
	rm ~/.local/bin/rf
	mv rf ~/.local/bin
