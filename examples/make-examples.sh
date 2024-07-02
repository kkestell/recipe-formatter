#!/usr/bin/env bash
set -x

pushd "$(dirname "$0")" || exit 1

URL="https://www.allrecipes.com/recipe/17644/german-chocolate-cake-iii/"

python ../main.py -o example1.pdf -v $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example1-%d.jpg example1.pdf

python ../main.py -o example2.pdf -v -n $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example2-%d.jpg example2.pdf

python ../main.py -o example3.pdf -v -n -g $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example3-%d.jpg example3.pdf

python ../main.py -o example4.pdf -v -n -g -t $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example4-%d.jpg example4.pdf

python ../main.py -o example5.pdf -v -n -g -t -r "sub goat's milk" $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example5-%d.jpg example5.pdf

python ../main.py -o example6.pdf -v -n -g -t -r "sub goat's milk" -s 2 $URL || exit 1
gs -dNOPAUSE -dBATCH -sDEVICE=jpeg -dTextAlphaBits=4 -dGraphicsAlphaBits=4 -dJPEGQ=100 -r150 -sOutputFile=example6-%d.jpg example6.pdf

popd || exit 1
