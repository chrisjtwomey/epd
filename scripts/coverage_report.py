#!/usr/bin/env python3
"""Measure test coverage: the server's, and firmware/src's.

The server's comes from pytest-cov (the server's dev extras). The firmware's
comes from the host test environments, built again with --coverage in a
build folder of their own, so the normal test builds stay as they are; gcovr
reads the result, through gcov on Linux and through llvm-cov on a Mac, whose
compiler is clang. gcovr runs under the Python that runs this script.

    python3 scripts/coverage_report.py               # both
    python3 scripts/coverage_report.py --server      # one of them
    python3 scripts/coverage_report.py --firmware
"""
import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIRMWARE = os.path.join(ROOT, "firmware")
SERVER = os.path.join(ROOT, "server")

# Appended to each host test environment: line and branch counters, and no
# optimisation, so each line of source is a line in the report.
FLAGS_SCRIPT = """Import("env")
env.Append(CCFLAGS=["--coverage", "-O0"], LINKFLAGS=["--coverage"])
"""


def server(python):
    if not os.path.exists(python):
        print(f"no Python at {python}: make the server's venv (CONTRIBUTING.md) or pass --python")
        return 1
    return subprocess.call(
        [python, "-m", "pytest", "-q", "--cov=epd_server", "--cov-branch",
         "--cov-report=term-missing:skip-covered"],
        cwd=SERVER)


def host_environments(ini_text):
    return re.findall(r"^\[env:(native[^\]]*)\]", ini_text, re.M)


def firmware(work):
    with open(os.path.join(FIRMWARE, "platformio.ini")) as f:
        ini = f.read()
    flags = os.path.join(work, "coverage_flags.py")
    with open(flags, "w") as f:
        f.write(FLAGS_SCRIPT)
    build = os.path.join(work, "build")
    measured = re.sub(r"^(\[env:native[^\]]*\])$", rf"\1\nextra_scripts = pre:{flags}", ini,
                      flags=re.M)
    measured = measured.replace("[platformio]", f"[platformio]\nbuild_dir = {build}", 1)
    conf = os.path.join(work, "platformio.ini")
    with open(conf, "w") as f:
        f.write(measured)

    if not shutil.which("pio"):
        print("no pio on the PATH: install PlatformIO Core")
        return 1
    failed = 0
    for name in host_environments(ini):
        failed |= subprocess.call(["pio", "test", "-d", FIRMWARE, "-c", conf, "-e", name])

    gcov = "xcrun llvm-cov gcov" if platform.system() == "Darwin" else "gcov"
    report = [sys.executable, "-m", "gcovr", "--root", FIRMWARE, "--filter", "src/",
              "--gcov-executable", gcov, "--merge-mode-functions=separate", build]
    # gcovr reads --filter from the folder it runs in.
    failed |= subprocess.call(report + ["--txt-summary"], cwd=FIRMWARE)
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--firmware", action="store_true")
    parser.add_argument("--python", default=os.path.join(SERVER, ".venv", "bin", "python"),
                        help="the Python that runs the server's tests")
    args = parser.parse_args()
    both = not (args.server or args.firmware)

    failed = 0
    if args.server or both:
        failed |= server(args.python)
    if args.firmware or both:
        with tempfile.TemporaryDirectory() as work:
            failed |= firmware(work)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
