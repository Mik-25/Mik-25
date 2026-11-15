"""Second brain: agente Mistral che legge e scrive nel vault Obsidian.

Punta il vault con la variabile d'ambiente OBSIDIAN_VAULT_PATH, ad esempio:
    export OBSIDIAN_VAULT_PATH="/Users/tu/Percorso/AlVault"
"""

import os
import re
from datetime import datetime
from pathlib import Path

from mistralai import agents


def _vault_root() -> Path:
    root = Path(os.environ.get("OBSIDIAN_VAULT_PATH", str(Path(__file__).resolve().parent / "vault"))).expanduser()
    root.mkdir(exist_ok=True)
    return root


def _safe_note_path(name: str) -> Path:
    root = _vault_root()
    if not name.endswith(".md"):
        name += ".md"
    path = (root / name).resolve()
    if root.resolve() not in path.parents and path != root.resolve():
        raise agents.ToolError("Il percorso della nota deve restare dentro il vault.")
    return path


@agents.tool
def list_notes(folder: str = "") -> list[str]:
    """Elenca le note del vault (file .md), anche nelle sottocartelle.

    `folder` è una sottocartella opzionale del vault, ad esempio "Progetti".
    """
    root = _vault_root() / folder if folder else _vault_root()
    if not root.exists():
        raise agents.ToolError(f"La cartella '{folder}' non esiste nel vault.")
    return sorted(str(p.relative_to(_vault_root())) for p in root.rglob("*.md"))


@agents.tool
def search_notes(query: str, max_results: int = 10) -> list[dict[str, str]]:
    """Cerca una parola o frase nel testo di tutte le note del vault.

    Restituisce per ogni nota trovata: percorso, righe corrispondenti e tag.
    """
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    hits: list[dict[str, str]] = []
    for path in sorted(_vault_root().rglob("*.md")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        matches = [line.strip() for line in lines if pattern.search(line)]
        if matches:
            tags = sorted(set(re.findall(r"#[\w/\-]+", "\n".join(lines))))
            hits.append({
                "nota": str(path.relative_to(_vault_root())),
                "righe": " | ".join(matches[:3])[:300],
                "tag": ", ".join(tags[:8]),
            })
        if len(hits) >= max_results:
            break
    if not hits:
        raise agents.ToolError(f"Nessuna nota contiene '{query}'.")
    return hits


@agents.tool
def read_note(name: str) -> str:
    """Legge il contenuto completo di una nota del vault, ad esempio "Progetti/Agente AI"."""
    path = _safe_note_path(name)
    if not path.exists():
        raise agents.ToolError(f"La nota '{name}' non esiste. Usa search_notes o list_notes per trovarla.")
    return path.read_text(encoding="utf-8")


@agents.tool
def write_note(name: str, content: str) -> dict[str, str]:
    """Crea o sostituisce una nota con `content` (testo Markdown).

    Aggiunge automaticamente i metadati di creazione in cima alla nota.
    """
    path = _safe_note_path(name)
    if path.exists():
        raise agents.ToolError(
            f"La nota '{name}' esiste già: usa append_note per aggiungere testo, "
            "o chiedi all'utente prima di sovrascriverla."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\ncreato: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n---\n\n"
    path.write_text(frontmatter + content.strip() + "\n", encoding="utf-8")
    return {"nota": str(path.relative_to(_vault_root())), "esito": "creata"}


@agents.tool
def append_note(name: str, content: str) -> dict[str, str]:
    """Aggiunge `content` in coda a una nota esistente, creandola se manca."""
    path = _safe_note_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        path.write_text(existing.rstrip() + "\n\n" + content.strip() + "\n", encoding="utf-8")
        esito = "aggiornata"
    else:
        frontmatter = f"---\ncreato: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n---\n\n"
        path.write_text(frontmatter + content.strip() + "\n", encoding="utf-8")
        esito = "creata"
    return {"nota": str(path.relative_to(_vault_root())), "esito": esito}


@agents.tool
def delete_note(name: str) -> dict[str, str]:
    """Elimina una nota dal vault. Da usare solo su richiesta esplicita dell'utente."""
    path = _safe_note_path(name)
    if not path.exists():
        raise agents.ToolError(f"La nota '{name}' non esiste.")
    path.unlink()
    return {"nota": str(path.relative_to(_vault_root())), "esito": "eliminata"}


agent = agents.Agent(
    model="mistral-large-4",
    name="second-brain",
    instructions=(
        "Sei il secondo brain dell'autore: gestisci le sue note nel vault Obsidian.\n"
        "IDENTITÀ: curatore metodico e discreto della conoscenza personale.\n"
        "CAPACITÀ: cercare, leggere, creare, aggiornare note con i tuoi tools; "
        "il vault vive nel percorso indicato da OBSIDIAN_VAULT_PATH.\n"
        "PROCEDURA:\n"
        "1. Prima di rispondere a qualsiasi domanda, cerca nel vault con "
        "search_notes: le note dell'utente vengono prima della tua conoscenza "
        "generale.\n"
        "2. Quando catturi una nuova informazione, proponi dove salvarla "
        "(cartella e titolo) e collegali alle note esistenti con wiki-link "
        "[[Titolo nota]] e tag pertinenti.\n"
        "3. Una nota = un'idea. Titoli brevi e descrittivi. Aggiungi sempre "
        "'Fonte:' quando l'informazione viene da fuori.\n"
        "4. Prima di modificare o eliminare una nota esistente, mostra all'utente "
        "cosa cambierai e attendi conferma. delete_note solo su richiesta esplicita.\n"
        "5. A fine di ogni operazione di scrittura, riporta il percorso della "
        "nota toccata.\n"
        "FORMATO: risposte brevi in italiano; per le revisioni del vault usa "
        "elenchi puntati."
    ),
    tools=[list_notes, search_notes, read_note, write_note, append_note, delete_note],
    builtins=agents.Builtins(subagents=False),
)


async def main() -> None:
    import sys

    richiesta = " ".join(sys.argv[1:]) or "Cosa c'è nel mio vault?"
    state = await agent.run(richiesta)
    match state:
        case agents.Completed(text=text):
            print(text)
        case agents.Failed(error=error):
            print(f"Errore: {error.code} - {error.message}")
        case _:
            print(f"Turno non completato: {state}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
