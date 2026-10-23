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
    python3 scripts/coverage_report.py --badges out  # also write shields.io badges
"""
import argparse
import json
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


def write_badge(badges, name, percent):
    """A shields.io endpoint file, badges/<name>-coverage.json, with the line
    percentage rounded down."""
    color = ("brightgreen" if percent >= 90 else "green" if percent >= 80
             else "yellow" if percent >= 60 else "red")
    with open(os.path.join(badges, f"{name}-coverage.json"), "w") as f:
        json.dump({"schemaVersion": 1, "label": f"{name} coverage",
                   "message": f"{int(percent)}%", "color": color}, f)


def server(python, work, badges):
    if not os.path.exists(python):
        print(f"no Python at {python}: make the server's venv (CONTRIBUTING.md) or pass --python")
        return 1
    summary = os.path.join(work, "server.json")
    failed = subprocess.call(
        [python, "-m", "pytest", "-q", "--cov=epd_server", "--cov-branch",
         "--cov-report=term-missing:skip-covered", f"--cov-report=json:{summary}"],
        cwd=SERVER)
    if badges and not failed:
        with open(summary) as f:
            totals = json.load(f)["totals"]
        write_badge(badges, "server", 100 * totals["covered_lines"] / totals["num_statements"])
    return failed


def host_environments(ini_text):
    return re.findall(r"^\[env:(native[^\]]*)\]", ini_text, re.M)


def firmware(work, badges):
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
    summary = os.path.join(work, "firmware.json")
    # gcovr reads --filter from the folder it runs in.
    failed |= subprocess.call(report + ["--txt-summary", "--json-summary", summary], cwd=FIRMWARE)
    if badges and not failed:
        with open(summary) as f:
            write_badge(badges, "firmware", json.load(f)["line_percent"])
    return failed


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--firmware", action="store_true")
    parser.add_argument("--python", default=os.path.join(SERVER, ".venv", "bin", "python"),
                        help="the Python that runs the server's tests")
    parser.add_argument("--badges", metavar="DIR",
                        help="also write a shields.io badge file for each figure into DIR")
    args = parser.parse_args()
    both = not (args.server or args.firmware)
    if args.badges:
        args.badges = os.path.abspath(args.badges)
        os.makedirs(args.badges, exist_ok=True)

    failed = 0
    with tempfile.TemporaryDirectory() as work:
        if args.server or both:
            failed |= server(args.python, work, args.badges)
        if args.firmware or both:
            failed |= firmware(work, args.badges)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
