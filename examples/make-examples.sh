#!/usr/bin/env bash
set -x

urls=(
  'https://www.bonappetit.com/recipe/bas-best-chocolate-chip-cookies'
  'https://smittenkitchen.com/2022/05/double-chocolate-chip-muffins/'
  'https://www.foodandwine.com/recipes/jamaican-jerk-chicken'
  'https://www.allrecipes.com/recipe/7399/tres-leches-milk-cake/'
  'https://www.epicurious.com/recipes/food/views/flourless-chocolate-cake-14478'
)

pushd "$(dirname "$0")" || exit 1

for i in "${!urls[@]}"; do
    url="${urls[i]}"

    python ../main.py -m gpt-4o -o "example$(($i+1)).pdf" "$url" || exit 1
    convert -density 100 -quality 100 -flatten "example$(($i+1)).pdf" "example$(($i+1)).jpg"

    python ../main.py -m gpt-4o -o "example$(($i+1))-cleaned.pdf" -c "$url" || exit 1
    convert -density 100 -quality 100 -flatten "example$(($i+1))-cleaned.pdf" "example$(($i+1))-cleaned.jpg"
done

popd || exit 1
