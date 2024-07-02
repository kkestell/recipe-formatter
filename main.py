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

recipe_to_json_prompt = """
Convert the recipe to JSON format.
Unless the recipe is already grouped, please put all of the ingredients in a single ingredient group and all of the instructions in a single instruction group, both with empty titles.
If the recipe is already grouped, please preserve the existing groupings.

Here is an example of the JSON format:
```json
{
  "title": "Recipe Title",
  "description": "Optional introductory text.",
  "ingredient_groups": [
    {
      "title": "...",
      "ingredients": [
        "Ingredient 1",
        "Ingredient 2",
        "Ingredient 3"
      ]
    }
  ],
  "instruction_groups": [
    {
      "title": "...",
      "instructions": [
        "Step 1",
        "Step 2",
        "Step 3"
      ]
    }
  ],
  "notes": "Optional notes."
}
"""


group_ingredients_and_instructions_prompt = """
Please split the ingredients and instructions into groups. If the recipe already has groups, you can leave them as is.
Ingredient titles should take the form "For the Cake", "For the Frosting", etc.
Instruction titles should take the form "Making the Cake", "Making the Frosting", "Grilling the Chicken", etc.
Return the recipe JSON with the updated groups.
"""


update_ingredients_prompt = """
Update the ingredients in the recipe to strictly conform to the following style guide, and return the updated JSON.

### Detailed Ingredient List Style Guide

1. **Naming**: Use clear, standard names for all ingredients, specifying types or varieties when relevant.
   - **Examples**:
     - "granulated sugar" not just "sugar"
     - "kosher salt" not just "salt"
     - "Granny Smith apple"
     - "extra virgin olive oil"
     - "whole wheat flour"

2. **Order**: Ingredients should be listed in the order they are used in the recipe.
   - **Examples**:
     - Begin with "2 eggs," followed by "1 c sugar" if used sequentially.
     - "1 tsp vanilla extract" after "2 c flour" if mixing follows.
     - List base ingredients before toppings in recipes like pizza.
     - Spices listed after main ingredients in a curry.
     - Salad dressings ingredients listed after salad components.

3. **Measurements**: Use the measurement system most familiar to your intended audience, with one alternative for precision or clarity.
   - **Examples**:
     - "1 c (240 ml) milk"
     - "3⁄4 c (100 g) flour"
     - "2 tbsp (30 ml) olive oil"
     - "4 tsp (20 ml) maple syrup"
     - "5 lb (2.3 kg) potatoes"

4. **Formatting**: Use numerals for quantities, with standard abbreviations for units.
   - **Examples**:
     - "1 tbsp olive oil"
     - "3 tsp yeast"
     - "2 lb chicken"
     - "5 oz (140 g) cheddar cheese"
     - "100 g (3.5 oz) dark chocolate"

5. **Case Usage**: Keep ingredient names in lowercase, except for proper nouns.
   - **Examples**:
     - "cheddar cheese"
     - "Greek yogurt"
     - "Japanese soy sauce"
     - "Himalayan pink salt"
     - "San Marzano tomatoes"

6. **Descriptors and Preparation Details**: Attach relevant preparation details directly with the ingredient.
   - **Examples**:
     - "1 onion, finely chopped"
     - "2 cloves garlic, minced"
     - "3 carrots, peeled and diced"
     - "200 g spinach, washed and drained"
     - "1 apple, cored and sliced"

7. **Packaged Ingredients**: Clearly indicate the package size or weight.
   - **Examples**:
     - "1 stick (1⁄2 c) unsalted butter"
     - "1 can (15 oz) black beans"
     - "1 package (10 oz) frozen peas"
     - "1 jar (500 ml) marinara sauce"
     - "1 box (1 lb) pasta"
     - "1 bottle (750 ml) red wine"

8. **Variable Ingredients**: Specify the precise measurement first, followed by the approximate quantity in physical units, particularly for variable-size ingredients.
    - **Examples**:
      - "2 c (1 large) chopped yellow onion"
      - "3 tbsp (1 lemon) lemon juice"
      - "1 c (about 8 oz) chopped tomatoes"
      - "4 c (about 1 lb) sliced mushrooms"
      - "1 pt (about 10-12) strawberries, hulled and halved"

9. **Cookware and Temperatures**: Specify cookware sizes using quotation marks for inches and the multiplication sign for rectangular measurements; provide temperatures in both Fahrenheit and Celsius using the degree sign.
    - **Examples**:
      - "Preheat oven to 350 °F (175 °C)"
      - "Use a 9\" round cake pan"
      - "Prepare a 9×13\" baking dish"

Please return your output in this format:

```json
{
"ingredient_groups": [
    {
        "title": "...",
        "ingredients": [...]
    },
]
```
"""


update_instructions_prompt = """
Update the instructions in the recipe to strictly conform to the following style guide, and return the updated recipe JSON. Do not update any other parts of the recipe, such as the title, description, ingredients, or notes.

Style Guide:
* Split or combine steps as needed to ensure each step is a single instruction, but don't make steps too granular.
* Use the imperative mood and present tense for instructions. Instructions should generally start with a verb.
* Do not include ingredient amounts in the instructions unless the recipe calls for multiple additions of the same ingredient. For example, "Add the flour" NOT "Add 1 c flour", unless the recipe calls for adding flour in multiple steps.
* Instructions should be a high level overview of the cooking process. Do not include detailed explanations or tips.
* Assume the reader has basic cooking knowledge and does not need detailed explanations of common cooking techniques. For example, "1. Pour marinade into a large, shallow dish. 2. Add chicken and turn to coat. 3. Cover and refrigerate overnight." should just be "1. Marinade chicken in the refrigerator overnight." And skip stuff like "until a toothpick inserted in the center comes out clean" and other common sense stuff.
* Be extremely terse. Each instruction should be as concise as possible while still being clear.
* Remove any steps that are unnecessary, e.g. "Gather the ingredients" or "Enjoy!"
* For baked goods, be clear about the pan size and baking time. For cupcakes, specify the number of cups and the baking time.

Examples:
* Preheat oven to 350 °F.
* Mix flour, sugar, and salt in a bowl.
* Add eggs and milk to the dry ingredients.
* Stir until just combined.
* Pour batter into a greased pan.
* Bake for 30 minutes or until golden brown.

Please return your output in this format:

```json
{
    "instruction_groups": [
        {
            "title": "...",
            "instructions": [...]
        },
    ]
}
```
"""


update_title_and_notes_prompt = """
Please update the recipe's title, description, and notes to strictly conform to the following style guide, and return the updated recipe JSON. Do not update any other parts of the recipe, such as the ingredients or instructions.

Style Guide:
* Title should be concise and descriptive. Remove any self-aggrandizing words or phrases e.g. "Delicious", "Best Ever" but descriptive words e.g. "Chewy" are OK.
* Title should be in title case, with the first letter of each word capitalized.
* Title should not include the word "recipe" or "how to make".
* Descriptions are optional. No description is better than a pointless or redundant description.
* Descriptions are for describing the finished dish. Serving suggestions, history of the dish, etc. can go in the notes.
* Notes are optional. No notes are better than a pointless or redundant note.
* Remove any mentions of how delicious, healthy, easy, etc. the recipe is.
* Descriptions and notes should be in sentence case.
* Remove any editors notes, publication information, or other irrelevant information.
* Remove any personal anecdotes or stories.
* Adopt the dry, factual tone of a cooking textbook author. Avoid adjectives like "dreamy", "delicious", "tasty", "awesome", etc.
* Ensure proper spelling, punctuation, and grammar.
* Remove any fluff-phrases and filler words that are designed to try to enhance the appeal of the recipe without adding substantial information or value e.g. "perfect for any occasion", "great for a weeknight dinner", "your family will love this", etc.

Please do not add any new information to the title, description, or notes. Only update the existing text to conform to the style guide.
"""


final_prompt = """
Please review the recipe and make any final adjustments as needed. If the recipe is correct, please return the JSON as-is. We've already heavily edited the recipe to conform to the style guide, so only make changes if you see something that needs fixing -- it's probably already pretty close!

As a reminder, here's the style guide:

**General Formatting Rules:**
* Use the FRACTION SLASH ⁄ for fractions, e.g., 1⁄2.
* Express measurements in inches using QUOTATION MARK ", e.g., 9".
* Use the MULTIPLICATION SIGN × for rectangular measurements, e.g., 9×13".
* Temperatures should use the DEGREE SIGN ° and be given in both Fahrenheit and Celsius, e.g., 350 °F (175 °C).
* Include packaged ingredient units in parentheses, e.g., "1 stick (1⁄2 c) unsalted butter", "1 can (15 oz) black beans".
* Employ standard abbreviations without periods: ea, c, g, tbsp, tsp, L, ml, oz, lb, kg, pt, qt, gal, fl oz, in, cm, mm, m, ft, °F, °C.
* When listing both weight and volume for an ingredient, place the weight first, e.g., "1 c (120 g) flour".
* Exclude ingredients used solely for greasing or flouring pans.

**Instructions Formatting:**
* Utilize the imperative mood and present tense.
* Begin each instruction with a verb.
* Refrain from including ingredient amounts in instructions unless necessary for clarity.
* Be succinct; provide an overarching view of the cooking process.
* Assume foundational cooking knowledge; omit detailed explanations of common techniques.
* Remove nonessential steps such as "Gather ingredients" or "Enjoy!"
* Relocate any steps that describe finishing, serving, or storage to the notes section. E.g., "Serve hot with a side of rice." or "Store leftovers in an airtight container in the refrigerator."

**Title, Description, and Notes:**
* Ensure the title is concise, descriptive, and in title case without phrases like "recipe" or "how to make".
* Descriptions should focus on the dish's end result and avoid redundancy.
* Notes may include serving suggestions or historical context but should exclude personal anecdotes and maintain an objective tone.
* Use sentence case for descriptions and notes.
* Verify correct spelling, punctuation, and grammar throughout.
* Eliminate fluff-phrases and filler words that do not contribute substantial information or value, e.g., "perfect for any occasion", "great for a weeknight dinner", "your family will love this", etc.
"""


reviews_prompt = f"""
If there are any common changes, modifications, additions, etc. in the provided reviews, please summarize them. 

Style Guide:
* Format your output as paragraphs of grammatically correct English text.
* Try to limit yourself to 1 or 2 paragraphs of text.
* When mentioning additions and tweaks, please be specific and include amounts and ingredients, times, temperatures, etc.
* Please be extremely concise and to the point.
* Adopt a dry, factual tone and avoid any personal opinions or anecdotes.
* Avoid fluffy language and focus on the most common themes in the reviews.
* If the reviews don't contain any common themes, you may return an empty array.
* Use the FRACTION SLASH ⁄ for fractions, e.g., 1⁄2.
* Express measurements in inches using QUOTATION MARK ", e.g., 9".
* Use the MULTIPLICATION SIGN × for rectangular measurements, e.g., 9×13".
* Temperatures should use the DEGREE SIGN ° and be given in both Fahrenheit and Celsius, e.g., 350 °F (175 °C).
* Include packaged ingredient units in parentheses, e.g., "1 stick (1⁄2 c) unsalted butter", "1 can (15 oz) black beans".
* Employ standard abbreviations without periods: ea, c, g, tbsp, tsp, L, ml, oz, lb, kg, pt, qt, gal, fl oz, in, cm, mm, m, ft, °F, °C.
* When listing both weight and volume for an ingredient, place the weight first, e.g., "1 c (120 g) flour".

Please return the output in the following JSON format:

{{
    "paragraphs": [
        "...",
        "..."
    ]
}}            
"""


revisions_prompt = """
Please make the following user modifications to the recipe and return the updated recipe JSON. 
Remember that these are direct user requests and should be followed exactly. The user has requested the following changes:
"""


scale_prompt = f"""
Scale the recipe and return the updated JSON.
Do not make any other modifications to the recipe.
The scale factor is: 
"""


def run_pipeline_step(args, prompt, recipe):
    if isinstance(recipe, dict):
        recipe = json.dumps(recipe)
    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": prompt}, {"role": "user", "content": recipe}],
                response_format=ResponseFormat(type="json_object"),
                model=args.model,
                temperature=0.0,
                timeout=30
            )
            recipe = chat_completion.choices[0].message.content
            break
        except Exception as e:
            print(f"Request failed: {e}")
            print("Retrying in 10 seconds...")
            time.sleep(10)
            if attempts == 3:
                print(f"Failed after 3 attempts: {e}")
                raise e
            continue
    return json.loads(recipe)


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


# def json_to_latex(recipe):
#     title = recipe.get('title', 'No Title')
#     description = recipe.get('description', None)
#     ingredient_groups = recipe.get('ingredient_groups', [])
#     instruction_groups = recipe.get('instruction_groups', [])
#     notes = recipe.get('notes', None)
#     reviews = recipe.get('reviews', None)
#     source = recipe.get('source', None)
#     scale = recipe.get('scale', None)
#     source_latex = "\\fancyfoot[C]{\\footnotesize " + escape_latex(source) + "}" if source else ""
#
#     latex = [
#         "\\documentclass[10pt]{article}",
#         "\\usepackage{fontspec}",
#         "\\usepackage{geometry}",
#         "\\usepackage{enumitem}",
#         "\\usepackage{graphicx}",
#         "\\usepackage{paracol}",
#         "\\usepackage{microtype}",
#         "\\usepackage{parskip}",
#         "\\usepackage{fancyhdr}",
#         "\\geometry{letterpaper, margin=0.75in}",
#         "\\setmainfont{Source Serif 4}",
#         "\\newfontfamily\\headingfont{Source Serif 4}",
#         "\\pagestyle{fancy}",
#         "\\fancyhf{}",
#         "\\renewcommand{\\headrulewidth}{0pt}",
#         source_latex,
#         "\\begin{document}",
#         "\\setlist[enumerate,1]{itemsep=0em}",
#         "\\begin{center}",
#         "{\\huge \\bfseries \\headingfont " + escape_latex(title) + "}",
#         "\\end{center}"
#     ]
#
#     if description:
#         latex.append("\\vspace{1em}")
#         latex.append(description)
#
#     latex.append("\\vspace{1em}")
#     latex.append("\\columnratio{0.35}")
#     latex.append("\\begin{paracol}{2}")
#     latex.append("\\setlength{\\columnsep}{2em}")
#     latex.append("\\sloppy")
#     latex.append("\\section*{Ingredients}")
#     latex.append("\\raggedright")
#
#     for ingredient_group in ingredient_groups:
#         if ingredient_group.get('title'):
#             latex.append(f"\\subsection*{{{ingredient_group['title']}}}")
#         latex.append("\\begin{itemize}[leftmargin=*]")
#         for ingredient in ingredient_group['ingredients']:
#             latex.append(f"\\item {fix_fractions(escape_latex(ingredient))}")
#         latex.append("\\end{itemize}")
#
#     latex.append("\\switchcolumn")
#     latex.append("\\section*{Instructions}")
#
#     for instruction_group in instruction_groups:
#         if instruction_group.get('title'):
#             latex.append(f"\\subsection*{{{instruction_group['title']}}}")
#         latex.append("\\begin{enumerate}[leftmargin=*]")
#         for i, instruction in enumerate(instruction_group['instructions'], 1):
#             latex.append(f"\\item {escape_latex(instruction)}")
#         latex.append("\\end{enumerate}")
#
#     latex.append("\\end{paracol}")
#
#     if notes:
#         latex.append("\\section*{Notes}")
#         latex.append(escape_latex(notes))
#
#     if reviews:
#         latex.append("\\section*{Tips}")
#         for review in reviews:
#             latex.append(escape_latex(review))
#             latex.append("\n")
#
#     # if scale:
#     #     latex.append(f"\\vspace{{1em}}")
#     #     latex.append(f"\\noindent Scale: {scale}")
#
#     latex.append("\\end{document}")
#
#     return "\n".join(latex)

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

    if args.verbose:
        print(f"Fetching recipe from {args.url}...")

    recipe, reviews = fetch_recipe_from_url(args.url)

    if args.verbose:
        print("Converting recipe to JSON format...")

    recipe = run_pipeline_step(args, recipe_to_json_prompt, recipe)

    if args.verbose:
        print(json.dumps(recipe, indent=4))

    if args.normalize:
        if args.verbose:
            print("Normalizing ingredients and instructions...")

        updated_ingredient_groups = run_pipeline_step(args, update_ingredients_prompt, recipe)
        recipe['ingredient_groups'] = updated_ingredient_groups['ingredient_groups']

        updated_instruction_groups = run_pipeline_step(args, update_instructions_prompt, recipe)
        recipe['instruction_groups'] = updated_instruction_groups['instruction_groups']

    if args.group:
        if args.verbose:
            print("Grouping ingredients and instructions...")

        recipe = run_pipeline_step(args, group_ingredients_and_instructions_prompt, recipe)

    if args.normalize:
        if args.verbose:
            print("Normalizing title, description, and notes...")

        recipe = run_pipeline_step(args, update_title_and_notes_prompt, recipe)

    if args.scale != 1.0:
        if args.verbose:
            print(f"Scaling the recipe by {args.scale}...")

        recipe = run_pipeline_step(args, scale_prompt, recipe)

    if args.tips and reviews:
        if args.verbose:
            print("Summarizing common themes from reviews...")

        reviews_text = "\n".join(reviews)
        recipe_reviews = run_pipeline_step(args, f"{reviews_prompt}\n\n{reviews_text}", recipe)
        recipe['reviews'] = recipe_reviews.get('paragraphs', [])

    if args.revise:
        if args.verbose:
            print("Making user revisions to the recipe...")

        recipe = run_pipeline_step(args, f"{revisions_prompt}\n\n{args.revise}", recipe)

    if args.normalize:
        if args.verbose:
            print("Finalizing the recipe...")

        recipe = run_pipeline_step(args, final_prompt, recipe)

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
