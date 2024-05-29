# Recipe Formatter

## Overview

Uses the OpenAI API to reformat recipes from URLs or local files into markdown or PDF.

## Usage

Set the `OPENAI_API_KEY` environment variable before running the program.

Run the program by specifying either a URL or a file path for the recipe, and optionally define an output path:

- `-u, --url URL`: Specify the URL of the recipe to fetch and process.
- `-f, --file FILE`: Specify the path to a local file containing the recipe.
- `-o, --output OUTPUT`: Define the output file path for the formatted recipe (supports `.md` and `.pdf`). If not provided, the recipe is formatted as markdown and printed to stdout. If the filename is `$TITLE.pdf`, the filename will be automatically generated based on the recipe title.
- `-m, --model MODEL`: Specify the OpenAI model to use for recipe formatting (default: `gpt-4-turbo`).
- `-c, --clean`: Rewrite instructions to be more concise, clean up ingredients, and remove unnecessary information.

## Examples

```
export OPENAI_API_KEY='your-api-key'
```

### PDF

```
rf -u https://www.epicurious.com/recipes/food/views/flourless-chocolate-cake-14478 -o flourless-chocolate-cake.pdf
rf -u https://www.epicurious.com/recipes/food/views/flourless-chocolate-cake-14478 -o flourless-chocolate-cake-cleaned.pdf -c
```

|              ![](examples/flourless-chocolate-cake.jpg)               |                  ![](examples/flourless-chocolate-cake-cleaned.jpg)                   |
|:---------------------------------------------------------------------:|:-------------------------------------------------------------------------------------:|
| [flourless-chocolate-cake.pdf](examples/flourless-chocolate-cake.pdf) | [flourless-chocolate-cake-cleaned.pdf](examples/flourless-chocolate-cake-cleaned.pdf) |

### Markdown (Normal)

```
rf -u https://www.allrecipes.com/recipe/240784/easy-coleslaw-dressing
```

```markdown
# Easy Coleslaw Dressing

For a coleslaw recipe that's creamy and delicious, toss this easy-to-make, 5-minute homemade dressing with a bag of store-bought coleslaw mix.

## Ingredients

* 0.5 cup mayonnaise
* 2 tablespoons white sugar
* 1.5 tablespoons lemon juice
* 1 tablespoon vinegar
* 0.5 teaspoon ground black pepper
* 0.25 teaspoon salt

## Instructions

1. Gather all ingredients.
2. Whisk mayonnaise, sugar, lemon juice, vinegar, pepper, and salt together in a bowl until smooth and creamy.
3. Store in an airtight container.

## Notes

This dressing can be used immediately or stored in the refrigerator for up to a week.

Source: https://www.allrecipes.com/recipe/240784/easy-coleslaw-dressing/
```

### Markdown (Cleaned)

```
rf -u https://www.allrecipes.com/recipe/240784/easy-coleslaw-dressing -o easy-coleslaw-dressing-cleaned.md -c
```

```markdown
# Easy Coleslaw Dressing

For a coleslaw recipe that's creamy and delicious, toss this easy-to-make, 5-minute homemade dressing with a bag of store-bought coleslaw mix.

## Ingredients

* 1⁄2 c mayonnaise
* 2 tbsp white sugar
* 1 1⁄2 tbsp lemon juice
* 1 tbsp vinegar
* 1⁄2 tsp ground black pepper
* 1⁄4 tsp salt

## Instructions

1. Whisk mayonnaise, sugar, lemon juice, vinegar, pepper, and salt together in a bowl until smooth.
2. Transfer to an airtight container for storage.

Source: https://www.allrecipes.com/recipe/240784/easy-coleslaw-dressing/
```

## Dependencies

### Arch

```
sudo pacman -Sy texlive
```
