# Redazione LinkedIn — gerarchia multi-agente (Mistral Agents SDK)

Sistema multi-agente che produce post LinkedIn pronti da pubblicare, con
controllo qualità incrociato su **testo, fonti e immagini**.

## Architettura

```
# redattore capo (root, mistral-large-4)
## controllore redazione          -> coordina le sezioni e la coerenza d'insieme
### controllore fonti             -> attendibilità e corrispondenza fonte/affermazione
#### ricercatore fonti            -> web_search + web_fetch, verifica le affermazioni
### controllore testo             -> tono, struttura, chiarezza, onestà
#### scrittore                    -> bozza del post (hook, corpo, chiusura, max 3 hashtag)
### controllore immagini          -> coerenza immagine/post, idoneità a LinkedIn
#### generatore immagini          -> immagine via Gemini (gemini-2.5-flash-image)
```

Flusso: il controllore redazione avvia le tre sezioni; ogni controllore fa
lavorare il proprio operatore e valida il risultato; revisioni e coerenza
d'insieme tornano al controllore redazione (max 3 round) → consegna di post
finale, file immagine ed elenco fonti.

La profondità dell'albero (4 livelli) richiede `SubagentPolicy(max_depth=3)`
sul root agent: il default dell'SDK è 2.

## Setup

1. Installa le dipendenze (serve [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

2. Crea `.env` con le chiavi:

   ```bash
   cp .env.example .env
   # MISTRAL_API_KEY: https://console.mistral.ai/api-keys
   # GEMINI_API_KEY:  https://aistudio.google.com/apikey
   ```

## Uso

Una richiesta singola da riga di comando:

```bash
uv run --env-file .env python main.py "Come l'AI generativa sta cambiando il lavoro degli editor"
```

Chat interattiva con l'agente:

```bash
uv run --env-file .env agents chat
```

Verifica della configurazione (senza chiamare il modello):

```bash
uv run agents info
```

Le immagini generate finiscono in `output/`.

## Personalizzazione

- **Tono e stile dei post**: istruzioni di `scrittore` e `controllore-testo` in `main.py`.
- **Criteri di attendibilità delle fonti**: istruzioni di `ricercatore-fonti` e `controllore-fonti`.
- **Stile visivo**: istruzioni di `generatore-immagini` e `controllore-immagini`.
- **Tolleranza alle revisioni**: campo `Tolleranza` nelle istruzioni di `redattore-capo` (default: 3 round).

## Note

- I tool web (`web_search`, `web_fetch`) non usano API key esterne; le ricerche
  passano dall'endpoint HTML di DuckDuckGo e possono variare nel formato.
- La generazione immagini richiede un modello Gemini con output immagine
  (default: `gemini-2.5-flash-image`, modificabile con `GEMINI_IMAGE_MODEL`).
