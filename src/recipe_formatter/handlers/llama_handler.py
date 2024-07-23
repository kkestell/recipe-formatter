from typing import Type, Callable, Optional

import instructor
from instructor import patch, Mode
from llama_cpp import Llama
from llama_cpp.llama_speculative import LlamaPromptLookupDecoding
from pydantic import BaseModel, ValidationError
from recipy.models import Recipe

from . import LanguageModelInterface, RecipeIngredients, RecipeInstructions


def group_schema(item_type: str):
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


recipe_schema = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
        "ingredient_groups": {
            "type": "array",
            "items": group_schema("ingredients")
        },
        "instruction_groups": {
            "type": "array",
            "items": group_schema("instructions")
        }
    },
    "required": ["title", "ingredient_groups", "instruction_groups"]
}


ingredients_schema = {
        "type": "object",
        "properties": {
            "ingredient_groups": {
                "type": "array",
                "items": group_schema("ingredients")
            }
        },
        "required": ["ingredient_groups"]
    }


instructions_schema = {
        "type": "object",
        "properties": {
            "instruction_groups": {
                "type": "array",
                "items": group_schema("instructions")
            }
        },
        "required": ["instruction_groups"]
    }


class LlamaModelHandler(LanguageModelInterface):
    def __init__(self, model_path: str):
        self.llama = Llama(
            model_path=model_path,
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

    def _generate_stream(self, prompt: str, response_model: Type[BaseModel], callback: Callable, **kwargs):
        response_schema = kwargs.get('response_schema')
        response_stream = self.create(
            response_model=instructor.Partial[response_model],
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object", "schema": response_schema},
            max_tokens=8192,
            stream=True
        )
        final_obj = None
        for response in response_stream:
            try:
                callback(response)
                final_obj = response
            except ValidationError as e:
                print(f"Validation error: {e}")
        return final_obj

    def get_recipe(self, prompt: str, callback: Callable) -> Optional[Recipe]:
        return self._generate_stream(prompt, Recipe, callback, response_schema=recipe_schema)

    def get_ingredients(self, prompt: str, callback: Callable) -> Optional[RecipeIngredients]:
        return self._generate_stream(prompt, RecipeIngredients, callback, response_schema=ingredients_schema)

    def get_instructions(self, prompt: str, callback: Callable) -> Optional[RecipeInstructions]:
        return self._generate_stream(prompt, RecipeInstructions, callback, response_schema=instructions_schema)
