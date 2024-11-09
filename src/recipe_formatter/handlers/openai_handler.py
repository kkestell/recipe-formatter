from typing import Type, Callable

import instructor
from openai import OpenAI
from pydantic import BaseModel, ValidationError


class OpenAIModelHandler:
    def __init__(self, api_key: str, model: str):
        self.client = instructor.from_openai(OpenAI(api_key=api_key))
        self.model = model

    def query(self, prompt: str, response_model: Type[BaseModel], callback: Callable, **kwargs):
        response_stream = self.client.chat.completions.create(
            model=self.model,
            response_model=instructor.Partial[response_model],
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            stream=True,
            **kwargs
        )
        final_obj = None
        for response in response_stream:
            try:
                callback(response)
                final_obj = response
            except ValidationError as e:
                print(f"Validation error: {e}")
        return final_obj
