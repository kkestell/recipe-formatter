from abc import ABC, abstractmethod
from typing import Type, Callable, Optional, List

from pydantic import BaseModel
from recipy.models import Recipe, IngredientGroup, InstructionGroup


class RecipeIngredients(BaseModel):
    ingredient_groups: List[IngredientGroup]


class RecipeInstructions(BaseModel):
    instruction_groups: List[InstructionGroup]


class LanguageModelInterface(ABC):
    @abstractmethod
    def _generate_stream(self, prompt: str, response_model: Type[BaseModel], callback: Callable, **kwargs):
        pass

    @abstractmethod
    def get_recipe(self, prompt: str, callback: Callable) -> Optional[Recipe]:
        pass

    @abstractmethod
    def get_ingredients(self, prompt: str, callback: Callable) -> Optional[RecipeIngredients]:
        pass

    @abstractmethod
    def get_instructions(self, prompt: str, callback: Callable) -> Optional[RecipeInstructions]:
        pass
