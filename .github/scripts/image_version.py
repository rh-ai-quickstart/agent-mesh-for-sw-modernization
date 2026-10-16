"""Read or bump the committed Makefile image version without loading .env."""

import argparse
import re
from pathlib import Path

VERSION = re.compile(r"v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
ASSIGNMENT = re.compile(
    r"^BASE_VERSION[ \t]*\?=[ \t]*(?P<version>[^ \t\r\n#]+)[ \t]*(?:#.*)?$",
    re.MULTILINE,
)


def parse_version(value):
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError("Version must use vMAJOR.MINOR.PATCH without leading zeros, e.g. v0.1.7")
    return tuple(int(part) for part in match.groups())


def image_version(makefile, requested=None):
    content = makefile.read_text()
    matches = list(ASSIGNMENT.finditer(content))
    if len(matches) != 1:
        raise ValueError("Makefile must contain exactly one BASE_VERSION ?= assignment")
    match = matches[0]
    current = match.group("version")
    parts = parse_version(current)
    if requested is None:
        return current

    requested = requested.strip()
    if not requested:
        requested = f"v{parts[0]}.{parts[1]}.{parts[2] + 1}"
    if parse_version(requested) <= parts:
        raise ValueError(f"New version must be greater than {current}")
    start, end = match.span("version")
    makefile.write_text(content[:start] + requested + content[end:])
    return requested


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--makefile", type=Path, default=Path("Makefile"))
    parser.add_argument(
        "--bump",
        nargs="?",
        const="",
        help="Update BASE_VERSION to this version, or increment the patch if omitted",
    )
    args = parser.parse_args()
    try:
        print(image_version(args.makefile, args.bump))
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
