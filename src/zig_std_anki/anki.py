from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Iterable

from .models import FIELDS, Note


class AnkiConnect:
    def __init__(self, url: str = "http://127.0.0.1:8765", retries: int = 3) -> None:
        self.url = url
        self.retries = retries

    def request(self, action: str, **params):
        payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
        req = urllib.request.Request(self.url, data=payload, headers={"Content-Type": "application/json"})
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as res:
                    data = json.loads(res.read().decode("utf-8"))
            except urllib.error.URLError as exc:
                last_error = RuntimeError(f"AnkiConnect unreachable at {self.url}: {exc}")
            else:
                if data.get("error") is None:
                    return data.get("result")
                last_error = RuntimeError(f"AnkiConnect {action} failed: {data['error']}")
            if attempt < self.retries:
                time.sleep(2 * (attempt + 1))
        assert last_error is not None
        raise last_error

    def ensure_deck(self, deck: str) -> None:
        if deck not in self.request("deckNames"):
            self.request("createDeck", deck=deck)

    def ensure_model(self, model: str) -> None:
        if model not in self.request("modelNames"):
            self.request(
                "createModel",
                modelName=model,
                inOrderFields=FIELDS,
                css=_CSS,
                isCloze=False,
                cardTemplates=[_CARD_TEMPLATE],
            )
            return
        self.update_model(model)

    def update_model(self, model: str) -> None:
        self.request(
            "updateModelTemplates",
            model={
                "name": model,
                "templates": {
                    "API": {
                        "Front": _CARD_TEMPLATE["Front"],
                        "Back": _CARD_TEMPLATE["Back"],
                    }
                },
            },
        )
        self.request("updateModelStyling", model={"name": model, "css": _CSS})

    def existing_uids(self, deck: str) -> dict[str, int]:
        ids = self.request("findNotes", query=f'deck:"{deck}"')
        if not ids:
            return {}
        result: dict[str, int] = {}
        for info in self.request("notesInfo", notes=ids):
            fields = info.get("fields", {})
            uid = fields.get("uid", {}).get("value", "")
            if uid:
                result[uid] = info["noteId"]
        return result

    def note_infos(self, deck: str) -> list[dict]:
        ids = self.request("findNotes", query=f'deck:"{deck}"')
        if not ids:
            return []
        return self.request("notesInfo", notes=ids)

    def add_notes(self, deck: str, model: str, notes: Iterable[Note]) -> list[int | None]:
        payload = [
            {
                "deckName": deck,
                "modelName": model,
                "fields": note.fields(),
                "tags": list(note.tags),
                "options": {"allowDuplicate": False, "duplicateScope": "deck"},
            }
            for note in notes
        ]
        if not payload:
            return []
        return self.request("addNotes", notes=payload)

    def update_note(self, note_id: int, note: Note) -> None:
        self.request("updateNoteFields", note={"id": note_id, "fields": note.fields()})

    def delete_notes(self, note_ids: list[int]) -> None:
        if note_ids:
            self.request("deleteNotes", notes=note_ids)

    def move_cards(self, card_ids: list[int], deck: str) -> None:
        if card_ids:
            self.request("changeDeck", cards=card_ids, deck=deck)


_CARD_TEMPLATE = {
    "Name": "API",
    "Front": """
<main class="wrap">
  <section class="hero">
    <div class="eyebrow">
      <span>{{module}}</span>
      <span>{{kind}}</span>
      <span>Zig {{zig_version}}</span>
    </div>
    <h1>{{fqn}}</h1>
    <pre class="code signature"><code>{{signature}}</code></pre>
  </section>
</main>
""",
    "Back": """
{{FrontSide}}
<main class="wrap back">
  <section class="panel">
    <h2>Description</h2>
    <p>{{definition}}</p>
  </section>
  <section class="panel">
    <h2>Return</h2>
    <pre class="info"><code>{{back}}</code></pre>
  </section>
  <section class="panel">
    <h2>Structure</h2>
    <pre class="info"><code>{{front}}</code></pre>
  </section>
  <section class="panel">
    <h2>Example</h2>
    <pre class="code"><code>{{example}}</code></pre>
  </section>
  <section class="panel">
    <h2>Tags</h2>
    <div>{{tags}}</div>
  </section>
  <footer class="source">{{source_path}}:{{source_line}}</footer>
</main>
""",
}


_CSS = """
html,
body {
  background: #151515 !important;
}
.card {
  min-height: 100vh;
  box-sizing: border-box;
  font-family: "Segoe UI Variable", "Segoe UI", Arial, Helvetica, sans-serif;
  font-size: 17px;
  line-height: 1.5;
  text-align: left;
  color: #f0f0f0;
  background: #151515;
  font-weight: 520;
}
.wrap {
  max-width: 1040px;
  margin: 0 auto;
  padding: 24px 22px;
}
.hero {
  border: 1px solid #343434;
  background: #202020;
  padding: 22px 24px;
  box-shadow: 0 14px 40px rgba(0, 0, 0, .24);
}
.eyebrow {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}
.eyebrow span {
  display: inline-block;
  padding: 4px 9px;
  border: 1px solid #4a4a4a;
  color: #d6d6d6;
  background: #252525;
  font-size: 12px;
  letter-spacing: .06em;
  text-transform: uppercase;
  font-weight: 700;
}
h1 {
  margin: 4px 0 18px;
  color: #fff;
  font-size: 32px;
  line-height: 1.15;
  font-weight: 760;
  letter-spacing: 0;
}
h2 {
  margin: 0 0 8px;
  color: #e9e9e9;
  font-size: 14px;
  line-height: 1.2;
  text-transform: uppercase;
  letter-spacing: .06em;
  border-bottom: 1px solid #444;
  padding-bottom: 6px;
  font-weight: 800;
}
p {
  margin: 0;
  color: #eeeeee;
  font-weight: 560;
}
.code {
  margin: 0;
  padding: 15px 16px;
  overflow-x: auto;
  white-space: pre;
  word-break: normal;
  font-family: "Cascadia Mono", "Cascadia Code", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: 14px;
  line-height: 1.7;
  font-weight: 400;
  color: #e6edf3;
  background: #161a21;
  border: 1px solid #303846;
  border-left: 3px solid #6ea8fe;
  border-radius: 4px;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}
.tok-kw {
  color: #f47067;
  font-weight: 500;
}
.tok-type {
  color: #76b7ff;
  font-weight: 450;
}
.tok-builtin {
  color: #c8a6ff;
}
.tok-string {
  color: #9dd9ff;
}
.tok-number {
  color: #8cc8ff;
}
.tok-comment {
  color: #8d96a0;
  font-style: italic;
}
.signature {
  font-size: 14px;
}
.info {
  margin: 0;
  padding: 12px 14px;
  white-space: pre-wrap;
  font-family: "Segoe UI Variable", "Segoe UI", Arial, Helvetica, sans-serif;
  font-size: 15px;
  line-height: 1.5;
  font-weight: 560;
  color: #f0f0f0;
  background: #181a1f;
  border: 1px solid #3f4652;
  border-radius: 4px;
}
.panel {
  margin-top: 18px;
  border: 1px solid #343434;
  background: #202020;
  padding: 16px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .18);
}
.tag {
  display: inline-block;
  margin: 4px 6px 4px 0;
  padding: 4px 8px;
  border: 1px solid #555;
  background: #252525;
  color: #e8e8e8;
  font-size: 12px;
  line-height: 1.2;
  font-weight: 700;
  text-transform: uppercase;
}
.tag-module {
  border-color: #38bdf8;
  color: #bae6fd;
}
.tag-version {
  border-color: #a78bfa;
  color: #ddd6fe;
}
.tag-part {
  border-color: #f472b6;
  color: #fbcfe8;
}
.tag-generic {
  border-color: #fbbf24;
  color: #fde68a;
}
.tag-deprecated {
  border-color: #fb7185;
  color: #fecdd3;
}
.tag-needs-docs {
  border-color: #f97316;
  color: #fed7aa;
}
.tag-call-shape {
  border-color: #34d399;
  color: #bbf7d0;
}
.tag-neutral {
  border-color: #6b7280;
  color: #e5e7eb;
}
.source {
  margin-top: 18px;
  color: #b5beca;
  font-size: 13px;
  border-top: 1px solid #424242;
  padding-top: 8px;
  font-weight: 600;
}
hr {
  display: none;
}
"""
