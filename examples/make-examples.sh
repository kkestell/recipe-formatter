#!/usr/bin/env bash

URL='https://www.epicurious.com/recipes/food/views/philly-fluff-cake'

pushd "$(dirname "$0")" || exit 1

rf -u $URL -o example.pdf || exit 1
convert -density 100 -quality 100 -flatten example.pdf example.jpg

rf -u $URL -o example-cleaned.pdf -c || exit 1
convert -density 100 -quality 100 -flatten example-cleaned.pdf example-cleaned.jpg

popd || exit 1
