#!/usr/bin/env python3
"""Bump and verify release versions using bump-release.manifest.json."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from collections.abc import Callable

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "bump-release.manifest.json"


def read_makefile_base_version(makefile: str, **_: object) -> str:
    matches = re.findall(
        r"^BASE_VERSION[ \t]*\?=[ \t]*([^ \t\r\n#]+)[ \t]*(?:#.*)?$",
        makefile,
        re.MULTILINE,
    )
    if len(matches) != 1:
        sys.exit("Could not find BASE_VERSION in Makefile")
    return matches[0]


def extract_chart_app_version(text: str, *, context_path: str = "", **__: object) -> str:
    for line in text.splitlines():
        if line.startswith("appVersion:"):
            rest = line[len("appVersion:") :].strip()
            return rest.strip('"').strip("'")
    context = f" ({context_path})" if context_path else ""
    sys.exit(f"Could not find appVersion in Chart.yaml{context}")


def extract_release_image_tag_anchor(text: str, *, context_path: str = "", **__: object) -> str:
    match = re.search(r'^\s+tag: &releaseImageTag "([^"]+)"', text, flags=re.MULTILINE)
    if match is None:
        context = f" ({context_path})" if context_path else ""
        sys.exit('Could not find tag: &releaseImageTag "..." in Helm values' + context)
    return match.group(1)


def extract_bootstrap_image_tag(text: str, *, context_path: str = "", **__: object) -> str:
    match = re.search(r"^(\s+)imageTag:\s*\"([^\"]+)\"", text, flags=re.MULTILINE)
    if match is None:
        context = f" ({context_path})" if context_path else ""
        sys.exit(f"Could not find bootstrap imageTag in {context}")
    return match.group(2)


EXTRACTORS: dict[str, Callable[..., str]] = {
    "makefile_base_version": read_makefile_base_version,
    "chart_app_version": extract_chart_app_version,
    "release_image_tag_anchor": extract_release_image_tag_anchor,
    "bootstrap_image_tag": extract_bootstrap_image_tag,
}


def read_manifest_file(relative_path: str, *, git_ref: str | None, repo_root: pathlib.Path) -> str:
    if git_ref is not None:
        completed = subprocess.run(
            ["git", "show", f"{git_ref}:{relative_path}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout

    path = repo_root / relative_path
    if not path.is_file():
        sys.exit(f"Manifest path does not exist or is not a file: {relative_path}")
    return path.read_text(encoding="utf-8")


def load_manifest(path: pathlib.Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Manifest not found: {path}")
    except json.JSONDecodeError as error:
        sys.exit(f"Invalid JSON in {path}: {error}")

    if not isinstance(data, dict):
        sys.exit("Manifest root must be a JSON object")
    replacements = data.get("replacements")
    if not isinstance(replacements, list) or not replacements:
        sys.exit('Manifest must contain a non-empty "replacements" array')

    for index, item in enumerate(replacements):
        if not isinstance(item, dict):
            sys.exit(f"replacements[{index}] must be an object")
        rule = item.get("rule")
        if rule not in EXTRACTORS:
            sys.exit(f"Unknown rule {rule!r}; known: {', '.join(sorted(EXTRACTORS))}")
        paths = item.get("paths")
        if not isinstance(paths, list) or not paths:
            sys.exit(f'replacements[{index}] must have a non-empty "paths" array')
        for path_index, relative_path in enumerate(paths):
            if not isinstance(relative_path, str) or not relative_path.strip():
                sys.exit(
                    f"replacements[{index}].paths[{path_index}] " "must be a non-empty string"
                )
    return data


def manifest_relative_paths(data: dict) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in data["replacements"]:
        for relative_path in item["paths"]:
            if relative_path not in seen:
                seen.add(relative_path)
                paths.append(relative_path)
    return paths


def verify_manifest_alignment(
    manifest_path: pathlib.Path, *, git_ref: str | None, repo_root: pathlib.Path
) -> str:
    data = load_manifest(manifest_path)
    makefile = read_manifest_file("Makefile", git_ref=git_ref, repo_root=repo_root)
    base_version = read_makefile_base_version(makefile)
    errors: list[str] = []

    for item in data["replacements"]:
        extractor = EXTRACTORS[item["rule"]]
        for relative_path in item["paths"]:
            text = read_manifest_file(relative_path, git_ref=git_ref, repo_root=repo_root)
            found = extractor(text, context_path=relative_path)
            if found != base_version:
                errors.append(
                    f"{relative_path} ({item['rule']}): found {found!r}, "
                    f"expected {base_version!r} (Makefile BASE_VERSION)"
                )

    if errors:
        reference = f" (git ref {git_ref})" if git_ref else ""
        print(
            f"::error::Release version mismatch across manifest{reference}",
            file=sys.stderr,
        )
        for error in errors:
            print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)

    print(f"version={base_version}")
    print(f"Verified release manifest alignment ({base_version})")
    return base_version


def replace_makefile_base_version(text: str, new_version: str, **_: object) -> str:
    def replacement(match: re.Match[str]) -> str:
        current_version = match.group(2)
        version = new_version
        if current_version.startswith("v") and not version.startswith("v"):
            version = f"v{version}"
        elif not current_version.startswith("v") and version.startswith("v"):
            version = version[1:]
        return f"{match.group(1)}{version}"

    updated, count = re.subn(
        r"^(BASE_VERSION[ \t]*\?=[ \t]*)([^ \t\r\n#]+)",
        replacement,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        sys.exit("Failed to replace BASE_VERSION in Makefile")
    return updated


def replace_chart_app_version(text: str, new_version: str, **_: object) -> str:
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("appVersion:"):
            rest = line[len("appVersion:") :].strip()
            if rest.startswith('"') and rest.endswith('"'):
                lines[index] = f'appVersion: "{new_version}"\n'
            elif rest.startswith("'") and rest.endswith("'"):
                lines[index] = f"appVersion: '{new_version}'\n"
            else:
                lines[index] = f"appVersion: {new_version}\n"
            return "".join(lines)
    sys.exit("Could not find appVersion in helm/Chart.yaml")


def replace_release_image_tag_anchor(text: str, new_version: str, **_: object) -> str:
    updated, count = re.subn(
        r'(^\s+tag: &releaseImageTag )"[^"]+"',
        rf'\g<1>"{new_version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        sys.exit('Could not find exactly one line matching: tag: &releaseImageTag "..."')
    return updated


def replace_bootstrap_image_tag(
    text: str,
    new_version: str,
    *,
    context_path: pathlib.Path | None = None,
    **_: object,
) -> str:
    updated, count = re.subn(
        r"^(\s+imageTag:\s*)\"[^\"]+\"",
        rf'\g<1>"{new_version}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    display = context_path if context_path is not None else "manifest path"
    if count != 1:
        sys.exit(f"Could not find bootstrap imageTag in {display}")
    return updated


REPLACEMENTS: dict[str, Callable[..., str]] = {
    "makefile_base_version": replace_makefile_base_version,
    "chart_app_version": replace_chart_app_version,
    "release_image_tag_anchor": replace_release_image_tag_anchor,
    "bootstrap_image_tag": replace_bootstrap_image_tag,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=pathlib.Path,
        default=DEFAULT_MANIFEST,
        help=f"JSON manifest of files and rules (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--print-manifest-paths",
        action="store_true",
        help="Print manifest-relative paths, one per line",
    )
    parser.add_argument(
        "-0",
        "--null",
        dest="paths_nul_terminated",
        action="store_true",
        help="With --print-manifest-paths: separate paths with ASCII NUL",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify every manifest path matches Makefile BASE_VERSION",
    )
    parser.add_argument(
        "--git-ref",
        default=None,
        help="With --verify: read files from this Git ref",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned changes without writing files",
    )
    parser.add_argument(
        "version",
        nargs="?",
        default=None,
        help="New release version; required unless --verify is used",
    )
    args = parser.parse_args()

    manifest_path = args.manifest
    if not manifest_path.is_absolute():
        manifest_path = (ROOT / manifest_path).resolve()

    if args.paths_nul_terminated and not args.print_manifest_paths:
        parser.error("-0/--null is only valid with --print-manifest-paths")
    if args.print_manifest_paths:
        if args.verify:
            parser.error("--print-manifest-paths cannot be combined with --verify")
        if args.git_ref:
            parser.error("--print-manifest-paths cannot be combined with --git-ref")
        if args.version:
            parser.error("version must not be given with --print-manifest-paths")
        paths = manifest_relative_paths(load_manifest(manifest_path))
        if args.paths_nul_terminated:
            if paths:
                sys.stdout.buffer.write("\0".join(paths).encode("utf-8"))
        else:
            for relative_path in paths:
                print(relative_path)
        return

    if args.git_ref and not args.verify:
        parser.error("--git-ref is only valid with --verify")
    if args.verify:
        if args.version:
            parser.error("version is not valid with --verify")
        if args.dry_run:
            parser.error("--dry-run is not valid with --verify")
        verify_manifest_alignment(manifest_path, git_ref=args.git_ref, repo_root=ROOT)
        return

    if args.version is None:
        parser.error("version is required unless --verify is used")
    new_version = args.version.strip().strip('"').strip("'")
    if re.fullmatch(r"v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", new_version) is None:
        sys.exit(
            "Version must be semver (MAJOR.MINOR.PATCH), optionally prefixed with v: "
            f"{new_version}"
        )

    data = load_manifest(manifest_path)
    updates: list[tuple[pathlib.Path, str]] = []
    for item in data["replacements"]:
        replacement = REPLACEMENTS[item["rule"]]
        for relative_path in item["paths"]:
            path = ROOT / relative_path
            if not path.is_file():
                sys.exit(f"Manifest path does not exist or is not a file: {relative_path}")
            text = path.read_text(encoding="utf-8")
            updated = replacement(text, new_version, context_path=path)
            updates.append((path, updated))

    changed = [
        (path, updated) for path, updated in updates if updated != path.read_text(encoding="utf-8")
    ]
    if args.dry_run:
        for path, _ in changed:
            print(f"Would update {path.relative_to(ROOT)}")
        if not changed:
            print("No changes needed")
        return

    for path, updated in changed:
        path.write_text(updated, encoding="utf-8")
        print(f"Updated {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
