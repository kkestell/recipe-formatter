.PHONY: install

install:
	python -m nuitka --standalone --onefile --output-filename=rf main.py
	rm ~/.local/bin/rf
	mv rf ~/.local/bin
