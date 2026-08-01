"""A backend that writes the resolved grammar as text, for inspection."""

from __future__ import annotations

from pathlib import Path

from ...semantics.model import GrammarModel
from ..base import Generator


class DumpGenerator(Generator):
    """Writes one `.txt` file describing the targets and their productions."""

    name = "dump"
    description = "write the resolved grammar as plain text"

    def generate(self, model: GrammarModel, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{Path(model.name).stem}.txt"
        path.write_text(self.render(model), encoding="utf-8")
        return [path]

    def render(self, model: GrammarModel) -> str:
        """Render the model without touching the file system."""
        lines = [f"grammar {model.name}"]
        for target in model.targets:
            lines.append(f"  target {target.name}")
            for production in target.productions.values():
                marker = production.choice_symbol or "="
                lines.append(f"    {production.name} ({len(production.alternatives)} alt, {marker})")
                for attribute in production.attributes:
                    lines.append(f"      > {attribute}")
        return "\n".join(lines) + "\n"
