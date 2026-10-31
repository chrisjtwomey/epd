"""scripts/check_png_buffer.py: the check that PNGdec and the board agree on a size."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "check_png_buffer", Path(__file__).parents[2] / "scripts" / "check_png_buffer.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

PNG = "g++ -o .pio/build/dev/lib1/PNGdec/PNGdec.cpp.o -c {} x.cpp"
BOARD = "g++ -o .pio/build/dev/lib2/EpdBoardInkplate/InkplateBoard.cpp.o -c {} y.cpp"
SIZED = "-DPNG_MAX_BUFFERED_PIXELS=2640"


def problem(*lines):
    return check.problem(check.sizes("\n".join(lines)))


def test_one_size_in_both_passes():
    assert problem(PNG.format(SIZED), BOARD.format(SIZED)) is None


def test_a_library_with_none_fails():
    assert "disagree" in problem(PNG.format(""), BOARD.format(SIZED))


def test_two_sizes_fail():
    assert "disagree" in problem(PNG.format("-DPNG_MAX_BUFFERED_PIXELS=4000"), BOARD.format(SIZED))


def test_no_compile_line_fails():
    assert "no compile line for PNGdec" in problem(BOARD.format(SIZED))
