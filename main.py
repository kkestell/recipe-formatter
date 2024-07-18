import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from typing import List, Optional, Type, Callable

import instructor
import llama_cpp
import requests
from bs4 import BeautifulSoup
from instructor import patch, Mode
from llama_cpp.llama_speculative import LlamaPromptLookupDecoding
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.json import JSON
from rich.live import Live
from slugify import slugify


class IngredientGroup(BaseModel):
    title: str
    ingredients: List[str]


class InstructionGroup(BaseModel):
    title: str
    instructions: List[str]


class RecipeModel(BaseModel):
    title: str
    description: Optional[str]
    ingredient_groups: List[IngredientGroup]
    instruction_groups: List[InstructionGroup]


class RecipeIngredientsModel(BaseModel):
    ingredient_groups: List[IngredientGroup]


class RecipeInstructionsModel(BaseModel):
    instruction_groups: List[InstructionGroup]


class Llama:
    def __init__(self):
        self.llama = llama_cpp.Llama(
            model_path="/home/kyle/src/public/recipe-formatter/models/gemma-2-9b-it-Q6_K.gguf",
            # model_path="/home/kyle/src/public/recipe-formatter/models/Phi-3-mini-4k-instruct-fp16.gguf",
            n_gpu_layers=-1,
            chat_format="chatml",
            n_ctx=8192,
            draft_model=LlamaPromptLookupDecoding(num_pred_tokens=2),
            logits_all=True,
            verbose=False,
            temperature=0
        )
        self.create = patch(
            create=self.llama.create_chat_completion_openai_v1,
            mode=Mode.JSON_SCHEMA,
        )
        self.console = Console()
        self.live = Live(console=self.console)

    def _create_response_stream(self, prompt: str, response_model: Type[BaseModel], response_schema, callback: Callable):
        self.console.print(f"[dim]{prompt}[/dim]", highlight=False)
        response_stream = self.create(
            response_model=instructor.Partial[response_model],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object", "schema": response_schema},
            max_tokens=8192,
            stream=True
        )
        final_obj = None
        with self.live:
            for response in response_stream:
                try:
                    obj = response.model_dump()
                    callback(obj)  # Invoke callback with the new data
                    final_obj = obj
                except ValidationError as e:
                    self.console.print(f"Validation error: {e}")
        return final_obj

    def prompt_all(self, prompt: str, callback: Callable) -> Optional[RecipeModel]:
        response_schema = self._recipe_schema()
        return self._create_response_stream(prompt, RecipeModel, response_schema, callback)

    def prompt_ingredients(self, prompt: str, callback: Callable) -> Optional[RecipeIngredientsModel]:
        response_schema = {
            "type": "object",
            "properties": {
                "ingredient_groups": {
                    "type": "array",
                    "items": self._group_schema("ingredients")
                }
            },
            "required": ["ingredient_groups"]
        }
        return self._create_response_stream(prompt, RecipeIngredientsModel, response_schema, callback)

    def prompt_instructions(self, prompt: str, callback: Callable) -> Optional[RecipeInstructionsModel]:
        response_schema = {
            "type": "object",
            "properties": {
                "instruction_groups": {
                    "type": "array",
                    "items": self._group_schema("instructions")
                }
            },
            "required": ["instruction_groups"]
        }
        return self._create_response_stream(prompt, RecipeInstructionsModel, response_schema, callback)

    def _group_schema(self, item_type: str):
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                item_type: {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["title", item_type]
        }

    def _recipe_schema(self):
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
                "ingredient_groups": {
                    "type": "array",
                    "items": self._group_schema("ingredients")
                },
                "instruction_groups": {
                    "type": "array",
                    "items": self._group_schema("instructions")
                }
            },
            "required": ["title", "ingredient_groups", "instruction_groups"]
        }


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

    reviews = []
    for review in json_data.get('review', []):
        reviews.append(review['reviewBody'])

    return formatted_recipe, reviews


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
        return recipe_text, []
    raise ValueError("No recipe content found.")


def fetch_recipe_from_url(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36',
        'Referer': 'https://www.google.com/'
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    if not soup:
        raise ValueError("Failed to parse the recipe page.")

    return extract_recipe_content(soup)


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


def normalize_fractions(val):
    val = re.sub(r'\(\$.+\)', '', val)
    normalized = _decimal_to_fraction(_fraction_to_decimal(val))
    normalized = re.sub(r'(\d+)/(\d+)', r'\1⁄\2', normalized)
    return normalized


def normalize_temperatures(val):
    val = re.sub(r'(\d{3}) degrees F', r'\1 °F', val)
    val = re.sub(r'(\d{3}) degrees C', r'\1 °C', val)
    return val


def _decimal_to_fraction(val):
    def replace_decimal(match):
        d = match.groups(0)[0]
        f = _mixed_number(Fraction(d).limit_denominator(8))
        return f
    result = re.sub(r'([0-9]*\.?[0-9]+)', replace_decimal, val)
    return result


def _mixed_number(fraction: Fraction) -> str:
    whole = fraction.numerator // fraction.denominator
    remainder = fraction.numerator % fraction.denominator
    if whole == 0:
        return f"{fraction.numerator}/{fraction.denominator}"
    elif remainder == 0:
        return str(whole)
    else:
        return f"{whole} {remainder}/{fraction.denominator}"


def _fraction_to_decimal(val):
    def replace_fraction(s):
        i, f = s.groups(0)
        f = Fraction(f)
        return str(int(i) + float(f))
    result = re.sub(r'(?:(\d+)[-\s])?(\d+/\d+)', replace_fraction, val)
    return result


def _unicode_fraction_to_ascii(val):
    fractions = {
        "¼": "1/4",
        "⅓": "1/3",
        "½": "1/2",
        "⅖": "2/5",
        "⅗": "3/5",
        "⅘": "4/5",
        "⅙": "1/6",
        "⅐": "1/7",
        "⅛": "1/8",
        "⅑": "1/9",
        "⅒": "1/10",
        "⅚": "5/6",
        "⅜": "3/8",
        "⅝": "5/8",
        "⅞": "7/8",
        "¾": "3/4",
        "⅔": "2/3",
        "⅕": "1/5"
    }

    for unicode_frac, ascii_frac in fractions.items():
        val = val.replace(unicode_frac, ascii_frac)

    return val


def json_to_latex(recipe):
    title = recipe.get('title', 'No Title')
    description = recipe.get('description', None)
    ingredient_groups = recipe.get('ingredient_groups', [])
    instruction_groups = recipe.get('instruction_groups', [])
    notes = recipe.get('notes', None)
    reviews = recipe.get('reviews', None)
    source = recipe.get('source', None)
    scale = recipe.get('scale', None)
    source_latex = "\\fancyfoot[C]{\\footnotesize " + escape_latex(source) + "}" if source else ""

    latex = [
        "\\documentclass[10pt]{article}",
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
        "\\end{center}",
        "\\vspace{1em}"
    ]

    if description:
        latex.append("\\noindent " + escape_latex(description))

    latex.append("\\vspace{1em}")
    latex.append("\\columnratio{0.35}")  # Adjust the column ratio as needed
    latex.append("\\begin{paracol}{2}")
    latex.append("\\section*{Ingredients}")
    latex.append("\\raggedright")

    for ingredient_group in ingredient_groups:
        if ingredient_group.get('title'):
            latex.append(f"\\subsection*{{{escape_latex(ingredient_group['title'])}}}")
        latex.append("\\begin{itemize}[leftmargin=*]")
        for ingredient in ingredient_group['ingredients']:
            latex.append(f"\\item {escape_latex(ingredient)}")
        latex.append("\\end{itemize}")

    latex.append("\\switchcolumn")
    latex.append("\\section*{Instructions}")

    for instruction_group in instruction_groups:
        if instruction_group.get('title'):
            latex.append(f"\\subsection*{{{escape_latex(instruction_group['title'])}}}")
        latex.append("\\begin{enumerate}[leftmargin=*]")
        for instruction in instruction_group['instructions']:
            latex.append(f"\\item {escape_latex(instruction)}")
        latex.append("\\end{enumerate}")

    latex.append("\\end{paracol}")

    if notes:
        latex.append("\\section*{Notes}")
        latex.append(escape_latex(notes))

    if reviews:
        latex.append("\\section*{Tips}")
        for review in reviews:
            latex.append(escape_latex(review))
            latex.append("\\par")

    latex.append("\\end{document}")

    return "\n".join(latex)


def recipe_to_markdown(recipe):
    title = recipe.get('title', 'Recipe')
    description = recipe.get('description', None)
    ingredient_groups = recipe.get('ingredient_groups', [])
    instruction_groups = recipe.get('instruction_groups', [])
    notes = recipe.get('notes', None)
    reviews = recipe.get('reviews', None)
    source = recipe.get('source', None)

    md = f"# {title}\n\n"

    if description:
        md += f"{description}\n\n"

    md += "## Ingredients\n\n"
    for ingredient_group in ingredient_groups:
        if ingredient_group.get('title'):
            md += f"### {ingredient_group['title']}\n\n"
        for ingredient in ingredient_group['ingredients']:
            md += f"* {ingredient}\n"
        md += "\n"

    md += "## Instructions\n\n"
    for instruction_group in instruction_groups:
        if instruction_group.get('title'):
            md += f"### {instruction_group['title']}\n\n"
        for i, instruction in enumerate(instruction_group['instructions'], 1):
            md += f"{i}. {instruction}\n"
        md += "\n"

    if notes:
        md += "## Notes\n\n"
        md += notes

    if reviews:
        md += "## Reviews\n\n"
        md += reviews

    if source:
        md += f"Source: {source}"

    return md.strip()


def write_output(recipe, args):
    fmt = args.format
    if not fmt:
        fmt = os.path.splitext(args.output)[1][1:]
    output, mode = None, 'w'
    if fmt == 'tex':
        output = json_to_latex(recipe)
    elif fmt == 'json':
        output = json.dumps(recipe, ensure_ascii=False, indent=4)
    elif fmt == 'pdf':
        output, mode = generate_pdf(recipe, args.verbose), 'wb'
    else:
        output = recipe_to_markdown(recipe)

    if args.output:
        title = slugify(recipe.get('title', 'Recipe'))
        output_file = args.output.replace('{title}', title)
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


def display_update(data, live):
    live.update(JSON(json.dumps(data, ensure_ascii=False)))


def main():
    parser = argparse.ArgumentParser(description="Reformat and optionally rewrite a recipe from a URL.")

    parser.add_argument("url", type=str, help="URL of the recipe to process.")

    parser.add_argument("-o", "--output", type=str, help="Output file to write the processed recipe. If not provided, print to stdout.")
    parser.add_argument("-f", "--format", type=str, help="Output format (md, tex, pdf, json)")
    parser.add_argument("-n", "--normalize", action="store_true", help="Normalize the recipe to a standard format")
    parser.add_argument("-t", "--tips", action="store_true", help="Include tips from reviews in the output")
    parser.add_argument("-g", "--group", action="store_true", help="Add groups to ingredients and instructions")
    parser.add_argument("-s", "--scale", type=float, default=1.0, help="Scale the recipe by the given factor")
    parser.add_argument("-r", "--revise", type=str, help="Revisions to make to the recipe")
    parser.add_argument("-v", "--verbose", action="store_true", help="Increase output verbosity")
    # parser.add_argument("-m", "--model", type=str, default="gpt-4o", help="OpenAI model to use for rewriting the recipe.")

    args = parser.parse_args()

    console = Console()

    console.print(f"[bold]Fetching recipe from {args.url}...[/bold]", highlight=False)

    recipe, reviews = fetch_recipe_from_url(args.url)

    recipe = normalize_fractions(recipe)
    recipe = normalize_temperatures(recipe)

    llama = Llama()

    # ==================================================================================================================
    # Convert to JSON
    # ==================================================================================================================

    with Live(console=console, refresh_per_second=4) as live:
        console.print(f"[bold]Converting recipe to JSON...[/bold]", highlight=False)
        prompt = f"""Please convert the following recipe to JSON format:\n{recipe}"""
        recipe = llama.prompt_all(prompt, lambda data: display_update(data, live))

    # ==================================================================================================================
    # Update ingredients and instructions
    # ==================================================================================================================

    if args.normalize:
        with Live(console=console, refresh_per_second=4) as live:
            console.print(f"[bold]Normalizing ingredients...[/bold]", highlight=False)
            prompt = f"""Please update the recipe's ingredients.
            
* Convert all decimal amounts to fractions. Use the FRACTION SLASH ⁄, e.g., 0.5 -> 1⁄2.
* Express measurements in inches using QUOTATION MARK ", e.g., 9".
* Use the MULTIPLICATION SIGN × for rectangular measurements, e.g., 9×13".
* Temperatures should use the DEGREE SIGN ° and be in Fahrenheit only, e.g., 350 °F.
* Include packaged ingredient units in parentheses, e.g., "1 stick (1⁄2 c) unsalted butter", "1 can (15 oz) black
  beans".
* Employ standard units: 1 cup, 2 cups, 1 teaspoon, 1/2 tablespoon, 1 1⁄2 gallons, 1⁄4 ounce, 1 pound, 1 kilogram, etc...
* Exclude ingredients used solely for greasing or flouring pans.   
* Ingredient group titles must be prepositional phrases, e.g., "For the Cake", "For the Frosting". 
    
The recipe is:
{recipe}"""
            recipe_ingredients = llama.prompt_ingredients(prompt, lambda data: display_update(data, live))
            recipe['ingredient_groups'] = recipe_ingredients['ingredient_groups']

        with Live(console=console, refresh_per_second=4) as live:
            console.print(f"[bold]Normalizing instructions...[/bold]", highlight=False)
            prompt = f"""Please update the recipe's instructions.

* Split or combine steps as needed to ensure each step is a single instruction, but don't make steps too granular.
* Use the imperative mood and present tense for instructions. Instructions should generally start with a verb.
* Do not include ingredient amounts in the instructions unless the recipe calls for multiple additions of the same
  ingredient. For example, "Add the flour" NOT "Add 1 cup flour", unless the recipe calls for adding flour in multiple
  steps.
* Instructions should be a high level overview of the cooking process. Do not include detailed explanations or tips.
* Assume the reader has basic cooking knowledge and does not need detailed explanations of common cooking techniques.
  For example, "1. Pour marinade into a large, shallow dish. 2. Add chicken and turn to coat. 3. Cover and refrigerate
  overnight." should just be "1. Marinade chicken in the refrigerator overnight."
* Remove any steps that are unnecessary, e.g. "Gather the ingredients" or "Enjoy!"
* For baked goods, be clear about the pan size and baking time. For cupcakes, specify the number of cups and the baking
  time.
* Instruction group titles must be gerund phrases, e.g., "Making the Cake", "Making the Frosting".

The recipe is:
{recipe}"""
            recipe_instructions = llama.prompt_instructions(prompt, lambda data: display_update(data, live))
            recipe['instruction_groups'] = recipe_instructions['instruction_groups']

    # ==================================================================================================================
    # Group ingredients and instructions
    # ==================================================================================================================

    if args.group:
        with Live(console=console, refresh_per_second=4) as live:
            console.print(f"[bold]Grouping ingredients and instructions...[/bold]", highlight=False)
            prompt = f"""Please group the recipe's ingredients and instructions.
            
* Ingredient titles must be prepositional phrases, e.g., "For the Cake", "For the Frosting".
* Instruction titles must be gerund phrases, e.g., "Making the Cake", "Making the Frosting".
          
The recipe is:
{recipe}"""
            recipe = llama.prompt_all(prompt, lambda data: display_update(data, live))

    # ==================================================================================================================
    # Revise recipe
    # ==================================================================================================================

    if args.revise:
        with Live(console=console, refresh_per_second=4) as live:
            console.print(f"[bold]Revising the recipe...[/bold]", highlight=False)
            prompt = f"""Please revise the recipe according to the following user request:
{args.revise}
The recipe is:
{recipe}"""
            recipe = llama.prompt_all(prompt, lambda data: display_update(data, live))

    # ==================================================================================================================
    # Finalize recipe
    # ==================================================================================================================

    recipe['notes'] = []
    recipe['reviews'] = []
    recipe['source'] = args.url
    recipe['scale'] = args.scale

    recipe['ingredient_groups'] = [group for group in recipe['ingredient_groups'] if group['ingredients']]
    recipe['instruction_groups'] = [group for group in recipe['instruction_groups'] if group['instructions']]

    if len(recipe['ingredient_groups']) == 1:
        recipe['ingredient_groups'][0]['title'] = ''

    if len(recipe['instruction_groups']) == 1:
        recipe['instruction_groups'][0]['title'] = ''

    recipe['source'] = args.url
    recipe['scale'] = args.scale

    # ==================================================================================================================
    # Write output
    # ==================================================================================================================

    console.print(f"[bold]Final recipe[/bold]", highlight=False)
    console.print(recipe)

    write_output(recipe, args)


if __name__ == "__main__":
    main()
