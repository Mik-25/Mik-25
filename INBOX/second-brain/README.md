# Second Brain — agente Obsidian (Mistral Agents SDK)

Agente che legge, cerca, crea e organizza le note del tuo vault Obsidian.

## Setup

1. Installa le dipendenze (serve [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

2. Indica il vault e la chiave Mistral in `.env`:

   ```bash
   cp .env.example .env
   # MISTRAL_API_KEY:      https://console.mistral.ai/api-keys
   # OBSIDIAN_VAULT_PATH:  percorso assoluto alla cartella del vault
   ```

   Se `OBSIDIAN_VAULT_PATH` non è impostata, l'agente lavora su `./vault`
   dentro il progetto (utile per provare).

## Uso

Una richiesta singola:

```bash
uv run --env-file .env python main.py "Cosa ho annotato sull'agentic AI?"
```

Chat interattiva:

```bash
uv run --env-file .env agents chat
```

Verifica della configurazione (senza chiamare il modello):

```bash
uv run agents info
```

## Cosa sa fare

- **Recuperare**: cerca nel vault prima di rispondere; le tue note precedono la sua conoscenza generale.
- **Catturare**: propone cartella, titolo, wiki-link `[[...]]` e tag per ogni nuova nota.
- **Organizzare**: una nota = un'idea, con metadati di creazione automatici.
- **Proteggere**: mostra le modifiche proposte prima di applicarle; cancella solo su richiesta esplicita.

## Tools disponibili

| Tool | Cosa fa |
| --- | --- |
| `list_notes` | elenca tutte le note `.md` del vault |
| `search_notes` | ricerca full-text con estrazione delle righe e dei tag |
| `read_note` | legge una nota completa |
| `write_note` | crea una nuova nota (rifusa di sovrascrivere) |
| `append_note` | aggiunge testo in coda a una nota |
| `delete_note` | elimina una nota (solo su richiesta esplicita) |

## Estensioni possibili

- Indicizzazione semantica (embedding) per ricerca per similitudine oltre al full-text.
- Sync con il vault mobile via cartella sincronizzata (iCloud, Syncthing, Git).
- Un subagente "curatore" che rivede e ricollega periodicamente le note.
