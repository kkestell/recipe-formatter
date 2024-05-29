import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from openai.types.chat.completion_create_params import ResponseFormat
from slugify import slugify


system_prompt = """
Please return the recipe in JSON format with the following structure:

```json
{
  "title": "Recipe Title",
  "description": "Optional introductory text.",
  "ingredients": [
    "Ingredient 1",
    "Ingredient 2",
    "Ingredient 3"
  ],
  "instructions": [
    "Step 1",
    "Step 2",
    "Step 3"
  ],
  "notes": "Optional notes."
}
```
"""

clean_prompt = """
Additionally, please rewrite the recipe to strictly conform to the following guidelines. None of these are optional:

* Fractions must use U+2044 FRACTION SLASH ⁄ e.g. 1⁄2
* Dimensions must use U+00D7 MULTIPLICATION SIGN × e.g. 4×8"
* Temperatures must use U+00B0 DEGREE SIGN ° e.g. 350 °F.
* All temperatures must be in both Fahrenheit and Celsius e.g. "350 °F (175 °C)"
* All amounts must use standard abbreviations: 1 c, 3 tsp, 4 tbsp, 5 g, 6 qt, 4 ea (for each), 5 g, 6 ml, 7 oz, 8 lb, 9 kg, 10 L
* When ingredient amounts are standard units e.g. stick of butter, can of beans, etc. also include the relevant measurement e.g. "1 stick (1⁄2 c) unsalted butter"
* Units and Measurements: Use the following standard abbreviations c, g, tbsp, tsp, L, ml, oz, lb, kg, pt, qt, gal, fl oz, in, cm, mm, m, ft, °F, °C. Do not use periods after abbreviations.
* When an amount contains both weight and volume, list both with weight in parentheses _before_ the ingredient e.g. "1 c (120 g) flour" NOT "120 g (1 c) flour" or "1 c flour (120 g)"
* List ingredients in the order they are used.
* Remove any unnecessary qualifiers e.g. "fine-quality chocolate" should be "chocolate" and "farm fresh eggs" should be "eggs"
* Rewrite the instructions to be concise and to the point. Do not include unnecessary words or phrases. Assume the reader is an experienced cook and omit anything that is obvious. THIS IS EXTREMELY IMPORTANT!!!
* Remove any notes of when / where the recipe was first published or information about the publisher.
* Remove any fluffy language, claims about how good the recipe is, personal anecdotes, etc.
"""


def rewrite_recipe(recipe_text, model, clean):
    prompt = system_prompt
    if clean:
        prompt += "\n\n" + clean_prompt
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    chat_completion = client.chat.completions.create(
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": recipe_text}],
        model=model,
        response_format=ResponseFormat(type="json_object"),
        temperature=0
    )
    json_text = chat_completion.choices[0].message.content
    return json.loads(json_text)


def fetch_and_parse(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup
    except requests.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None


def extract_recipe_json(soup):
    try:
        scripts = soup.find_all('script', {'type': 'application/ld+json'})
        for script in scripts:
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") == "Recipe" or "Recipe" in item.get("@type", []):
                            return item
                else:
                    if data.get("@type") == "Recipe" or "Recipe" in data.get("@type", []):
                        return data
            except json.JSONDecodeError:
                print(f"Failed to parse JSON: {script.string}")
                continue
        return None
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None


def format_recipe(json_data):
    title = json_data.get('name', 'No Title')
    description = json_data.get('description', 'No description available.')
    formatted_recipe = f"# {title}\n\n{description}\n\n## Ingredients\n"
    ingredients = json_data.get('recipeIngredient', [])
    for ingredient in ingredients:
        formatted_recipe += f"* {ingredient}\n"
    formatted_recipe += "\n## Instructions\n"
    steps = json_data.get('recipeInstructions', [])
    for i, step in enumerate(steps, 1):
        formatted_recipe += f"{i}. {step['text']}\n"
    return formatted_recipe


def fetch_recipe_from_url(url):
    soup = fetch_and_parse(url)
    recipe_json = extract_recipe_json(soup)
    return format_recipe(recipe_json)


def read_recipe_from_file(file_path):
    with open(file_path, 'r') as file:
        return file.read()


def escape_latex(text):
    mapping = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}'
    }
    return "".join(mapping.get(c, c) for c in text)


def fix_fractions(text):
    return re.sub(r'(\d)/(\d)', r'\1⁄\2', text)


def node_to_latex(node):
    if node.tag == "p":
        return node.children[0].content + "\\par"
    elif node.tag == "h3":
        return "\\subsection*{" + node.children[0].content + "}\n"
    elif node.tag == "ol":
        latex = "\\begin{enumerate}[leftmargin=*]\n"
        for item in node.children:
            latex += "    \\item " + escape_latex(item.children[0].children[0].content) + "\n"
        latex += "\\end{enumerate}\n"
        return latex
    elif node.tag == "ul":
        latex = "\\begin{itemize}[leftmargin=*]\n"
        for item in node.children:
            latex += "    \\item " + escape_latex(item.children[0].children[0].content) + "\n"
        latex += "\\end{itemize}\n"
        return latex
    elif node.tag == "table":
        latex = "\\begin{tabular}{@{}ll}\n"
        for row in node.children[1]:
            amount = escape_latex(row.children[0].children[0].content)
            ingredient = escape_latex(row.children[1].children[0].content)
            latex += fix_fractions(amount) + " & " + ingredient + " \\\\\n"
        latex += "\\end{tabular}\n"
        return latex
    else:
        raise ValueError(f"Unsupported node type: {node.tag}")


def json_to_latex(json):
    title = json.get('title', 'No Title')
    description = json.get('description', None)
    ingredients = json.get('ingredients', [])
    instructions = json.get('instructions', [])
    notes = json.get('notes', None)
    source = json.get('source', None)

    source_latex = ""
    if source:
        source_latex = "\\fancyfoot[C]{\\footnotesize " + escape_latex(source) + "}"

    latex = [
        "\\documentclass[11pt]{article}",
        "\\usepackage{fontspec}",
        "\\usepackage{geometry}",
        "\\usepackage{enumitem}",
        "\\usepackage{graphicx}",
        "\\usepackage{paracol}",
        "\\usepackage{microtype}",
        "\\usepackage{parskip}",
        "\\usepackage{fancyhdr}",
        "\\geometry{letterpaper, margin=0.75in}",
        "\\setmainfont{Source Serif 4}",
        "\\newfontfamily\\headingfont{Source Serif 4}",
        "\\pagestyle{fancy}",
        "\\fancyhf{}",
        "\\renewcommand{\\headrulewidth}{0pt}",
        source_latex,
        "\\begin{document}",
        "\\setlist[enumerate,1]{itemsep=0em}",
        "\\begin{center}",
        "{\\huge \\bfseries \\headingfont " + escape_latex(title) + "}",
        "\\end{center}"
    ]
    if description:
        latex.append("\\vspace{1em}")
        latex.append(description)
    latex.append("\\vspace{1em}")
    latex.append("\\columnratio{0.35}")
    latex.append("\\begin{paracol}{2}")
    latex.append("\\setlength{\\columnsep}{2em}")
    latex.append("\\sloppy")
    latex.append("\\section*{Ingredients}")
    latex.append("\\begin{itemize}[leftmargin=*]")
    for ingredient in ingredients:
        latex.append(f"\\item {ingredient}")
    latex.append("\\end{itemize}")
    latex.append("\\switchcolumn")
    latex.append("\\section*{Instructions}")
    latex.append("\\begin{enumerate}[leftmargin=*]")
    for instruction in instructions:
        latex.append(f"\\item {instruction}")
    latex.append("\\end{enumerate}")
    latex.append("\\end{paracol}")
    if notes:
        latex.append("\\section*{Notes}")
        latex.append(notes)
    latex.append("\\end{document}")

    return "\n".join(latex)


def recipe_to_markdown(recipe):
    title = recipe.get('title', 'Recipe')
    description = recipe.get('description', None)
    ingredients = recipe.get('ingredients', [])
    instructions = recipe.get('instructions', [])
    notes = recipe.get('notes', None)
    source = recipe.get('source', None)

    markdown = f"# {title}\n\n"
    if description:
        markdown += f"{description}\n\n"
    markdown += "## Ingredients\n\n"
    for ingredient in ingredients:
        markdown += f"* {ingredient}\n"
    markdown += "\n## Instructions\n\n"
    for i, instruction in enumerate(instructions, 1):
        markdown += f"{i}. {instruction}\n"
    if notes:
        markdown += "\n## Notes\n\n"
        markdown += notes
    if source:
        markdown += f"\n\nSource: {source}"
    return markdown


def write_output(recipe, output_file=None):
    if output_file:
        if output_file == '$TITLE.pdf':
            title = slugify(recipe.get('title', 'Recipe'))
            output_file = f"{title}.pdf"
        extension = os.path.splitext(output_file)[1]
        if extension == '.pdf':
            latex = json_to_latex(recipe)
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_file = os.path.join(temp_dir, 'recipe.tex')
                with open(temp_file, 'w') as f:
                    f.write(latex)
                subprocess.run(['xelatex', temp_file], cwd=temp_dir)
                pdf_file = os.path.join(temp_dir, 'recipe.pdf')
                shutil.move(pdf_file, output_file)
        else:
            with open(output_file, 'w') as f:
                markdown = recipe_to_markdown(recipe)
                f.write(markdown)
    else:
        print(recipe)


def main():
    parser = argparse.ArgumentParser(description="Process and reformat a recipe from a URL or file.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", "--url", type=str, help="URL of the recipe to process.")
    group.add_argument("-f", "--file", type=str, help="File containing the recipe to process.")
    parser.add_argument("-o", "--output", type=str,
                        help="Output file to write the processed recipe. If not provided, print to stdout.")
    parser.add_argument("-c", "--clean", action="store_true", help="Clean up the recipe")
    parser.add_argument("-m", "--model", type=str, default="gpt-4-turbo",
                        help="The model to use for rewriting the recipe.")
    args = parser.parse_args()
    if args.url:
        recipe = fetch_recipe_from_url(args.url)
    else:
        recipe = read_recipe_from_file(args.file)
    processed_recipe = rewrite_recipe(recipe, args.model, args.clean)
    if args.url:
        processed_recipe['source'] = args.url
    write_output(processed_recipe, args.output)


if __name__ == "__main__":
    main()
