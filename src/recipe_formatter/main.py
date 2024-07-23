import argparse
import json
import os
import sys

from recipy.latex import recipe_to_latex
from recipy.markdown import recipe_to_markdown
from recipy.microdata import recipe_from_url
from recipy.pdf import recipe_to_pdf
from rich.console import Console
from rich.json import JSON
from rich.live import Live
from slugify import slugify

from handlers.openai_handler import OpenAIModelHandler
from handlers.llama_handler import LlamaModelHandler


def load_config(config_path):
    config_path = os.path.expanduser(config_path)
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Reformat and optionally rewrite a recipe from a URL.")

    parser.add_argument("url", type=str, help="URL of the recipe to process.")
    parser.add_argument("-o", "--output", type=str, help="Output file to write the processed recipe. If not provided, print to stdout.")
    parser.add_argument("-f", "--format", type=str, help="Output format (md, tex, pdf, json)")
    parser.add_argument("-n", "--normalize", action="store_true", help="Normalize the recipe to a standard format")
    parser.add_argument("-g", "--group", action="store_true", help="Group the recipe's ingredients and instructions")
    parser.add_argument("-r", "--revisions", type=str, help="Apply revisions to the recipe")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output with live updates")
    parser.add_argument("-c", "--config", type=str, default="~/.config/recipe-formatter/config.json", help="Path to the configuration file (default: config.json)")

    args = parser.parse_args()

    config = load_config(args.config)

    recipe = recipe_from_url(args.url)

    console = Console()

    if config["engine"] == "openai":
        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found in config or environment variables")
        llm = OpenAIModelHandler(api_key, model=config.get("openai_model", "gpt-4o-mini"))
    elif config["engine"] == "llama":
        llm = LlamaModelHandler(config["llama_model_path"])
    else:
        raise ValueError(f"Unsupported engine: {config['engine']}")

    def process_with_live(message, prompt, method):
        if args.verbose:
            with Live(console=console, refresh_per_second=4) as live:
                live.console.print(message, highlight=False)
                return method(prompt, lambda data: live.update(JSON(json.dumps(data.model_dump(), indent=2))))
        else:
            return method(prompt, lambda data: None)

    # if isinstance(recipe, str):
    recipe = process_with_live(
        "Converting recipe to JSON...",
        f"""Please convert the recipe to JSON. 
        * Try to provide as literal a conversion as possible. Do not change units, amounts, ingredients, instructions, etc.
        * Place all ingredients in a single group with a null name.
        * Place all instructions in a single group with a null name.
        The recipe is:
        {recipe}""",
        llm.get_recipe
    )

    if not recipe:
        console.print("Failed to process recipe")
        return

    recipe.reviews = []

    if args.normalize:
        response = process_with_live(
            "Normalizing ingredients...",
            f"""Please update the recipe's ingredients and return JSON.
            * Convert all decimal amounts to fractions. Use the FRACTION SLASH ⁄, e.g., 0.5 -> 1⁄2.
            * Express measurements in inches using QUOTATION MARK ", e.g., 9".
            * Use the MULTIPLICATION SIGN × for rectangular measurements, e.g., 9×13".
            * Temperatures should use the DEGREE SIGN ° and be in Fahrenheit only, e.g., 350 °F.
            * Include packaged ingredient units in parentheses, e.g., "1 stick (1⁄2 c) unsalted butter", "1 can (15 oz) black
            beans".
            * Employ standard units: 1 cup, 2 cups, 1 teaspoon, 1/2 tablespoon, 1 1⁄2 gallons, 1⁄4 ounce, 1 pound, 1 kilogram, etc...
            * Exclude ingredients used solely for greasing or flouring pans.   
            The recipe is:
            {recipe}""",
            llm.get_ingredients
        )
        recipe.ingredient_groups = response.ingredient_groups

        response = process_with_live(
            "Normalizing instructions...",
            f"""Please update the recipe's instructions and return JSON.
            * Split or combine steps as needed to ensure each step is a single instruction, but don't make steps too granular.
            * Use the imperative mood and present tense for instructions. Instructions should generally start with a verb.
            * Do not include ingredient amounts in the instructions unless the recipe calls for multiple additions of the same
              ingredient. For example, "Add the flour" NOT "Add 1 cup flour", unless the recipe calls for adding flour in multiple
              steps.
            * Instructions should be a high level overview of the cooking process. Do not include detailed explanations or tips.
            * Assume the reader has basic cooking knowledge and does not need detailed explanations of common cooking techniques.
            * Remove any steps that are unnecessary, e.g. "Gather the ingredients" or "Enjoy!"
            * For baked goods, be clear about the pan size and baking time.
            * Do not put the ingredients into multiple groups.
            * Do not put the instructions into multiple groups.
            The recipe is:
            {recipe}""",
            llm.get_instructions
        )
        recipe.instruction_groups = response.instruction_groups

    if args.group:
        recipe = process_with_live(
            "Grouping ingredients and instructions...",
            f"""Please group the recipe's ingredients and instructions and return JSON.
            * Ingredient titles should take the form "For the Cake", "For the Frosting", etc.
            * Instruction titles should take the form "Making the Cake", "Making the Frosting", "Grilling the Chicken", etc.
            * Ingredient group titles must be prepositional phrases, e.g., "For the Cake", "For the Frosting". 
            * Instruction group titles must be gerund phrases, e.g., "Making the Cake", "Making the Frosting".
            The recipe is:
            {recipe}""",
            llm.get_recipe
        )

    if args.revisions:
        recipe = process_with_live(
            "Revising recipe...",
            f"""Please revise the recipe and return JSON.
            The revisions are:
            {args.revisions}
            The recipe is:
            {recipe}""",
            llm.get_recipe
        )

    output_format = args.format
    output_path = args.output

    if output_path is not None and "{title}" in output_path:
        output_path = output_path.replace("{title}", slugify(recipe.title))

    if output_path is None and output_format is None:
        output_format = 'json'
    elif output_format is None:
        output_format = output_path.split('.')[-1]
        if output_format not in ['md', 'tex', 'pdf', 'json']:
            console.print(f"Unsupported output format: {output_format}")
            return

    output_data = None
    if output_format == 'json':
        output_data = recipe.model_dump_json(indent=2) + "\n"
    elif output_format == 'md':
        output_data = recipe_to_markdown(recipe)
    elif output_format == 'tex':
        output_data = recipe_to_latex(recipe)
    elif output_format == 'pdf':
        output_data = recipe_to_pdf(recipe)

    if output_path is not None:
        output_mode = "wb" if isinstance(output_data, bytes) else "w"
        with open(output_path, output_mode) as f:
            f.write(output_data)
    else:
        sys.stdout.write(output_data)


if __name__ == "__main__":
    main()
