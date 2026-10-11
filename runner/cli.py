import argparse
from pathlib import Path
import sys
from .engine import Session


def main(argv=None):
    p = argparse.ArgumentParser(description="MiSTer-BDSM: reproducible RTL evidence; hardware testing remains necessary")
    p.add_argument("command", choices=["test", "regression", "mutate", "build"])
    p.add_argument("core", type=Path)
    checkout_adapter = Path(__file__).resolve().parents[1] / "adapters/cinematronics/adapter.json"
    installed_adapter = Path(sys.prefix) / "share/mister-bdsm/adapters/cinematronics/adapter.json"
    p.add_argument("--adapter", type=Path, default=checkout_adapter if checkout_adapter.is_file() else installed_adapter)
    p.add_argument("--suite", choices=["smoke", "lint", "audio", "regression", "game", "all"], default="smoke")
    p.add_argument("--check", help="Exact stable check ID")
    p.add_argument("--output", type=Path, default=Path.home() / ".local/state/mister-bdsm/results")
    p.add_argument("--rom-dir", type=Path, help="Private directory of user-supplied validated ZIP files")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--repeats", type=int, default=2)
    p.add_argument("--profile", choices=["candidate", "diagnostic"], default="candidate")
    args = p.parse_args(argv)
    if sys.platform != "linux":
        p.error("Run in Linux/WSL; use the supplied Windows launcher")
    if not 1 <= args.seed <= 2147483647 or not 2 <= args.repeats <= 10:
        p.error("Seed must be 1..2147483647; mutation repeats must be 2..10")
    session = None
    try:
        session = Session(args.core, args.adapter, args.output.resolve(), args.seed)
        if args.command == "mutate":
            return session.mutate(args.repeats)
        if args.command == "build":
            return session.build(args.profile == "diagnostic", args.rom_dir.resolve() if args.rom_dir else None)
        checks = session.adapter["checks"]
        if args.check:
            checks = [check for check in checks if check["id"] == args.check]
        elif args.command != "regression" and args.suite != "all":
            checks = [check for check in checks if check["suite"] == args.suite]
        if not checks:
            raise ValueError("No checks selected; refusing an empty successful run")
        results = session.run(checks, args.rom_dir.resolve() if args.rom_dir else None)
        return session.finalize(results, "development")
    except (ValueError, OSError, KeyError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        if session is not None:
            return session.finalize([{"id": "framework.execution", "status": "ERROR", "required": True, "reason": str(exc)}], "error")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
