"""Command line, JSON out.

    papelada 34191.09008 61207.727308 71140.050007 4 16460000125000   # inspect a slip code
    papelada nota.xml                                                 # read an NF-e / NFC-e XML
    pdftotext fatura.pdf - | papelada                                 # find every slip in a text

Exit code 0 when the input is valid (or at least one slip was found), 1 otherwise.
"""
import json
import os
import sys

from . import nfe_xml
from ._inspect import find_slips, inspect


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(args) == 1 and args[0].lower().endswith(".xml") and os.path.isfile(args[0]):
        try:
            doc = nfe_xml.parse(args[0])
        except nfe_xml.InvalidNFeXML as exc:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
            return 1
        result, ok = doc.to_dict(), doc.valid
    elif args:
        info = inspect(" ".join(args))
        result, ok = info.to_dict(), info.valid
    else:
        slips = find_slips(sys.stdin.read())
        result, ok = [s.to_dict() for s in slips], bool(slips)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
