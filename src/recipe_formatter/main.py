import argparse
import json
import os
import sys
from typing import List

from recipy.latex import recipe_to_latex
from recipy.markdown import recipe_to_markdown
from recipy.microdata import recipe_from_url
from recipy.models import InstructionGroup, IngredientGroup, Recipe
from recipy.pdf import recipe_to_pdf
from rich.console import Console
from rich.json import JSON
from rich.live import Live
from slugify import slugify
from pydantic import BaseModel

from handlers.openai_handler import OpenAIModelHandler


class RecipeIngredients(BaseModel):
    ingredient_groups: List[IngredientGroup]


class RecipeInstructions(BaseModel):
    instruction_groups: List[InstructionGroup]


class IngredientList(BaseModel):
    ingredients: List[str]


class InstructionList(BaseModel):
    instructions: List[str]


class GroupedRecipe(BaseModel):
    title: str
    ingredient_groups: List[IngredientGroup]
    instruction_groups: List[InstructionGroup]


class SimpleRecipe(BaseModel):
    title: str
    ingredients: List[str]
    instructions: List[str]


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

    console = Console()

    if config["engine"] == "openai":
        api_key = config.get("openai_api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OpenAI API key not found in config or environment variables")
        llm = OpenAIModelHandler(api_key, model=config.get("openai_model", "gpt-4o-mini"))
    else:
        raise ValueError(f"Unsupported engine: {config['engine']}")

    live = Live(console=console, refresh_per_second=4) if args.verbose else None

    def update_live(data):
        if live:
            live.update(JSON(json.dumps(data.model_dump(), indent=2)))

    if live:
        live.start()

    try:
        recipe = recipe_from_url(args.url)

        if isinstance(recipe, Recipe):
            recipe = SimpleRecipe(title=recipe.title, ingredients=[i for ig in recipe.ingredient_groups for i in ig.ingredients], instructions=[i for ig in recipe.instruction_groups for i in ig.instructions])
        elif isinstance(recipe, str):
            recipe = llm.query(
                f"""Please convert the recipe to JSON. 
                * Try to provide as literal a conversion as possible. Do not change units, amounts, ingredients, instructions, etc.
                The recipe is:
                {recipe}""",
                SimpleRecipe,
                lambda data: update_live(data) if live else lambda _: None
            )
            if not recipe:
                raise ValueError("Failed to convert recipe to JSON")
        else:
            raise ValueError(f"Invalid recipe type: {type(recipe)}")

        if args.normalize:
            def normalize_ingredients_update(data):
                recipe.ingredients = data.ingredients
                update_live(recipe)

            llm.query(
                f"""Please update the recipe's ingredients and return JSON.
                * Convert all decimal amounts to fractions.
                * Include packaged ingredient units in parentheses, e.g., "1 stick (1⁄2 cup) unsalted butter", "1 can (15 ounce) black beans".
                * Expand all unit abbreviations
                * Exclude ingredients used solely for greasing or flouring pans.
                The recipe's ingredients are:
                {recipe.ingredients}""",
                IngredientList,
                normalize_ingredients_update if live else lambda data: None
            )

            def normalize_instructions_update(data):
                recipe.instructions = data.instructions
                update_live(recipe)

            llm.query(
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
                The recipe's instructions are:
                {recipe.instructions}""",
                InstructionList,
                normalize_instructions_update if live else lambda data: None
            )

        if args.revisions:
            def revise_update(data):
                recipe.ingredients = data.ingredients
                recipe.instructions = data.instructions
                update_live(recipe)

            recipe = llm.query(
                f"""Please revise the recipe and return JSON.
                The revisions are:
                {args.revisions}
                The recipe is:
                {recipe}""",
                Recipe,
                revise_update if live else lambda data: None
            )

        if args.group:
            recipe = GroupedRecipe(
                title=recipe.title,
                ingredient_groups=[IngredientGroup(name=None, ingredients=recipe.ingredients)],
                instruction_groups=[InstructionGroup(name=None, instructions=recipe.instructions)])

            def group_update(data):
                if data.ingredient_groups:
                    recipe.ingredient_groups = data.ingredient_groups

                if data.instruction_groups:
                    recipe.instruction_groups = data.instruction_groups

                update_live(recipe)

            recipe = llm.query(
                f"""Please group the recipe's ingredients and instructions and return JSON. The user has requested
                that both the ingredients and instructions be grouped, so you MUST return at least 2 ingredient groups and 2 instruction groups.
                * Ingredient group names must be prepositional phrases, e.g., "For the Cake", "For the Frosting". 
                * Instruction group names must be gerund phrases, e.g., "Making the Cake", "Making the Frosting".
                The recipe is:
                {recipe}""",
                GroupedRecipe,
                group_update if live else lambda data: None
            )

    finally:
        if live:
            live.stop()

    if isinstance(recipe, SimpleRecipe):
        recipe = Recipe(
            title=recipe.title,
            description=None,
            ingredient_groups=[IngredientGroup(name=None, ingredients=recipe.ingredients)],
            instruction_groups=[InstructionGroup(name=None, instructions=recipe.instructions)]
        )
    elif isinstance(recipe, GroupedRecipe):
        recipe = Recipe(
            title=recipe.title,
            description=None,
            ingredient_groups=recipe.ingredient_groups,
            instruction_groups=recipe.instruction_groups
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
