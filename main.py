import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from openai.types.chat.completion_create_params import ResponseFormat
from slugify import slugify


def run_pipeline_step(args, prompt, content):
    if isinstance(content, dict):
        content = json.dumps(content)
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": content}],
                response_format=ResponseFormat(type="json_object"),
                model=args.model,
                temperature=0.0,
                timeout=30
            )
            response = chat_completion.choices[0].message.content
            break
        except Exception as e:
            print(f"Request failed: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
            if attempts == 3:
                print(f"Failed after 3 attempts: {e}")
                raise e
            continue
    return json.loads(response)


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


def fix_fractions(text):
    return re.sub(r'(\d)/(\d)', r'\1⁄\2', text)


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

    return md


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


def load_prompts():
    config_dir = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.join(os.environ['HOME'], '.config')), 'recipe-formatter')
    prompts = {}
    for filename in os.listdir(os.path.join(config_dir, 'prompts')):
        if filename.endswith(".txt"):
            with open(os.path.join(config_dir, 'prompts', filename), 'r') as f:
                prompts[filename[:-4]] = f.read()
    return prompts


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

    parser.add_argument("-m", "--model", type=str, default="gpt-4o", help="OpenAI model to use for rewriting the recipe.")

    args = parser.parse_args()

    prompts = load_prompts()

    if args.verbose:
        print(f"Fetching recipe from {args.url}...")

    recipe, reviews = fetch_recipe_from_url(args.url)

    if args.verbose:
        print("Converting recipe to JSON format...")

    recipe = run_pipeline_step(args, prompts['json'], recipe)

    if args.verbose:
        print(json.dumps(recipe, indent=4))

    if args.normalize:
        if args.verbose:
            print("Normalizing ingredients and instructions...")

        updated_ingredient_groups = run_pipeline_step(args, prompts['ingredients'], recipe)
        recipe['ingredient_groups'] = updated_ingredient_groups['ingredient_groups']

        updated_instruction_groups = run_pipeline_step(args, prompts['instructions'], recipe)
        recipe['instruction_groups'] = updated_instruction_groups['instruction_groups']

    if args.group:
        if args.verbose:
            print("Grouping ingredients and instructions...")

        recipe = run_pipeline_step(args, prompts['group'], recipe)

    if args.normalize:
        if args.verbose:
            print("Normalizing title, description, and notes...")

        recipe = run_pipeline_step(args, prompts['title_description_notes'], recipe)

    if args.scale != 1.0:
        if args.verbose:
            print(f"Scaling the recipe by {args.scale}...")

        recipe = run_pipeline_step(args, prompts['scale'], recipe)

    if args.tips and reviews:
        if args.verbose:
            print("Summarizing common themes from reviews...")

        reviews_text = "\n".join(reviews)
        recipe_reviews = run_pipeline_step(args, f"{prompts['tips']}", reviews_text)
        recipe['reviews'] = recipe_reviews.get('paragraphs', [])

    if args.revise:
        if args.verbose:
            print("Making user revisions to the recipe...")

        recipe = run_pipeline_step(args, f"{prompts['revise']}\n\n{args.revise}", recipe)

    if args.normalize:
        if args.verbose:
            print("Finalizing the recipe...")

        recipe = run_pipeline_step(args, prompts['finalize'], recipe)

    if len(recipe['ingredient_groups']) == 1:
        recipe['ingredient_groups'][0]['title'] = ''

    if len(recipe['instruction_groups']) == 1:
        recipe['instruction_groups'][0]['title'] = ''

    recipe['source'] = args.url
    recipe['scale'] = args.scale

    write_output(recipe, args)

    # also write a markdown version of the recipe
    # args.format = 'md'
    # args.output = "recipe.md"
    # write_output(recipe, args)


if __name__ == "__main__":
    main()
