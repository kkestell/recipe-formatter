install:
	pdm run python -m nuitka --standalone --onefile --output-filename=rf src/recipe_formatter/main.py
	mkdir -p ~/.local/bin/
	cp -f rf ~/.local/bin/

#asciinema rec demo.cast
#rf -v -n -f md https://www.allrecipes.com/recipe/17644/german-chocolate-cake-iii/
# asciinema rec -c "rf -v -g -f md -r 'scale by 2x' https://www.allrecipes.com/recipe/9622/quick-chocolate-frosting/" demo.cast --overwrite
