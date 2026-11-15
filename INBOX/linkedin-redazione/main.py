"""Redazione LinkedIn: gerarchia multi-agente con Mistral Agents SDK.

# redattore capo
## controllore redazione
### controllore fonti
#### ricercatore fonti
### controllore testo
#### scrittore
### controllore immagini
#### generatore immagini
"""

import base64
import json
import os
import re
import urllib.parse
import urllib.request
from html import unescape
from pathlib import Path

from mistralai import agents

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"


# ---------------------------------------------------------------- tools web

@agents.tool
def web_search(query: str, max_results: int = 5) -> list[dict[str, str]]:
    """Cerca sul web e restituisce titoli, URL e snippet dei risultati.

    Usala per trovare fonti attendibili (istituzioni, testate giornalistiche,
    paper, documentazione ufficiale) su un argomento.
    """
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query, "count": str(max_results)})
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept-Language": "it,it-IT;q=0.9,en;q=0.8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise agents.ToolError(f"Ricerca web non riuscita: {exc}") from exc

    results: list[dict[str, str]] = []
    for block in re.finditer(r'<li class="b_algo"[^>]*>(.*?)</li>', html, re.DOTALL):
        body = block.group(1)
        link = re.search(r'<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, re.DOTALL)
        if not link:
            continue
        href, title = link.group(1), re.sub(r"<[^>]+>", "", link.group(2))
        encoded = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", unescape(href))
        if encoded:
            padding = "=" * (-len(encoded.group(1)) % 4)
            try:
                href = base64.urlsafe_b64decode(encoded.group(1) + padding).decode("utf-8", errors="replace")
            except Exception:
                pass
        snippet_match = re.search(r"<p[^>]*>(.*?)</p>", body, re.DOTALL)
        snippet = re.sub(r"<[^>]+>", "", snippet_match.group(1)) if snippet_match else ""
        results.append({"title": unescape(title).strip(), "url": href, "snippet": unescape(snippet).strip()[:300]})
        if len(results) >= max_results:
            break
    if not results:
        raise agents.ToolError("Nessun risultato trovato: prova una query diversa.")
    return results


@agents.tool
def web_fetch(url: str, max_chars: int = 6000) -> str:
    """Scarica una pagina web e ne restituisce il testo principale.

    Usala per leggere una fonte e verificare che dica davvero ciò che il post afferma.
    """
    if not url.startswith(("http://", "https://")):
        raise agents.ToolError("URL non valido: deve iniziare con http:// o https://")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (redazione-agents)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise agents.ToolError(f"Impossibile scaricare la pagina: {exc}") from exc

    html = re.sub(r"<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


# ------------------------------------------------------------- tool immagini

@agents.tool
def generate_image(prompt: str, file_name: str) -> dict[str, str]:
    """Genera un'immagine con Gemini e la salva in output/.

    Args illustrativi: `prompt` descrive l'immagine in dettaglio (soggetto,
    stile, atmosfera, formato quadrato 1:1 adatto a LinkedIn); `file_name`
    è il nome del file senza estensione, in snake_case.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise agents.ToolError("GEMINI_API_KEY non impostata: serve per generare immagini.")
    if not re.fullmatch(r"[a-z0-9_]+", file_name):
        raise agents.ToolError("file_name non valido: usa solo lettere minuscole, cifre e underscore.")

    payload = {
        "contents": [{"parts": [{"text": f"{prompt}\n\nFormato quadrato 1:1, adatto a un post LinkedIn."}]}],
    }
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise agents.ToolError(f"Chiamata a Gemini non riuscita: {exc}") from exc

    image_part = next(
        (p for c in data.get("candidates", []) for p in c.get("content", {}).get("parts", []) if "inlineData" in p),
        None,
    )
    if image_part is None:
        raise agents.ToolError(f"Gemini non ha restituito un'immagine: {json.dumps(data)[:300]}")

    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / f"{file_name}.png"
    path.write_bytes(base64.b64decode(image_part["inlineData"]["data"]))
    return {"file": str(path), "note": "Immagine generata e salvata."}


# ------------------------------------------------------------ livello 3: operatori

RICERCATORE_FONTI = agents.Subagent(
    name="ricercatore-fonti",
    description="Cerca sul web fonti attendibili che confermino o smentiscano le affermazioni del post.",
    instructions=(
        "Sei il ricercatore di fonti della redazione.\n"
        "PROCEDURA:\n"
        "1. Per ogni affermazione fattuale segnata [FONTE: ...] nel post, "
        "usa web_search per trovare fonti attendibili: istituzioni, testate "
        "riconosciute, paper, documentazione ufficiale. Evita blog personali "
        "e contenuti promozionali.\n"
        "2. Apri con web_fetch le 1-2 fonti più promettenti per ogni "
        "affermazione e verifica che dicano davvero ciò che il post afferma.\n"
        "3. Rispondi con un elenco: affermazione -> fonte (titolo, URL, cosa "
        "dice esattamente la fonte) -> ESITO: CONFERMATA / PARZIALE / NON "
        "TROVATA / CONTRADDETTA."
    ),
    tools=[web_search, web_fetch],
    builtins=agents.Builtins(subagents=False),
)

SCRITTORE = agents.Subagent(
    name="scrittore",
    description="Scrive la bozza del post LinkedIn a partire da tema, fonti e materiale fornito.",
    instructions=(
        "Sei uno scrittore di post LinkedIn. Scrivi UNA bozza di post in italiano.\n"
        "IDENTITÀ: voce dell'autore, professionista che scrive per la sua rete.\n"
        "TONO: professionale ma con linguaggio accessibile a tutti, anche a chi "
        "non conosce l'argomento. Zero gergo inutile: se usi un termine tecnico, "
        "spiegalo con una frase semplice.\n"
        "PROCEDURA:\n"
        "1. Usa solo il materiale e le informazioni che ricevi nel compito; "
        "non inventare dati, numeri o citazioni.\n"
        "2. Struttura il post così: hook nelle prime 2 righe (ferma lo scroll), "
        "corpo con 3-5 paragrafi brevi o elenco puntato, chiusura con una "
        "riflessione o una domanda aperta.\n"
        "3. Massimo 1300 caratteri. Frasi brevi. Un'idea per paragrafo.\n"
        "4. Al massimo 3 hashtag pertinenti, in coda al post.\n"
        "5. Segna ogni affermazione fattuale con [FONTE: descrizione], così il "
        "controllore potrà verificarla.\n"
        "FORMATO: consegna solo il testo del post, niente commenti tuoi."
    ),
    builtins=agents.Builtins(subagents=False),
)

GENERATORE_IMMAGINI = agents.Subagent(
    name="generatore-immagini",
    description="Genera l'immagine del post LinkedIn con Gemini, coerente con il testo.",
    instructions=(
        "Sei il generatore di immagini della redazione.\n"
        "PROCEDURA:\n"
        "1. Ricevi il testo (o il riassunto) del post. Ricavane il concetto "
        "visivo centrale, non una illustrazione letterale del titolo.\n"
        "2. Scrivi un prompt dettagliato per Gemini: soggetto, stile "
        "(fotorealistico o illustrazione flat, coerente col tono professionale "
        "ma accessibile dell'autore), palette sobria, niente testo dentro "
        "l'immagine.\n"
        "3. Chiama generate_image una sola volta con quel prompt.\n"
        "4. Rispondi con: percorso del file e in una frase perché l'immagine "
        "rispecchia il post."
    ),
    tools=[generate_image],
    builtins=agents.Builtins(subagents=False),
)

# ------------------------------------------------------------ livello 2: controllori

CONTROLLORE_FONTI = agents.Subagent(
    name="controllore-fonti",
    description="Verifica con il ricercatore che ogni affermazione del post sia coperta da una fonte attendibile.",
    instructions=(
        "Sei il controllore delle fonti, a capo della sezione Fonti.\n"
        "PROCEDURA:\n"
        "1. Ricevi il post con le sue affermazioni [FONTE: ...]. Avvia il "
        "ricercatore-fonti passandogli il testo completo del post e attendi "
        "il suo rapporto.\n"
        "2. VERIFICA per ogni affermazione:\n"
        "   a. La fonte è attendibile (istituzione, testata riconosciuta, "
        "paper, documentazione ufficiale)?\n"
        "   b. La fonte dice davvero ciò che il post afferma, senza "
        "esagerazioni o deformazioni?\n"
        "   c. Ogni numero, data o citazione corrisponde alla fonte?\n"
        "3. Se un'affermazione resta senza fonte valida, puoi rinviare il "
        "punto al ricercatore con una richiesta più precisa (una sola volta).\n"
        "FORMATO DEL VERDETTO:\n"
        "- ESITO: APPROVATE / DA CORREGGERE\n"
        "- Per ogni problema: l'affermazione, il motivo, la correzione proposta."
    ),
    subagents=[RICERCATORE_FONTI],
)

CONTROLLORE_TESTO = agents.Subagent(
    name="controllore-testo",
    description="Fa scrivere la bozza allo scrittore e ne controlla tono, struttura, chiarezza e onestà.",
    instructions=(
        "Sei il controllore del testo, a capo della sezione Post.\n"
        "PROCEDURA:\n"
        "1. Avvia lo scrittore passandogli tema, materiale e fonti ricevuti "
        "dal controllore della redazione. Attendi la bozza.\n"
        "2. VERIFICA la bozza:\n"
        "   a. Tono: professionale ma accessibile a chi non conosce "
        "l'argomento; ogni termine tecnico è spiegato.\n"
        "   b. Struttura: hook nelle prime 2 righe, corpo chiaro, chiusura "
        "con riflessione o domanda.\n"
        "   c. Lunghezza: massimo 1300 caratteri; frasi brevi; un'idea per "
        "paragrafo.\n"
        "   d. Onestà: nessun dato, numero o citazione inventato.\n"
        "   e. Hashtag: al massimo 3, pertinenti.\n"
        "3. Se la bozza ha problemi, rinviiala allo scrittore con le "
        "correzioni richieste (massimo 2 revisioni interne), poi ricontrolla.\n"
        "FORMATO DEL VERDETTO:\n"
        "- ESITO: APPROVATO / DA CORREGGERE\n"
        "- Bozza finale controllata.\n"
        "- Elenco dei problemi trovati e corretti."
    ),
    subagents=[SCRITTORE],
)

CONTROLLORE_IMMAGINI = agents.Subagent(
    name="controllore-immagini",
    description="Fa generare l'immagine al generatore e controlla che sia coerente con il post.",
    instructions=(
        "Sei il controllore delle immagini, a capo della sezione Immagini.\n"
        "PROCEDURA:\n"
        "1. Avvia il generatore-immagini passandogli il testo del post. "
        "Attendi percorso del file e descrizione.\n"
        "2. VERIFICA:\n"
        "   a. L'immagine rappresenta il concetto centrale del post, non "
        "solo un dettaglio decorativo?\n"
        "   b. Lo stile è adatto a un post professionale ma accessibile?\n"
        "   c. Non contiene testo sovrapposto, loghi, volti riconoscibili "
        "non autorizzati o elementi fuorvianti rispetto al contenuto?\n"
        "3. Se l'immagine non passa, rinviiala al generatore con il prompt "
        "corretto (massimo 2 rigenerazioni), poi ricontrolla.\n"
        "FORMATO DEL VERDETTO:\n"
        "- ESITO: APPROVATA / DA CORREGGERE\n"
        "- Percorso del file approvato e descrizione."
    ),
    subagents=[GENERATORE_IMMAGINI],
)

# ------------------------------------------------------------ livello 1: controllore redazione

CONTROLLORE_REDAZIONE = agents.Subagent(
    name="controllore-redazione",
    description=(
        "A capo della redazione: coordina le sezioni Fonti, Post e Immagini e "
        "verifica che i tre elementi siano corretti e coerenti tra loro."
    ),
    instructions=(
        "Sei il Controllore della Redazione: coordini le tre sezioni e rispondi "
        "al redattore capo con il materiale finale approvato. Ricevi tema, "
        "materiale e fonti già raccolte.\n"
        "PROCEDURA:\n"
        "1. Avvia il controllore-testo passando tema, materiale e fonti. "
        "Attendi la bozza approvata.\n"
        "2. Avvia il controllore-fonti passando la bozza (con le affermazioni "
        "[FONTE: ...]) e il materiale originale. Attendi il verdetto.\n"
        "3. Avvia il controllore-immagini passando la bozza approvata. Attendi "
        "il verdetto con il file.\n"
        "4. Verifica la coerenza d'insieme: post, fonti e immagine raccontano "
        "la stessa cosa, senza contraddizioni né affermazioni non coperte.\n"
        "5. Se qualcosa non passa, rinviialo alla sezione competente con le "
        "correzioni richieste e ripeti i controlli. Tolleranza: massimo 3 "
        "round totali.\n"
        "FORMATO DELLA RELAZIONE FINALE AL REDATTORE CAPO:\n"
        "- VERDETTO: APPROVA / RILAVORA\n"
        "- POST FINALE: (testo pronto da pubblicare)\n"
        "- IMMAGINE: (percorso del file e descrizione)\n"
        "- FONTI: (elenco degli URL usati)\n"
        "- ROUND DI REVISIONE: (numero)\n"
        "Sii severo: approva solo se tutti i controlli passano."
    ),
    subagents=[CONTROLLORE_FONTI, CONTROLLORE_TESTO, CONTROLLORE_IMMAGINI],
)

# ------------------------------------------------------------ root: redattore capo

agent = agents.Agent(
    model="mistral-large-4",
    name="redattore-capo",
    instructions=(
        "Sei il Redattore Capo della redazione LinkedIn dell'autore. Ricevi un "
        "tema (eventualmente con materiale, note o fonti già raccolte).\n"
        "PROCEDURA:\n"
        "1. Avvia il controllore-redazione passando tema, materiale e ogni "
        "informazione utile. Attendi la sua relazione finale.\n"
        "2. Se la relazione è RILAVORA, rinviiala al controllore-redazione con "
        "le correzioni richieste (massimo 3 round totali).\n"
        "3. Consegna all'utente la relazione approvata, con: post finale, "
        "percorso dell'immagine, fonti e round di revisione.\n"
        "Non pubblicare nulla tu stesso, non scrivere o correggere il post di "
        "tuo pugno e non avviare altri agenti: tutto passa dal controllore-redazione."
    ),
    subagents=[CONTROLLORE_REDAZIONE],
    subagent_policy=agents.SubagentPolicy(max_depth=3, concurrent_child_turn_limit=4),
)


async def main() -> None:
    import sys

    tema = " ".join(sys.argv[1:]) or "L'importanza di dormire bene per la produttività sul lavoro"
    print(f"Tema: {tema}\n")
    state = await agent.run(tema)
    match state:
        case agents.Completed(text=text):
            print(text)
        case agents.Blocked():
            print("Il turno è in attesa di approvazioni:", state.callbacks)
        case agents.Failed(error=error):
            print(f"Errore: {error.code} - {error.message}")
        case _:
            print(f"Turno non completato: {state}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
