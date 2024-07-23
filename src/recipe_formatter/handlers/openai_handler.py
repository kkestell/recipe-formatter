from typing import Type, Callable, Optional

import instructor
from openai import OpenAI
from pydantic import BaseModel, ValidationError
from recipy.models import Recipe

from . import LanguageModelInterface, RecipeIngredients, RecipeInstructions


class OpenAIModelHandler(LanguageModelInterface):
    def __init__(self, api_key: str, model: str):
        self.client = instructor.from_openai(OpenAI(api_key=api_key))
        self.model = model

    def _generate_stream(self, prompt: str, response_model: Type[BaseModel], callback: Callable, **kwargs):
        response_stream = self.client.chat.completions.create(
            model=self.model,
            response_model=instructor.Partial[response_model],
            messages=[{"role": "user", "content": prompt}],
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
        return self._generate_stream(prompt, Recipe, callback)

    def get_ingredients(self, prompt: str, callback: Callable) -> Optional[RecipeIngredients]:
        return self._generate_stream(prompt, RecipeIngredients, callback)

    def get_instructions(self, prompt: str, callback: Callable) -> Optional[RecipeInstructions]:
        return self._generate_stream(prompt, RecipeInstructions, callback)
