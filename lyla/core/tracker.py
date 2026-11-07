import time
from typing import Dict, Any, List

class ResourceTracker:
    """
    Rastreador de consumo de tokens, latencia de red y llamadas a APIs cloud.
    Monitorea el uso de recursos para formular recomendaciones proactivas ("Oye Víctor...").
    """
    def __init__(self):
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.calls_by_provider: Dict[str, int] = {}
        self.latencies: Dict[str, List[float]] = {}
        self.session_start = time.time()
        self.proactive_alerts: List[str] = []

    def record_call(self, provider: str, tokens_in: int, tokens_out: int, latency_seconds: float):
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.calls_by_provider[provider] = self.calls_by_provider.get(provider, 0) + 1
        
        if provider not in self.latencies:
            self.latencies[provider] = []
        self.latencies[provider].append(latency_seconds)

    def check_proactive_advice(self) -> List[str]:
        """
        Analiza métricas y devuelve sugerencias si se superan ciertos umbrales.
        """
        suggestions = []
        total_tokens = self.total_tokens_in + self.total_tokens_out

        # Si el consumo de tokens en la sesión supera 30k
        if total_tokens > 30000 and "high_tokens" not in self.proactive_alerts:
            suggestions.append(
                "Oye Víctor, hemos superado los 30,000 tokens en esta sesión. "
                "Para no desgastar tu cuota, sugiero condensar la memoria de trabajo y usar Gemini Flash o Groq. ¿Te parece bien?"
            )
            self.proactive_alerts.append("high_tokens")

        # Si una API muestra latencia promedio alta (> 4.0 segundos)
        for provider, lats in self.latencies.items():
            if len(lats) >= 3:
                avg_lat = sum(lats[-3:]) / 3.0
                alert_key = f"high_latency_{provider}"
                if avg_lat > 4.0 and alert_key not in self.proactive_alerts:
                    suggestions.append(
                        f"Oye Víctor, la latencia con {provider} está rondando los {avg_lat:.1f}s. "
                        f"Podemos alternar automáticamente a un proveedor cloud más ágil si lo deseas."
                    )
                    self.proactive_alerts.append(alert_key)

        return suggestions

    def get_summary(self) -> Dict[str, Any]:
        return {
            "total_tokens_in": self.total_tokens_in,
            "total_tokens_out": self.total_tokens_out,
            "total_tokens": self.total_tokens_in + self.total_tokens_out,
            "calls_by_provider": self.calls_by_provider,
            "uptime_seconds": round(time.time() - self.session_start, 1)
        }
