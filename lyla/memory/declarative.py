from pathlib import Path

class DeclarativeMemory:
    """
    Capa 1: Memoria Declarativa en Markdown (Transparencia, editable y Git-friendly).
    Carga el perfil de usuario (profile.md) y las reglas/personalidad (rules.md).
    """
    def __init__(self, config_dir: Path):
        self.config_dir = config_dir
        self.profile_path = config_dir / "profile.md"
        self.rules_path = config_dir / "rules.md"
        self.skills_path = config_dir.parent / "SKILLS.md"

    def get_system_prompt_context(self) -> str:
        parts = []
        if self.rules_path.exists():
            parts.append(self.rules_path.read_text(encoding="utf-8").strip())
        if self.profile_path.exists():
            parts.append("### Contexto del Usuario:\n" + self.profile_path.read_text(encoding="utf-8").strip())
        if self.skills_path.exists():
            parts.append("### Comandos y Skills Disponibles:\n" + self.skills_path.read_text(encoding="utf-8").strip())
        return "\n\n---\n\n".join(parts)

    def append_preference(self, key_fact: str):
        """Permite añadir notas o preferencias detectadas al final de profile.md."""
        if not self.profile_path.exists():
            self.profile_path.write_text(f"# Perfil de Usuario\n\n- {key_fact}\n", encoding="utf-8")
        else:
            with open(self.profile_path, "a", encoding="utf-8") as f:
                f.write(f"\n- {key_fact}")
