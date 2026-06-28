from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re


FIELDS = [
    "uid",
    "zig_version",
    "module",
    "fqn",
    "kind",
    "signature",
    "definition",
    "front",
    "back",
    "example",
    "source_path",
    "source_line",
    "tags",
]


@dataclass(frozen=True)
class ZigEnv:
    zig_exe: str
    std_dir: Path
    version: str


@dataclass(frozen=True)
class Note:
    uid: str
    zig_version: str
    module: str
    fqn: str
    kind: str
    signature: str
    definition: str
    front: str
    back: str
    example: str
    source_path: str
    source_line: int
    tags: tuple[str, ...]

    def fields(self) -> dict[str, str]:
        return {
            "uid": self.uid,
            "zig_version": self.zig_version,
            "module": self.module,
            "fqn": self.fqn,
            "kind": self.kind,
            "signature": highlight_zig(self.signature),
            "definition": self.definition,
            "front": self.front,
            "back": self.back,
            "example": highlight_zig(self.example),
            "source_path": self.source_path,
            "source_line": str(self.source_line),
            "tags": _tag_chips(self.tags),
        }


def _tag_chips(tags: tuple[str, ...]) -> str:
    chips = []
    for tag in tags:
        cls = "tag"
        if tag.startswith("std::"):
            cls += " tag-module"
        elif tag.startswith("zig-"):
            cls += " tag-version"
        elif tag in {"generic", "deprecated", "needs_docs", "call_shape"}:
            cls += f" tag-{tag.replace('_', '-')}"
        else:
            cls += " tag-neutral"
        chips.append(f'<span class="{cls}">{escape(tag)}</span>')
    return "".join(chips)


_KEYWORDS = {
    "addrspace",
    "align",
    "allowzero",
    "and",
    "anyframe",
    "anytype",
    "asm",
    "async",
    "await",
    "break",
    "callconv",
    "catch",
    "comptime",
    "const",
    "continue",
    "defer",
    "else",
    "enum",
    "errdefer",
    "error",
    "export",
    "extern",
    "fn",
    "for",
    "if",
    "inline",
    "noalias",
    "nosuspend",
    "opaque",
    "or",
    "orelse",
    "packed",
    "pub",
    "resume",
    "return",
    "struct",
    "suspend",
    "switch",
    "test",
    "threadlocal",
    "try",
    "union",
    "unreachable",
    "usingnamespace",
    "var",
    "volatile",
    "while",
}

_TYPES = {
    "bool",
    "void",
    "type",
    "usize",
    "isize",
    "u8",
    "u16",
    "u32",
    "u64",
    "u128",
    "i8",
    "i16",
    "i32",
    "i64",
    "i128",
    "f16",
    "f32",
    "f64",
    "f80",
    "f128",
    "anyopaque",
}

_TOKEN_RE = re.compile(
    r"(?P<comment>//[^\n]*)"
    r"|(?P<string>\"(?:\\.|[^\"])*\"|'(?:\\.|[^'])*')"
    r"|(?P<builtin>@[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<number>\b\d+(?:\.\d+)?\b)"
    r"|(?P<ident>\b[A-Za-z_][A-Za-z0-9_]*\b)"
)


def highlight_zig(code: str) -> str:
    out: list[str] = []
    pos = 0
    for match in _TOKEN_RE.finditer(code):
        out.append(escape(code[pos : match.start()]))
        text = escape(match.group(0))
        if match.lastgroup == "ident":
            if text in _KEYWORDS:
                cls = "tok-kw"
            elif text in _TYPES or text[:1].isupper():
                cls = "tok-type"
            else:
                out.append(text)
                pos = match.end()
                continue
        else:
            cls = {
                "comment": "tok-comment",
                "string": "tok-string",
                "builtin": "tok-builtin",
                "number": "tok-number",
            }[match.lastgroup or ""]
        out.append(f'<span class="{cls}">{text}</span>')
        pos = match.end()
    out.append(escape(code[pos:]))
    return "".join(out)
