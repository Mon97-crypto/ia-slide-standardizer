#!/usr/bin/env python3
"""Build battlecard decks from the JSON cards in content/battlecards/.

    python3 build_battlecards.py                    # every card, into outputs/
    python3 build_battlecards.py --out decks        # choose the directory
    python3 build_battlecards.py oracle relex       # only matching cards

Each card is validated before it builds, so a brand voice problem or a missing
source shows up as a warning on the console rather than inside a deck a seller
takes into a meeting.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

from battlecards import service

CONTENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'content', 'battlecards')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('filters', nargs='*',
                        help='Substrings matched against the card filename.')
    parser.add_argument('--out', default='outputs', help='Output directory.')
    parser.add_argument('--content', default=CONTENT_DIR, help='Card directory.')
    args = parser.parse_args(argv)

    paths = sorted(glob.glob(os.path.join(args.content, '*.json')))
    if args.filters:
        needles = [needle.lower() for needle in args.filters]
        paths = [path for path in paths
                 if any(needle in os.path.basename(path).lower() for needle in needles)]
    if not paths:
        print('No cards matched. Looked in %s' % args.content)
        return 1

    failures = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            with open(path) as handle:
                payload = json.load(handle)
        except (OSError, ValueError) as exc:
            print('%-46s FAILED to read: %s' % (name, exc))
            failures += 1
            continue

        try:
            result = service.build(payload, args.out)
        except ValueError as exc:
            print('%-46s REJECTED: %s' % (name, exc))
            failures += 1
            continue

        compat = result['compatibility']
        print('%-46s %2d slides  google_slides=%s  %s'
              % (name, result['slide_count'],
                 'pass' if compat['ok'] else 'CHECK', result['filename']))
        for warning in result['warnings']:
            print('    warning [%s] %s' % (warning['rule'], warning['message']))
        for finding in compat['findings']:
            print('    compat  [%s] %s' % (finding['level'], finding['message']))

    print('\n%d card(s) built into %s, %d failure(s).'
          % (len(paths) - failures, args.out, failures))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
