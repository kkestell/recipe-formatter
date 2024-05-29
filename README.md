# Recipe Formatter

## Overview

Uses the OpenAI API to reformat a recipe from a URL or local file and converts it into markdown or PDF.

## Usage

Set the `OPENAI_API_KEY` environment variable before running the program.

Run the program by specifying either a URL or a file path for the recipe, and optionally define an output path:

```commandline
rf { -u URL | -f FILE } [ -o OUTPUT ] [ -m MODEL ] [ -c ] [ -v ]
```

### Arguments

#### `-u, --url URL`

Specify the URL of the recipe to fetch and process.

#### `-f, --file FILE`

Specify the path to a local file containing the recipe.

#### `-o, --output OUTPUT`

Define the output file format and path for the formatted recipe.

Supported formats: `.json`, `.md`, `.tex`, and `.pdf`.

If the file path contains the special token `{title}`, it will be replaced with the slugified recipe name.

If no output path is specified, the recipe will be printed to stdout in JSON format.

#### `-m, --model MODEL`

Specify the OpenAI model to use for recipe formatting. Defaults to `gpt-4-turbo`.

#### `-c, --clean`

Rewrite instructions to be more concise, clean up ingredients, and remove unnecessary information. Defaults to `false`.

#### `-v, --verbose`

Enable verbose mode to display additional information during processing. Defaults to `false`.

## Examples

```
export OPENAI_API_KEY='your-api-key'
```

### PDF

```
rf -u https://www.epicurious.com/recipes/food/views/flourless-chocolate-cake-14478 -o flourless-chocolate-cake.pdf
rf -c -u https://www.epicurious.com/recipes/food/views/flourless-chocolate-cake-14478 -o flourless-chocolate-cake-cleaned.pdf
```

|            ![](examples/example.jpg)            |                  ![](examples/example-cleaned.jpg)                   |
|:----------------------------------------------------:|:--------------------------------------------------------------------:|
| [example.pdf](examples/flourless-chocolate-cake.pdf) | [flourless-chocolate-cake-cleaned.pdf](examples/example-cleaned.pdf) |

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
rf -c -u https://www.allrecipes.com/recipe/240784/easy-coleslaw-dressing -o easy-coleslaw-dressing-cleaned.md
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

### Python

Python 3.8+ should be fine. Creating a self-contained binary requires a Python compatible with Nuitka (tested with Python 3.11).

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Arch

```
sudo pacman -Sy texlive adobe-source-serif-fonts
```

## Installation

Build a self-contained executable (`rf`) using Nuitka and install to `~/.local/bin`:

```
make install
```
