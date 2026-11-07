import time
from typing import List, Dict, Any, Tuple, Optional
from ..core.config import Config
from ..core.tracker import ResourceTracker

class LLMRouter:
    """
    Router Multi-Proveedor Cloud:
    Gestiona llamadas hacia Google Gemini y Groq con balanceo, medición de latencia y tokens.
    """
    def __init__(self, config: Config, tracker: ResourceTracker):
        self.config = config
        self.tracker = tracker
        self.gemini_client = None
        self.groq_client = None
        
        self._init_clients()

    def _init_clients(self):
        if self.config.gemini_api_key:
            try:
                from google import genai
                self.gemini_client = genai.Client(api_key=self.config.gemini_api_key)
            except Exception as e:
                print(f"[Aviso] No se pudo inicializar cliente Gemini: {e}")

        if self.config.groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.config.groq_api_key)
            except Exception as e:
                print(f"[Aviso] No se pudo inicializar cliente Groq: {e}")

    def generate(self, system_prompt: str, history: List[Dict[str, str]], user_message: str, preferred_provider: Optional[str] = None) -> Tuple[str, str]:
        provider = preferred_provider or self.config.default_provider
        
        # Intentar con el proveedor preferido; si falla o no está configurado, intentar el alternativo
        if provider == "gemini" and self.gemini_client:
            try:
                return self._call_gemini(system_prompt, history, user_message), "gemini"
            except Exception as e:
                print(f"[Router] Falló Gemini ({e}), intentando fallback con Groq...")
                if self.groq_client:
                    return self._call_groq(system_prompt, history, user_message), "groq"
                raise e
        elif provider == "groq" and self.groq_client:
            try:
                return self._call_groq(system_prompt, history, user_message), "groq"
            except Exception as e:
                print(f"[Router] Falló Groq ({e}), intentando fallback con Gemini...")
                if self.gemini_client:
                    return self._call_gemini(system_prompt, history, user_message), "gemini"
                raise e
        else:
            # Si el preferido no está configurado, usar el que esté disponible
            if self.gemini_client:
                return self._call_gemini(system_prompt, history, user_message), "gemini"
            elif self.groq_client:
                return self._call_groq(system_prompt, history, user_message), "groq"
            else:
                raise ValueError(
                    "No se encontró ninguna clave de API configurada. "
                    "Por favor agrega tu GEMINI_API_KEY o GROQ_API_KEY en el archivo .env"
                )

    def _call_gemini(self, system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
        from google.genai import types
        start_t = time.time()
        
        contents = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=h["content"])]))
        contents.append(types.Content(role="user", parts=[types.Part.from_text(text=user_message)]))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7
        )
        
        response = self.gemini_client.models.generate_content(
            model=self.config.gemini_model,
            contents=contents,
            config=config
        )
        latency = time.time() - start_t
        
        tokens_in = response.usage_metadata.prompt_token_count if response.usage_metadata else len(user_message) // 4
        tokens_out = response.usage_metadata.candidates_token_count if response.usage_metadata else len(response.text or "") // 4
        
        self.tracker.record_call("gemini", tokens_in, tokens_out, latency)
        return response.text or ""

    def _call_groq(self, system_prompt: str, history: List[Dict[str, str]], user_message: str) -> str:
        start_t = time.time()
        messages = [{"role": "system", "content": system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": user_message})

        chat_completion = self.groq_client.chat.completions.create(
            messages=messages,
            model=self.config.groq_model,
            temperature=0.7
        )
        latency = time.time() - start_t

        content = chat_completion.choices[0].message.content or ""
        usage = chat_completion.usage
        tokens_in = usage.prompt_tokens if usage else len(user_message) // 4
        tokens_out = usage.completion_tokens if usage else len(content) // 4

        self.tracker.record_call("groq", tokens_in, tokens_out, latency)
        return content
