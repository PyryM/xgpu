import argparse
import subprocess
from typing import Tuple

TESTLIST = ["triangle", "cubes"]


def runtest(name: str, snapshotdir: str, emit: bool, thresh: float) -> Tuple[bool, str]:
    args = [
        "python",
        f"test_{name}.py",
        "--snapshots",
        snapshotdir,
        "--threshold",
        str(thresh),
    ]
    if emit:
        args.append("--emit")
    res = subprocess.run(args)
    return res.returncode == 0, f"code: {res.returncode}"


def runtests(snapshotdir: str, emit: bool, thresh: float) -> bool:
    pass_count = 0
    fail_count = 0
    skip_count = 0
    for name in TESTLIST:
        passed, msg = runtest(name, snapshotdir, emit, thresh)
        if passed:
            pass_count += 1
            print("[PASS]", name)
        else:
            fail_count += 1
            print("[FAIL]", name, msg)
    print("-------------------")
    if emit:
        print(f"Emitted snapshots for {pass_count} tests.")
    else:
        print(f"{pass_count} passed, {fail_count} failed, {skip_count} skipped.")
    return fail_count == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run test harness.")
    parser.add_argument(
        "--snapshots", type=str, help="Snapshot directory", default="snapshots"
    )
    parser.add_argument("--emit", help="Emit (write) snapshot", action="store_true")
    parser.add_argument(
        "--threshold",
        type=float,
        help="Difference threshold (fraction) to fail",
        default=0.05,
    )
    args = parser.parse_args()
    if not runtests(args.snapshots, args.emit, args.threshold):
        raise RuntimeError("Tests failed.")
