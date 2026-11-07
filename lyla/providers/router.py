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
                from google.genai import types
                self.gemini_client = genai.Client(
                    api_key=self.config.gemini_api_key,
                    http_options=types.HttpOptions(
                        timeout=12000,
                        retry_options=types.HttpRetryOptions(attempts=1)
                    )
                )
            except Exception as e:
                print(f"[Aviso] No se pudo inicializar cliente Gemini: {e}")

        if self.config.groq_api_key:
            try:
                from groq import Groq
                self.groq_client = Groq(api_key=self.config.groq_api_key)
            except Exception as e:
                print(f"[Aviso] No se pudo inicializar cliente Groq: {e}")

    def get_available_models(self) -> List[Dict[str, str]]:
        """Devuelve la lista de modelos disponibles según los proveedores activos."""
        gemini_models = list(self.config.gemini_available_models)
        if self.config.gemini_model not in gemini_models:
            gemini_models.insert(0, self.config.gemini_model)

        groq_models = list(self.config.groq_available_models)
        if self.config.groq_model not in groq_models:
            groq_models.insert(0, self.config.groq_model)

        has_gemini = self.gemini_client is not None or not self.groq_client
        has_groq = self.groq_client is not None or not self.gemini_client

        options: List[Dict[str, str]] = []
        # Intercalar los modelos principales primero para que /model alterne rápido entre Gemini y Groq
        max_len = max(len(gemini_models), len(groq_models))
        for i in range(max_len):
            if has_gemini and i < len(gemini_models):
                options.append({"provider": "gemini", "model": gemini_models[i]})
            if has_groq and i < len(groq_models):
                options.append({"provider": "groq", "model": groq_models[i]})
        return options

    def get_active_model(self) -> Tuple[str, str]:
        """Devuelve (proveedor_activo, modelo_activo)."""
        provider = self.config.default_provider
        model = self.config.gemini_model if provider == "gemini" else self.config.groq_model
        return provider, model

    def switch_model(self, target: Optional[str] = None) -> Tuple[str, str]:
        """
        Cambia entre los modelos/proveedores disponibles.
        Si no se pasa `target`, cicla al siguiente modelo disponible.
        Si se pasa `target` (índice, proveedor o nombre de modelo), selecciona ese.
        """
        options = self.get_available_models()
        if not options:
            return self.get_active_model()

        curr_provider, curr_model = self.get_active_model()

        if not target:
            curr_idx = next(
                (i for i, opt in enumerate(options) if opt["provider"] == curr_provider and opt["model"] == curr_model),
                -1
            )
            chosen = options[(curr_idx + 1) % len(options)]
        else:
            t = target.strip().lower()
            chosen = None
            # 1. Por número de índice (1..N)
            if t.isdigit():
                idx = int(t) - 1
                if 0 <= idx < len(options):
                    chosen = options[idx]
            # 2. Por nombre de proveedor ("gemini" o "groq")
            if chosen is None and t in ("gemini", "groq"):
                if t == "gemini" and (self.gemini_client is not None or not self.groq_client):
                    chosen = {"provider": "gemini", "model": self.config.gemini_model}
                elif t == "groq" and (self.groq_client is not None or not self.gemini_client):
                    chosen = {"provider": "groq", "model": self.config.groq_model}
            # 3. Por coincidencia exacta o parcial de modelo
            if chosen is None:
                for opt in options:
                    full_key = f"{opt['provider']}:{opt['model']}".lower()
                    if t == opt["model"].lower() or t == full_key or t in opt["model"].lower():
                        chosen = opt
                        break

            if chosen is None:
                raise ValueError(f"Modelo o proveedor '{target}' no reconocido.")

        self.config.default_provider = chosen["provider"]
        if chosen["provider"] == "gemini":
            self.config.gemini_model = chosen["model"]
        else:
            self.config.groq_model = chosen["model"]

        return self.get_active_model()

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
