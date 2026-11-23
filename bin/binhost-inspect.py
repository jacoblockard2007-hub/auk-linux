#!/usr/bin/env python3
"""Inspect a Portage binary-package index (a `Packages` file).

The official Gentoo binhost describes every build it ships in one flat
index: one stanza per .gpkg.tar, each carrying the exact USE set it was
built with.  A zero-compile distribution lives or dies on matching those
USE sets, so this tool answers the two questions that matter:

  * which build variants exist for a package, and
  * which packages lack the variant the chosen profile needs.

Usage:
    binhost-inspect.py [--index PATH] [PACKAGE ...]

With no packages given, prints a summary.  PACKAGE may be a category
(`kde-plasma`), a category/name (`kde-plasma/kwin`) or a full CPV.
"""

import argparse
import re
import sys
from collections import defaultdict


def stanzas(path):
    rec = {}
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                if rec:
                    yield rec
                    rec = {}
                continue
            # continuation lines are indented; ignore them for our purposes
            if line[0] == " " or ":" not in line:
                continue
            key, value = line.split(":", 1)
            rec[key] = value.strip()
    if rec:
        yield rec


def pkgname(cpv):
    """kde-plasma/kwin-6.7.6 -> kde-plasma/kwin"""
    cat, _, name = cpv.partition("/")
    return f"{cat}/{re.sub(r'-[0-9].*$', '', name)}"


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="Packages", help="path to a Packages index")
    ap.add_argument("packages", nargs="*", help="category, category/name or CPV")
    args = ap.parse_args()

    records = [r for r in stanzas(args.index) if r.get("CPV")]
    by_pkg = defaultdict(list)
    for r in records:
        by_pkg[pkgname(r["CPV"])].append(r)

    if not args.packages:
        n32 = sum(1 for r in records if "abi_x86_32" in r.get("USE", "").split())
        multi = sum(1 for v in by_pkg.values() if len(v) > 1)
        print(f"index          : {args.index}")
        print(f"build stanzas  : {len(records)}")
        print(f"packages       : {len(by_pkg)}")
        print(f"multi-variant  : {multi}")
        print(f"with abi_x86_32: {n32}")
        print()
        print("Query specific packages for their variant table, e.g.:")
        print("  binhost-inspect.py --index Packages kde-plasma/kwin x11-libs/libX11")
        return 0

    status = 0
    for query in args.packages:
        matches = [p for p in by_pkg if p == query or p.startswith(query)]
        if not matches:
            print(f"{query}: not in index")
            status = 1
            continue
        for p in sorted(matches):
            variants = sorted(by_pkg[p], key=lambda r: r.get("PATH", ""))
            has32 = any("abi_x86_32" in r.get("USE", "").split() for r in variants)
            print(f"\n{p}  ({len(variants)} variants, "
                  f"32-bit: {'yes' if has32 else 'NO'})")
            for r in variants:
                print(f"  {r.get('PATH', '?'):55s} {r.get('USE', '')}")
    return status


if __name__ == "__main__":
    sys.exit(main())
