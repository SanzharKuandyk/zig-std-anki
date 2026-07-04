from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Part:
    index: int
    slug: str
    title: str

    @property
    def tag(self) -> str:
        return f"part_{self.index:02d}_{self.slug}"

    @property
    def deck_suffix(self) -> str:
        return f"{self.index:02d} {self.title}"


PARTS = [
    Part(1, "core", "Core Basics"),
    Part(2, "memory", "Memory & Collections"),
    Part(3, "io", "Files & IO"),
    Part(4, "text", "Text & Data"),
    Part(5, "algorithms", "Math & Algorithms"),
    Part(6, "systems", "System & Build"),
    Part(7, "advanced", "Advanced & Niche"),
]


def part_for(module: str, fqn: str) -> Part:
    path = f"{module}.{fqn}".lower()
    name = fqn.rsplit(".", 1)[-1]

    core_fqns = {
        "std.debug.print",
        "std.mem.eql",
        "std.mem.startsWith",
        "std.mem.endsWith",
        "std.mem.indexOf",
        "std.mem.splitScalar",
        "std.mem.tokenizeScalar",
        "std.mem.copyForwards",
        "std.mem.Allocator.alloc",
        "std.mem.Allocator.free",
        "std.mem.Allocator.create",
        "std.mem.Allocator.destroy",
        "std.mem.Allocator.dupe",
        "std.testing.expect",
        "std.testing.expectEqual",
        "std.testing.expectEqualStrings",
    }
    if fqn in core_fqns or (".ArrayList" in fqn and name in {"init", "append", "appendSlice", "deinit"}):
        return PARTS[0]

    if any(key in path for key in ("std.mem.", "std.mem", "std.array", "hash_map", "array_hash_map", "std.heap")):
        return PARTS[1]
    if any(key in path for key in ("std.fs", "std.io", "std.io.", "std.Io".lower(), "std.posix")):
        return PARTS[2]
    if any(key in path for key in ("std.fmt", "std.json", "std.unicode", "std.ascii", "std.base", "std.crypto.encoding")):
        return PARTS[3]
    if any(key in path for key in ("std.math", "std.sort", "std.hash", "std.random", "std.time", "std.rand")):
        return PARTS[4]
    if any(key in path for key in ("std.build", "std.process", "std.os", "std.target", "std.start", "std.thread")):
        return PARTS[5]
    return PARTS[6]


def part_deck(parent_deck: str, part: Part) -> str:
    return f"{parent_deck}::{part.deck_suffix}"
