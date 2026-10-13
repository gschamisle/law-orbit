"""Attach procedural citations and checked reading notes; preserve existing data."""
import argparse
import json
from pathlib import Path
from scripts.build_integrity_links_site import build as build_selected


def build(base, destination):
    return build_selected(base, destination, hub='remedy')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--dest', type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(build(a.base, a.dest), ensure_ascii=False, indent=2))
