from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .models import Note
from .partition import part_for


_PUB_FN_RE = re.compile(r"\bpub\s+(?:inline\s+|extern\s+|export\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\b")
_PUB_CONTAINER_RE = re.compile(
    r"\bpub\s+const\s+([A-Za-z_][A-Za-z0-9_]*)\s*=.*\b(struct|union|enum|opaque)\b"
)
_TEST_RE = re.compile(r"^\s*test\b")
_COMMENT_PREFIX_RE = re.compile(r"^\s*///\s?")


@dataclass(frozen=True)
class _Container:
    name: str
    depth: int


def extract_notes(std_dir: Path, zig_version: str, module_filter: str | None = None) -> list[Note]:
    notes: list[Note] = []
    for path in sorted(std_dir.rglob("*.zig")):
        module = module_name(std_dir, path)
        if module_filter and not (module == module_filter or module.startswith(module_filter + ".")):
            continue
        notes.extend(extract_file(path, std_dir, zig_version, module))
    dedup: dict[str, Note] = {}
    for note in notes:
        dedup.setdefault(note.uid, note)
    return sorted(dedup.values(), key=lambda n: n.fqn)


def module_name(std_dir: Path, path: Path) -> str:
    rel = path.relative_to(std_dir).with_suffix("")
    parts = list(rel.parts)
    if parts == ["std"]:
        return "std"
    if parts[-1] == "root":
        parts = parts[:-1]
    return ".".join(["std", *parts])


def extract_file(path: Path, std_dir: Path, zig_version: str, module: str) -> list[Note]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    line_starts = _line_starts(text)
    masked = _mask_comments_and_strings(text)
    notes: list[Note] = []
    containers: list[_Container] = []

    for match in _iter_interesting(masked):
        line_no = _line_number(line_starts, match.start())
        prefix = masked[match.start() : match.end()]
        depth = _brace_depth(masked[: match.start()])
        containers = [c for c in containers if c.depth < depth]

        container_match = _PUB_CONTAINER_RE.search(prefix)
        if container_match:
            name = container_match.group(1)
            containers.append(_Container(name=name, depth=depth))
            continue

        fn_match = _PUB_FN_RE.search(prefix)
        if not fn_match or _inside_test(lines, line_no):
            continue

        name = fn_match.group(1)
        signature = _extract_signature(text, match.start())
        if not signature:
            continue
        docs = _doc_comment_before(lines, line_no)
        rel_source = str(path.relative_to(std_dir.parent)).replace("\\", "/")
        fqn_parts = [module, *[c.name for c in containers], name]
        fqn = ".".join(p for p in fqn_parts if p)
        definition = _definition_from_docs(docs) or _definition_from_signature(fqn, signature, rel_source)
        example = _example_for(fqn, name, signature, docs, lines, line_no)
        tags = _tags(module, fqn, zig_version, signature, docs, example)
        front = f"{fqn}\n{signature}"
        back_parts = [
            definition or "No short documentation found.",
            "",
            "Example:",
            example or "No compact example found.",
            "",
            f"Source: {rel_source}:{line_no}",
            f"Zig: {zig_version}",
        ]
        uid = _uid(zig_version, fqn, signature)
        notes.append(
            Note(
                uid=uid,
                zig_version=zig_version,
                module=module,
                fqn=fqn,
                kind="function",
                signature=signature,
                definition=definition,
                front=_clip(front, 500),
                back=_clip("\n".join(back_parts), 1200),
                example=example,
                source_path=rel_source,
                source_line=line_no,
                tags=tags,
            )
        )
    return notes


def _iter_interesting(masked: str):
    pattern = re.compile(
        r"\bpub\s+(?:inline\s+|extern\s+|export\s+)?fn\s+[A-Za-z_][A-Za-z0-9_]*\b"
        r"|\bpub\s+const\s+[A-Za-z_][A-Za-z0-9_]*\s*=.*?\b(?:struct|union|enum|opaque)\b",
        re.S,
    )
    return pattern.finditer(masked)


def _line_starts(text: str) -> list[int]:
    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)
    return starts


def _line_number(starts: list[int], pos: int) -> int:
    lo, hi = 0, len(starts)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if starts[mid] <= pos:
            lo = mid
        else:
            hi = mid
    return lo + 1


def _mask_comments_and_strings(text: str) -> str:
    out = list(text)
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("///", i):
            i = text.find("\n", i)
            if i == -1:
                break
        elif text.startswith("//", i):
            j = text.find("\n", i)
            if j == -1:
                j = n
            for k in range(i, j):
                out[k] = " "
            i = j
        elif text.startswith("\\\\", i):
            i = text.find("\n", i)
            if i == -1:
                break
        elif text[i] in {'"', "'"}:
            quote = text[i]
            i += 1
            while i < n:
                out[i] = " "
                if text[i] == "\\":
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
        else:
            i += 1
    return "".join(out)


def _brace_depth(masked_prefix: str) -> int:
    return masked_prefix.count("{") - masked_prefix.count("}")


def _extract_signature(text: str, start: int) -> str:
    depth = 0
    end = start
    while end < len(text):
        ch = text[end]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "{" and depth == 0:
            return _clean_signature(text[start:end])
        elif ch == ";" and depth == 0:
            return _clean_signature(text[start:end])
        end += 1
    return ""


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clean_signature(value: str) -> str:
    value = re.sub(r"///[^\n\r]*", "", value)
    value = re.sub(r"//[^\n\r]*", "", value)
    return _pretty_signature(_collapse_ws(value.strip()))


def _pretty_signature(signature: str) -> str:
    if len(signature) <= 92:
        return signature
    start = signature.find("(")
    if start == -1:
        return signature
    depth = 0
    end = -1
    for i in range(start, len(signature)):
        if signature[i] == "(":
            depth += 1
        elif signature[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return signature
    head = signature[:start]
    params = [p.strip() for p in _split_top_level(signature[start + 1 : end]) if p.strip()]
    tail = signature[end + 1 :].strip()
    if not params:
        return signature
    body = ",\n    ".join(params)
    return f"{head}(\n    {body},\n) {tail}".rstrip()


def _doc_comment_before(lines: list[str], line_no: int) -> list[str]:
    docs: list[str] = []
    i = line_no - 2
    while i >= 0:
        line = lines[i]
        if _COMMENT_PREFIX_RE.match(line):
            docs.append(_COMMENT_PREFIX_RE.sub("", line).rstrip())
            i -= 1
            continue
        if line.strip() == "":
            i -= 1
            continue
        break
    docs.reverse()
    return docs


def _definition_from_docs(docs: list[str]) -> str:
    plain = " ".join(line.strip() for line in docs if line.strip() and not line.strip().startswith("```"))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return ""
    sentence = re.split(r"(?<=[.!?])\s+", plain, maxsplit=1)[0]
    return _clip(sentence, 260)


def _example_for(fqn: str, name: str, signature: str, docs: list[str], lines: list[str], line_no: int) -> str:
    manual = _manual_example(fqn, name)
    if manual:
        return manual
    block = _code_block_from_docs(docs)
    if block:
        return _clip_lines(block)
    nearby = _nearby_test(name, lines, line_no)
    if nearby:
        return _clip_lines(nearby)
    return _call_shape(fqn, signature)


def _manual_example(fqn: str, name: str) -> str:
    if fqn == "std.mem.Allocator.alignedAlloc":
        return """const allocator = std.heap.page_allocator;
const items = try allocator.alignedAlloc(u32, .@"16", 8);
defer allocator.free(items);

items[0] = 123;"""
    if fqn == "std.mem.Allocator.alloc":
        return """const allocator = std.heap.page_allocator;
const bytes = try allocator.alloc(u8, 64);
defer allocator.free(bytes);

@memset(bytes, 0);"""
    if fqn == "std.mem.Allocator.free":
        return """const allocator = std.heap.page_allocator;
const buf = try allocator.alloc(u8, 32);
defer allocator.free(buf);"""
    if fqn == "std.mem.Allocator.create":
        return """const allocator = std.heap.page_allocator;
const value = try allocator.create(u32);
defer allocator.destroy(value);

value.* = 42;"""
    if fqn == "std.mem.Allocator.destroy":
        return """const allocator = std.heap.page_allocator;
const value = try allocator.create(u32);
value.* = 42;
allocator.destroy(value);"""
    if fqn == "std.mem.Allocator.dupe":
        return """const allocator = std.heap.page_allocator;
const copy = try allocator.dupe(u8, "zig");
defer allocator.free(copy);"""
    if fqn == "std.mem.Allocator.dupeZ":
        return """const allocator = std.heap.page_allocator;
const c_string = try allocator.dupeZ(u8, "zig");
defer allocator.free(c_string);"""

    if fqn == "std.mem.eql":
        return """try std.testing.expect(std.mem.eql(u8, "zig", "zig"));
try std.testing.expect(!std.mem.eql(u8, "zig", "zag"));"""
    if fqn == "std.mem.startsWith":
        return """try std.testing.expect(std.mem.startsWith(u8, "zig std", "zig"));"""
    if fqn == "std.mem.endsWith":
        return """try std.testing.expect(std.mem.endsWith(u8, "main.zig", ".zig"));"""
    if fqn == "std.mem.indexOf":
        return """const pos = std.mem.indexOf(u8, "hello zig", "zig").?;
try std.testing.expectEqual(@as(usize, 6), pos);"""
    if fqn == "std.mem.splitScalar":
        return """var it = std.mem.splitScalar(u8, "a,b,c", ',');
try std.testing.expectEqualStrings("a", it.next().?);
try std.testing.expectEqualStrings("b", it.next().?);"""
    if fqn == "std.mem.tokenizeScalar":
        return """var it = std.mem.tokenizeScalar(u8, "a  b", ' ');
try std.testing.expectEqualStrings("a", it.next().?);
try std.testing.expectEqualStrings("b", it.next().?);"""
    if fqn == "std.mem.copyForwards":
        return """var dst: [3]u8 = undefined;
std.mem.copyForwards(u8, &dst, "zig");
try std.testing.expectEqualStrings("zig", &dst);"""

    if ".ArrayList" in fqn and name == "init":
        return """var list = std.ArrayList(u8).init(std.heap.page_allocator);
defer list.deinit();"""
    if ".ArrayList" in fqn and name == "append":
        return """var list = std.ArrayList(u8).init(std.heap.page_allocator);
defer list.deinit();

try list.append('z');
try std.testing.expectEqualStrings("z", list.items);"""
    if ".ArrayList" in fqn and name == "appendSlice":
        return """var list = std.ArrayList(u8).init(std.heap.page_allocator);
defer list.deinit();

try list.appendSlice("zig");
try std.testing.expectEqualStrings("zig", list.items);"""
    if ".ArrayList" in fqn and name == "deinit":
        return """var list = std.ArrayList(u8).init(std.heap.page_allocator);
defer list.deinit();

try list.append('z');"""
    if ".ArrayList" in fqn and name == "toOwnedSlice":
        return """var list = std.ArrayList(u8).init(std.heap.page_allocator);
try list.appendSlice("zig");

const owned = try list.toOwnedSlice();
defer std.heap.page_allocator.free(owned);"""
    return ""


def _code_block_from_docs(docs: list[str]) -> str:
    in_block = False
    buf: list[str] = []
    for line in docs:
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_block and buf:
                return "\n".join(buf).strip()
            in_block = not in_block
            continue
        if in_block:
            buf.append(line)
    return ""


def _nearby_test(name: str, lines: list[str], line_no: int) -> str:
    window = lines[line_no : min(len(lines), line_no + 180)]
    for idx, line in enumerate(window):
        if _TEST_RE.match(line) and name in line:
            return "\n".join(window[idx : min(idx + 20, len(window))]).strip()
    return ""


def _inside_test(lines: list[str], line_no: int) -> bool:
    start = max(0, line_no - 50)
    depth = 0
    in_test = False
    for line in lines[start : line_no - 1]:
        if _TEST_RE.match(line):
            in_test = True
            depth = 0
        if in_test:
            depth += line.count("{") - line.count("}")
            if depth <= 0 and "}" in line:
                in_test = False
    return in_test


def _tags(module: str, fqn: str, zig_version: str, signature: str, docs: list[str], example: str) -> tuple[str, ...]:
    tags = ["zig", f"zig-{zig_version}", "stdlib", module.replace(".", "::")]
    tags.append(part_for(module, fqn).tag)
    if "comptime" in signature:
        tags.append("generic")
    doc_text = "\n".join(docs).lower()
    if "deprecated" in doc_text:
        tags.append("deprecated")
    if not docs:
        tags.append("needs_docs")
    if "Call shape only" in example:
        tags.append("call_shape")
    return tuple(dict.fromkeys(tags))


def _definition_from_signature(fqn: str, signature: str, source: str) -> str:
    name = fqn.rsplit(".", 1)[-1]
    inferred = _infer_description(name, fqn, signature)
    if inferred:
        return inferred
    ret = _return_type(signature)
    if ret:
        return f"Public Zig stdlib API from `{source}`. Returns `{ret}`; read source for exact semantics."
    return f"Public Zig stdlib API from `{source}`. Read source for exact semantics."


def _infer_description(name: str, fqn: str, signature: str) -> str:
    lower = name.lower()
    owner = fqn.rsplit(".", 1)[0]
    ret = _return_type(signature)
    if lower in {"init", "initcapacity", "initbuffer"} or lower.startswith("init"):
        return f"Initialize `{owner}` state. Returns `{ret or 'initialized value'}`."
    if lower == "deinit":
        return f"Release resources owned by `{owner}`. Usually invalidates further use unless reinitialized."
    if lower.startswith("alloc") or "alloc" in lower:
        return f"Allocate memory/items through `{owner}`. Caller must follow matching ownership/free rules."
    if lower.startswith("free") or lower == "destroy":
        return f"Release memory/items previously owned by caller through `{owner}`."
    if lower.startswith("ensure"):
        return f"Ensure backing capacity/state is large enough before later operations."
    if lower.startswith("append"):
        return f"Append value(s) to `{owner}`, growing storage when needed."
    if lower.startswith("insert"):
        return f"Insert value(s) into `{owner}` at requested position."
    if lower.startswith("remove") or lower.startswith("pop"):
        return f"Remove value(s) from `{owner}` and return or discard them depending on return type."
    if lower.startswith("read"):
        return f"Read bytes/data from `{owner}` into caller-provided storage."
    if lower.startswith("write"):
        return f"Write bytes/data from caller storage into `{owner}`."
    if lower.startswith("parse"):
        return f"Parse input into Zig value/state. Returns `{ret or 'parsed result'}`."
    if lower.startswith("format") or lower.startswith("print"):
        return f"Format/write human-readable representation using provided writer/options."
    if lower.startswith("eql") or lower.startswith("equal"):
        return f"Compare values for equality and return `bool`."
    if lower.startswith("hash"):
        return f"Compute hash value for input/state."
    if lower.startswith("clone") or lower.startswith("dupe"):
        return f"Duplicate data; caller owns returned allocation when allocator is involved."
    if lower.startswith("is"):
        return f"Predicate helper returning whether `{owner}` satisfies `{name}` condition."
    return ""


def _call_shape(fqn: str, signature: str) -> str:
    params = _signature_params(signature)
    names = [p for p in params if p not in {"self"}]
    target = fqn
    if params and params[0] == "self":
        target = f"self.{fqn.rsplit('.', 1)[-1]}"
    args = ", ".join(_placeholder(name) for name in names)
    call = f"{target}({args})"
    prefix = "Call shape only; verify concrete types/values against source."
    if _return_type(signature) == "void":
        return f"{prefix}\n{call};"
    return f"{prefix}\nconst result = {call};"


def _signature_params(signature: str) -> list[str]:
    start = signature.find("(")
    if start == -1:
        return []
    depth = 0
    end = -1
    for i in range(start, len(signature)):
        if signature[i] == "(":
            depth += 1
        elif signature[i] == ")":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return []
    raw = signature[start + 1 : end]
    params = []
    for part in _split_top_level(raw):
        part = part.strip()
        if not part or part == "...":
            continue
        if ":" not in part:
            continue
        name = part.split(":", 1)[0].strip()
        if name in {"comptime", "noalias"}:
            pieces = part.split()
            if len(pieces) >= 2:
                name = pieces[1].split(":", 1)[0]
        name = name.lstrip("*").strip()
        if name:
            params.append(name)
    return params


def _split_top_level(raw: str) -> list[str]:
    items: list[str] = []
    start = 0
    paren = bracket = brace = 0
    for i, ch in enumerate(raw):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket -= 1
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace -= 1
        elif ch == "," and paren == 0 and bracket == 0 and brace == 0:
            items.append(raw[start:i])
            start = i + 1
    items.append(raw[start:])
    return items


def _placeholder(name: str) -> str:
    if name in {"T", "U", "E"}:
        return "u8"
    if name.startswith("comptime "):
        return name.split()[-1]
    return name


def _return_type(signature: str) -> str:
    start = signature.find("(")
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(signature)):
        if signature[i] == "(":
            depth += 1
        elif signature[i] == ")":
            depth -= 1
            if depth == 0:
                return signature[i + 1 :].strip()
    return ""


def _uid(zig_version: str, fqn: str, signature: str) -> str:
    digest = hashlib.sha1(_collapse_ws(signature).encode("utf-8")).hexdigest()[:12]
    return f"zig:{zig_version}:{fqn}:{digest}"


def _clip(value: str, max_chars: int) -> str:
    return value if len(value) <= max_chars else value[: max_chars - 1].rstrip() + "..."


def _clip_lines(value: str, max_lines: int = 20, max_chars: int = 900) -> str:
    lines = value.splitlines()[:max_lines]
    return _clip("\n".join(lines), max_chars)
