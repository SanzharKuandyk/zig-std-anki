from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from zig_std_anki.extractor import extract_notes


class ExtractorTest(unittest.TestCase):
    def test_extracts_top_level_and_nested_pub_fns(self) -> None:
        with TemporaryDirectory() as tmp:
            std = Path(tmp) / "std"
            std.mkdir()
            (std / "mem.zig").write_text(
                """
/// Compare slices.
pub fn eql(comptime T: type, a: []const T, b: []const T) bool {
    return a.len == b.len;
}

pub const Allocator = struct {
    /// Allocate items.
    pub fn alloc(self: @This(), comptime T: type, n: usize) ![]T {
        _ = self;
        _ = n;
    }
};
""",
                encoding="utf-8",
            )

            notes = extract_notes(std, "0.16.0")
            fqn = {note.fqn for note in notes}

        self.assertIn("std.mem.eql", fqn)
        self.assertIn("std.mem.Allocator.alloc", fqn)


if __name__ == "__main__":
    unittest.main()
