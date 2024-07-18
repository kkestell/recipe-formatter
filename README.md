# Recipe Formatter

## Overview

Clean up and reformat recipes using llama.cpp and output JSON, markdown, LaTeX, or PDF.

## Usage

```
rf [OPTIONS] URL
```

### Options

#### `-o, --output OUTPUT`

Define the output file path for the formatted recipe.

If the file path contains the special token `{title}`, it will be replaced with the slugified recipe name.

If no output path is specified, the recipe will be printed to stdout.

#### `-n, --normalize`

Normalize the recipe by using standard unit abbreviations and formatting. This is a boolean flag.

#### `-f, --format FORMAT`

Supported formats: `json`, `md`, `tex`, and `pdf`.

If no format is specified, the output format will be inferred from the output file extension. If no output file is specified, or the specified output file has an extension that is not recognized, the recipe will be formatted as JSON.

#### `-t, --tips`

Include tips from reviews in the output. This is a boolean flag.

#### `-g, --group`

Add groups to ingredients and instructions in the output. This is a boolean flag.

#### `-s, --scale SCALE`

Scale the recipe by the given factor. The default scaling factor is `1.0`.

#### `-r, --revise REVISIONS`

Specify revisions to make to the recipe. This option allows for custom textual modifications.

#### `-v, --verbose`

Enable verbose mode to display additional information during processing. Defaults to `false`.

## Examples

See the [examples](examples) directory for more examples.

### PDF Output

```
URL='https://www.allrecipes.com/recipe/17644/german-chocolate-cake-iii/'
```

| ![Example 1](examples/example1-1.jpg) | ![Example 2](examples/example2-1.jpg) | ![Example 3](examples/example3-1.jpg) |
|:-------------------------------------:|:-------------------------------------:|:-------------------------------------:|
|       `rf -o example1.pdf $URL`       |     `rf -o example2.pdf -n $URL`      |    `rf -o example3.pdf -n -g $URL`    |

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
