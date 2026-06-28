from __future__ import annotations

import argparse
import json
from pathlib import Path

from .anki import AnkiConnect
from .extractor import extract_notes
from .zig_env import read_zig_env


def main() -> None:
    args = parse_args()
    env = read_zig_env(args.zig_exe)
    std_dir = Path(args.std_dir) if args.std_dir else env.std_dir
    deck = args.deck or f"Zig::Stdlib::{env.version}"
    model = args.model

    notes = extract_notes(std_dir, env.version, args.module)
    if args.limit is not None:
        notes = notes[: args.limit]

    report = build_report(notes, env.version, std_dir, deck, model)
    print_report(report, notes[: args.sample])
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.dry_run or not args.write:
        return

    anki = AnkiConnect(args.anki_url, retries=args.retries)
    anki.ensure_deck(deck)
    anki.ensure_model(model)
    existing = anki.existing_uids(deck)
    if args.prune_stale:
        stale = stale_notes(anki.note_infos(deck), current_uid_sets(notes))
        print(f"prune stale: {len(stale)} notes")
        anki.delete_notes(stale)
        existing = anki.existing_uids(deck)
    to_add = [note for note in notes if note.uid not in existing]
    to_update = [note for note in notes if note.uid in existing]

    added = []
    for index, batch in enumerate(chunks(to_add, args.batch_size), start=1):
        print(f"add batch {index}: {len(batch)} notes")
        added.extend(anki.add_notes(deck, model, batch))
    for index, note in enumerate(to_update, start=1):
        if index % args.batch_size == 1:
            print(f"update batch {(index - 1) // args.batch_size + 1}")
        anki.update_note(existing[note.uid], note)

    print(
        json.dumps(
            {
                "deck": deck,
                "model": model,
                "added": sum(1 for item in added if item is not None),
                "add_failures": sum(1 for item in added if item is None),
                "updated": len(to_update),
            },
            indent=2,
        )
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map Zig stdlib declarations to Anki notes.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print report only; default")
    mode.add_argument("--write", action="store_true", help="write to Anki through AnkiConnect")
    parser.add_argument("--anki-url", default="http://127.0.0.1:8765")
    parser.add_argument("--deck")
    parser.add_argument("--model", default="ZigStdFunction")
    parser.add_argument("--std-dir")
    parser.add_argument("--zig-exe", default="zig")
    parser.add_argument("--module", help="limit to module, e.g. std.mem")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--sample", type=int, default=3)
    parser.add_argument("--report")
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--prune-stale", action="store_true", help="delete old generated notes with same fqn but stale uid")
    return parser.parse_args()


def build_report(notes, version: str, std_dir: Path, deck: str, model: str) -> dict:
    return {
        "zig_version": version,
        "std_dir": str(std_dir),
        "deck": deck,
        "model": model,
        "notes": len(notes),
        "needs_docs": sum(1 for n in notes if "needs_docs" in n.tags),
        "needs_example": sum(1 for n in notes if "needs_example" in n.tags),
        "deprecated": sum(1 for n in notes if "deprecated" in n.tags),
        "generic": sum(1 for n in notes if "generic" in n.tags),
        "modules": len({n.module for n in notes}),
    }


def print_report(report: dict, sample_notes) -> None:
    print(json.dumps(report, indent=2))
    for note in sample_notes:
        print("\n--- sample note ---")
        print(note.front)
        print()
        print(note.back)


def chunks(items, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def current_uid_sets(notes) -> dict[str, set[str]]:
    current: dict[str, set[str]] = {}
    for note in notes:
        current.setdefault(note.fqn, set()).add(note.uid)
    return current


def stale_notes(infos: list[dict], current_by_fqn: dict[str, set[str]]) -> list[int]:
    stale: list[int] = []
    for info in infos:
        fields = info.get("fields", {})
        fqn = fields.get("fqn", {}).get("value", "")
        uid = fields.get("uid", {}).get("value", "")
        current_uids = current_by_fqn.get(fqn)
        if current_uids and uid and uid not in current_uids:
            stale.append(info["noteId"])
    return stale


if __name__ == "__main__":
    main()
