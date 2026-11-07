import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

# Límites diarios aproximados en capa gratuita (Tokens Por Día - TPD) para cálculo de porcentajes
DAILY_TOKEN_LIMITS: Dict[str, int] = {
    "gemini-3.5-flash": 500_000,
    "gemini-3.5-flash-lite": 1_000_000,
    "gemini-3.1-flash-lite": 1_000_000,
    "gemini-3.8-flash": 500_000,
    "openai/gpt-oss-120b": 100_000,
    "qwen/qwen3.8-27b": 500_000,
    "openai/gpt-oss-20b": 500_000,
}


class ResourceTracker:
    """
    Rastreador de consumo de tokens, latencia de red y llamadas a APIs cloud.
    Persiste métricas por modelo en SQLite para compartir el estado entre CLI y HUD.
    """
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or (Path(__file__).resolve().parent.parent.parent / "lyla_memory.db")
        self.total_tokens_in = 0
        self.total_tokens_out = 0
        self.calls_by_provider: Dict[str, int] = {}
        self.tokens_by_model: Dict[str, int] = {}
        self.latencies: Dict[str, List[float]] = {}
        self.session_start = time.time()
        self.proactive_alerts: List[str] = []
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS model_usage_stats (
                        usage_date TEXT NOT NULL,
                        provider TEXT NOT NULL,
                        model TEXT NOT NULL,
                        tokens_in INTEGER DEFAULT 0,
                        tokens_out INTEGER DEFAULT 0,
                        calls INTEGER DEFAULT 0,
                        last_latency REAL DEFAULT 0.0,
                        PRIMARY KEY (usage_date, provider, model)
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def record_call(
        self,
        provider: str,
        tokens_in: int,
        tokens_out: int,
        latency_seconds: float,
        model: str = ""
    ):
        self.total_tokens_in += tokens_in
        self.total_tokens_out += tokens_out
        self.calls_by_provider[provider] = self.calls_by_provider.get(provider, 0) + 1
        if model:
            self.tokens_by_model[model] = self.tokens_by_model.get(model, 0) + tokens_in + tokens_out

        if provider not in self.latencies:
            self.latencies[provider] = []
        self.latencies[provider].append(latency_seconds)

        # Persistir en SQLite por día y modelo
        today = datetime.now().strftime("%Y-%m-%d")
        model_key = model or provider
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO model_usage_stats (usage_date, provider, model, tokens_in, tokens_out, calls, last_latency)
                    VALUES (?, ?, ?, ?, ?, 1, ?)
                    ON CONFLICT(usage_date, provider, model) DO UPDATE SET
                        tokens_in = tokens_in + excluded.tokens_in,
                        tokens_out = tokens_out + excluded.tokens_out,
                        calls = calls + 1,
                        last_latency = excluded.last_latency
                """, (today, provider, model_key, tokens_in, tokens_out, round(latency_seconds, 2)))
                conn.commit()
        except Exception:
            pass

    def get_models_status_report(self, available_models: List[Dict[str, str]], active_model: str = "") -> List[Dict[str, Any]]:
        """
        Devuelve el estado detallado por cada modelo disponible:
        tokens usados hoy, límite diario (Free Tier), % consumido, % disponible, llamadas y latencia.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        db_rows: Dict[str, Dict[str, Any]] = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT provider, model, tokens_in, tokens_out, calls, last_latency FROM model_usage_stats WHERE usage_date = ?",
                    (today,)
                )
                for r in cursor.fetchall():
                    db_rows[f"{r['provider']}:{r['model']}"] = dict(r)
        except Exception:
            pass

        report: List[Dict[str, Any]] = []
        for opt in available_models:
            prov = opt["provider"]
            mod = opt["model"]
            key = f"{prov}:{mod}"
            row = db_rows.get(key, {})
            t_in = int(row.get("tokens_in", 0))
            t_out = int(row.get("tokens_out", 0))
            t_total = t_in + t_out
            calls = int(row.get("calls", 0))
            lat = float(row.get("last_latency", 0.0))
            limit = DAILY_TOKEN_LIMITS.get(mod, 500_000)
            used_pct = min(100.0, (t_total * 100.0) / limit) if limit > 0 else 0.0
            rem_pct = max(0.0, 100.0 - used_pct)

            report.append({
                "provider": prov,
                "model": mod,
                "active": (mod == active_model),
                "tokens_in": t_in,
                "tokens_out": t_out,
                "tokens_total": t_total,
                "daily_limit": limit,
                "used_pct": round(used_pct, 2),
                "remaining_pct": round(rem_pct, 2),
                "calls": calls,
                "last_latency": lat,
            })
        return report

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
