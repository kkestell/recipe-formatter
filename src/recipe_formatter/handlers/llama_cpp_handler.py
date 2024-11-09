from typing import Type, Callable
from llama_cpp import Llama
from llama_cpp.llama_speculative import LlamaPromptLookupDecoding
import instructor
from pydantic import BaseModel
from pydantic_core import ValidationError


class LlamaCppModelHandler:
    def __init__(self, model_path: str, **kwargs):
        self.llm = Llama(
            model_path=model_path,
            chat_format="chatml",
            n_gpu_layers=-1,
            n_ctx=2048,
            draft_model=LlamaPromptLookupDecoding(num_pred_tokens=2),
            logits_all=True,
            verbose=False,
            **kwargs
        )

        self.create = instructor.patch(
            create=self.llm.create_chat_completion_openai_v1,
            mode=instructor.Mode.JSON_SCHEMA
        )

    def query(self, prompt: str, response_model: Type[BaseModel], callback: Callable, **kwargs):
        response_stream = self.create(
            response_model=instructor.Partial[response_model],
            messages=[{"role": "user", "content": prompt}],
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
