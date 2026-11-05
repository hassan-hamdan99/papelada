"""Command line: `boleto-br <code>` inspects one code; with no arguments, finds slips in stdin.

    boleto-br 34191.09008 61207.727308 71140.050007 4 16460000125000
    pdftotext fatura.pdf - | boleto-br

Prints JSON. Exit code 0 when the code is valid (or at least one slip was found), 1 otherwise.
"""
import json
import sys

from ._inspect import find_slips, inspect


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args:
        info = inspect(" ".join(args))
        result, ok = info.to_dict(), info.valid
    else:
        slips = find_slips(sys.stdin.read())
        result, ok = [s.to_dict() for s in slips], bool(slips)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
