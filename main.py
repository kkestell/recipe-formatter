import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import openai
import requests
from bs4 import BeautifulSoup
from openai import OpenAI, APITimeoutError
from openai.types.chat.completion_create_params import ResponseFormat
from slugify import slugify
from tqdm import tqdm


@dataclass
class Config:
    model: str
    clean: bool
    verbose: bool
    output_format: str
    output_path: str | None
    timeout: int
    max_attempts: int


p1 = """
Please return the recipe in JSON format with the following structure:
```json
{
  "title": "Recipe Title",
  "description": "Optional introductory text.",
  "ingredient_groups": [
    {
      "title": "",
      "ingredients": [
        "Ingredient 1",
        "Ingredient 2",
        "Ingredient 3"
      ]
    }
  ],
  "instruction_groups": [
    {
      "title": "",
      "instructions": [
        "Step 1",
        "Step 2",
        "Step 3"
      ]
    }
  ],
  "notes": "Optional notes."
}
Do not modify the recipe in any way. Just reformat it into the JSON structure above.
NOTE: If the recipe has multiple sections, such as "For the cake" and "For the frosting", please group the ingredients and instructions accordingly. Otherwise, you can leave the "title" fields empty.
"""

p2 = """
Update the ingredients in the recipe to strictly conform to the following style guide, and return the updated recipe JSON. Do not update any other parts of the recipe, such as the title, description, instructions, or notes.

Style Guide:
* List ingredients in the order they are used.
* Fractions must use U+2044 FRACTION SLASH ⁄ e.g. 1⁄2
* Measurements for cake and pie pans, etc. expressed in inches must use U+0022 QUOTATION MARK " for inches e.g. 9" and rectangular measurements must use U+00D7 MULTIPLICATION SIGN × e.g. 9×13"
* Temperatures must use U+00B0 DEGREE SIGN ° e.g. 350 °F. All temperatures must be in both Fahrenheit and Celsius e.g. 350 °F (175 °C)
* When ingredient amounts are packaged units e.g. stick of butter, can of beans, etc. also include the relevant measurement in parentheses e.g. "1 stick (1⁄2 c) unsalted butter" and "1 can (15 oz) black beans"
* Use the following standard abbreviations ea, c, g, tbsp, tsp, L, ml, oz, lb, kg, pt, qt, gal, fl oz, in, cm, mm, m, ft, °F, °C. Do not use periods after abbreviations.
* When an amount contains both weight and volume, list both with weight in parentheses _before_ the ingredient e.g. "1 c (120 g) flour" NOT "120 g (1 c) flour" or "1 c flour (120 g)"
* Remove any ingredients used for greasing / flouring pans.

Examples:
* 1 c (120 g) flour
* 1 tbsp olive oil
* 1⁄2 tsp salt
* 1 stick (1⁄2 c) unsalted butter
* 1 can (15 oz) black beans
* 1⁄2 c (120 ml) milk
* 1⁄4 c (60 ml) soy sauce
* 1 lb (450 g) ground beef
* 1⁄2 in (1 cm) piece of ginger
* 350 °F (175 °C)
* 9" round cake pan
* 9×13" baking dish
* 1 pt (500 ml) chicken stock
* salt and pepper to taste
"""

p3 = """
Update the instructions in the recipe to strictly conform to the following style guide, and return the updated recipe JSON. Do not update any other parts of the recipe, such as the title, description, ingredients, or notes.

Style Guide:
* Split or combine steps as needed to ensure each step is a single instruction.
* Use the imperative mood and present tense for instructions. Instructions should generally start with a verb.
* Do not include ingredient amounts in the instructions unless the recipe calls for multiple additions of the same ingredient. For example, "Add the flour" NOT "Add 1 c flour", unless the recipe calls for adding flour in multiple steps.
* Instructions should be a high level overview of the cooking process. Do not include detailed explanations or tips.
* Assume the reader has basic cooking knowledge and does not need detailed explanations of common cooking techniques. For example, "1. Pour marinade into a large, shallow dish. 2. Add chicken and turn to coat. 3. Cover and refrigerate overnight." should just be "1. Marinade chicken in the refrigerator overnight." And skip stuff like "until a toothpick inserted in the center comes out clean" and other common sense stuff.
* Be extremely terse. Each instruction should be as concise as possible while still being clear.
* Remove any steps that are unnecessary, e.g. "Gather the ingredients" or "Enjoy!"

Examples:
* Preheat oven to 350 °F.
* Mix flour, sugar, and salt in a bowl.
* Add eggs and milk to the dry ingredients.
* Stir until just combined.
* Pour batter into a greased pan.
* Bake for 30 minutes or until golden brown.
"""

p4 = """
Please regroup the ingredients and instructions as appropriate and return the updated recipe JSON. Do not update any other parts of the recipe, such as the title or description.
If the recipe does not lend itself to grouping, you can return the recipe as is. Please be judicious in your grouping and do not create unnecessary sections.

Examples of recipes that can be regrouped:
* Recipes with multiple sections, such as "For the cake" and "For the frosting".
* Recipes with multiple components, such as a main dish and a side dish.
* Recipes with a main dish and a sauce.
* Preparing a marinade and marinating the meat overnight in one group, and then cooking the meat in another group.

Style Guide:
* For instruction_group titles, prefer the gerund phrase form where appropriate, e.g. "Mixing the Ingredients" or "Baking the Cake".
* For ingredient_group titles, prefer the form "For the Cake" or "For the Frosting" where appropriate.
* Never create groups for "Wet Ingredients" or "Dry Ingredients", etc.
* Groups are for discrete components of the recipe, or dishes that are served together.

Please be EXTREMELY judicious in your grouping. Do not create unnecessary sections. If the recipe does not lend itself to grouping, you can return the recipe as is. Unnecessary grouping is far worse than no grouping at all.
If there is only one group in a section, you must leave the title empty.
"""

p5 = """
Please update the recipe's title, description, and notes to strictly conform to the following style guide, and return the updated recipe JSON. Do not update any other parts of the recipe, such as the ingredients or instructions.

Style Guide:
* Title should be concise and descriptive. Remove any unnecessary words or phrases e.g. "Delicious", "Best Ever", "Quick and Easy".
* Title should be in title case, with the first letter of each word capitalized.
* Title should not include the word "recipe" or "how to make".
* Descriptions are optional. No description is better than a pointless or redundant description.
* Descriptions are for describing the finished dish. Serving suggestions, history of the dish, etc. can go in the notes.
* Notes are optional. No notes are better than a pointless or redundant note.
* Remove any mentions of how delicious, healthy, easy, etc. the recipe is.
* Descriptions and notes should be in sentence case.
* Remove any editors notes, publication information, or other irrelevant information.
* Remove any personal anecdotes or stories.
* Adopt the dry, factual tone of a cooking textbook author.
* Ensure proper spelling, punctuation, and grammar.

Please do not add any new information to the title, description, or notes. Only update the existing text to conform to the style guide.
"""


class Pipeline:
    def __init__(self, config, steps):
        self.config = config
        self.steps = steps
        self.client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

    def run(self, recipe):
        for i, step in tqdm(enumerate(self.steps), total=len(self.steps), desc="Processing Steps"):
            attempts = 0
            while attempts < 3:
                attempts += 1
                try:
                    recipe = self.prompt(step, recipe)
                    break
                except openai.APITimeoutError as e:
                    if attempts == 3:
                        print(f"timed out after 3 attempts: {e}")
                        raise e
                    continue
        return recipe

    def addStep(self, step):
        self.steps.append(step)

    def prompt(self, prompt, recipe):
        chat_completion = self.client.chat.completions.create(
            messages=[{"role": "system", "content": prompt}, {"role": "user", "content": recipe}],
            response_format=ResponseFormat(type="json_object"),
            model=self.config.model,
            #temperature=self.config.temperature,
            temperature=0.5,
            timeout=self.config.timeout
        )
        return chat_completion.choices[0].message.content


def fetch_and_parse(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
        'Referer': 'https://www.google.com/'
    }
    try:
        response = requests.get(url, headers=headers)
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


def extract_recipe_text(soup):
    for container in soup.find_all():
        if container.find(string=lambda text: 'ingredients' in text.lower()) and (container.find(string=lambda text: 'instructions' in text.lower()) or container.find(string=lambda text: 'directions' in text.lower())):
            return container.get_text(separator=' ', strip=True)


def extract_recipe_content(soup):
    recipe_json = extract_recipe_json(soup)
    if recipe_json:
        return format_recipe(recipe_json)
    recipe_text = extract_recipe_text(soup)
    if recipe_text:
        return recipe_text
    raise ValueError("No recipe content found.")


def fetch_recipe_from_url(url):
    soup = fetch_and_parse(url)
    return extract_recipe_content(soup)


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


def json_to_latex(json_text):
    title = json_text.get('title', 'No Title')
    description = json_text.get('description', None)
    ingredient_groups = json_text.get('ingredient_groups', [])
    instruction_groups = json_text.get('instruction_groups', [])
    notes = json_text.get('notes', None)
    source = json_text.get('source', None)
    source_latex = "\\fancyfoot[C]{\\footnotesize " + escape_latex(source) + "}" if source else ""

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
    latex.append("\\raggedright")

    for ingredient_group in ingredient_groups:
        if ingredient_group.get('title'):
            latex.append(f"\\subsection*{{{ingredient_group['title']}}}")
        latex.append("\\begin{itemize}[leftmargin=*]")
        for ingredient in ingredient_group['ingredients']:
            latex.append(f"\\item {fix_fractions(escape_latex(ingredient))}")
        latex.append("\\end{itemize}")

    latex.append("\\switchcolumn")
    latex.append("\\section*{Instructions}")

    for instruction_group in instruction_groups:
        if instruction_group.get('title'):
            latex.append(f"\\subsection*{{{instruction_group['title']}}}")
        latex.append("\\begin{enumerate}[leftmargin=*]")
        for i, instruction in enumerate(instruction_group['instructions'], 1):
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
    ingredient_groups = recipe.get('ingredient_groups', [])
    instruction_groups = recipe.get('instruction_groups', [])
    notes = recipe.get('notes', None)
    source = recipe.get('source', None)

    markdown = f"# {title}\n\n"

    if description:
        markdown += f"{description}\n\n"

    markdown += "## Ingredients\n\n"
    for ingredient_group in ingredient_groups:
        if ingredient_group.get('title'):
            markdown += f"### {ingredient_group['title']}\n\n"
        for ingredient in ingredient_group['ingredients']:
            markdown += f"* {ingredient}\n"
        markdown += "\n"

    markdown += "\n## Instructions\n\n"
    for instruction_group in instruction_groups:
        if instruction_group.get('title'):
            markdown += f"### {instruction_group['title']}\n\n"
        for i, instruction in enumerate(instruction_group['instructions'], 1):
            markdown += f"{i}. {instruction}\n"
        markdown += "\n"

    if notes:
        markdown += "\n## Notes\n\n"
        markdown += notes

    if source:
        markdown += f"\n\nSource: {source}"

    return markdown


def write_output(recipe, config):
    output, mode = None, 'w'
    if config.output_format == 'tex':
        output = json_to_latex(recipe)
    elif config.output_format == 'json':
        output = json.dumps(recipe, ensure_ascii=False, indent=4)
    elif config.output_format == 'pdf':
        output, mode = generate_pdf(recipe, config.verbose), 'wb'
    else:
        output = recipe_to_markdown(recipe)

    if config.output_path:
        title = slugify(recipe.get('title', 'Recipe'))
        output_file = config.output_path.replace('{title}', title)
        with open(output_file, mode) as f:
            f.write(output)
    else:
        if mode == 'wb':
            sys.stdout.buffer.write(output)
        else:
            print(output)


def generate_pdf(recipe, verbose):
    latex_content = json_to_latex(recipe)
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file = os.path.join(temp_dir, 'recipe.tex')
        with open(temp_file, 'w') as f:
            f.write(latex_content)
        subprocess_args = ['xelatex', temp_file, '-output-directory', temp_dir]
        subprocess.run(subprocess_args, cwd=temp_dir, stdout=subprocess.DEVNULL if not verbose else None)
        pdf_file = os.path.join(temp_dir, 'recipe.pdf')
        with open(pdf_file, 'rb') as f:
            return f.read()


def main():
    parser = argparse.ArgumentParser(description="Reformat and optionally rewrite a recipe from a URL or file.")

    parser.add_argument("file_or_url", type=str, help="URL or file path to the recipe to process.")

    parser.add_argument("-o", "--output", type=str, help="Output file to write the processed recipe. If not provided, print to stdout.")
    parser.add_argument("-f", "--format", type=str, help="Output format (md, tex, pdf, json)")

    parser.add_argument("-c", "--clean", action="store_true", help="Clean up the recipe")

    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity")

    parser.add_argument("-m", "--model", type=str, default="gpt-4o", help="OpenAI model to use for rewriting the recipe.")
    # TODO
    # parser.add_argument("-p", "--prompt", type=str, help="Prompt to use for cleaning up the recipe (implies --clean)")
    # parser.add_argument("-b", "--built-in-prompt", action="store_true", help="Display the built-in prompt")

    args = parser.parse_args()

    fmt = "json"
    if args.format:
        fmt = args.format
    elif args.output:
        extension = os.path.splitext(args.output)[1]
        if extension in ['.md', '.tex', '.pdf', '.json']:
            fmt = extension[1:]

    config = Config(model=args.model, clean=args.clean, verbose=args.verbose, output_format=fmt,
                    output_path=args.output, timeout=30, max_attempts=3)

    is_url = args.file_or_url.startswith('http')

    if is_url:
        recipe = fetch_recipe_from_url(args.file_or_url)
    else:
        recipe = read_recipe_from_file(args.file_or_url)

    steps = [p1]
    if args.clean:
        steps.extend([p2, p3, p4, p5])

    pipeline = Pipeline(config, steps)
    processed_recipe = pipeline.run(recipe)
    processed_recipe = json.loads(processed_recipe)

    if len(processed_recipe['ingredient_groups']) == 1:
        processed_recipe['ingredient_groups'][0]['title'] = ''
    if len(processed_recipe['instruction_groups']) == 1:
        processed_recipe['instruction_groups'][0]['title'] = ''

    if is_url:
        processed_recipe['source'] = args.file_or_url

    write_output(processed_recipe, config)


if __name__ == "__main__":
    main()
