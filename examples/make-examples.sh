#!/usr/bin/env bash
set -x

pushd "$(dirname "$0")" || exit 1

URL="https://www.allrecipes.com/recipe/17644/german-chocolate-cake-iii/"

pdm run python ../src/recipe_formatter/main.py -o example1.pdf $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example1-%d.jpg example1.pdf

pdm run python ../src/recipe_formatter/main.py -o example2.pdf -n $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example2-%d.jpg example2.pdf

pdm run python ../src/recipe_formatter/main.py -o example3.pdf -n -g $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example3-%d.jpg example3.pdf

pdm run python ../src/recipe_formatter/main.py -o example4.pdf -n -g -r "sub goat's milk" $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example4-%d.jpg example4.pdf


popd || exit 1
