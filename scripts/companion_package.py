#!/usr/bin/env python3
"""Package and validate the skills-only companion plugin for OpenAI's Plugin Directory.

    python3 scripts/companion_package.py check [--final] [--online]
    python3 scripts/companion_package.py build [--out DIR]
    python3 scripts/companion_package.py validate-zip PATH.zip
    python3 scripts/companion_package.py sync
    python3 scripts/companion_package.py rename --slug NEW --display "New Name" [--dry-run]
    python3 scripts/companion_package.py rules
    python3 scripts/companion_package.py selftest

`check` validates the plugin directory as it lives in this repository, which is also what
our own Codex and Claude Code marketplaces serve. `build` writes the ZIP for the OpenAI
submission portal and then validates the ZIP itself. A ZIP is never trusted because the
tree it came from passed: the archive gets its own checks.

Every rule has an ID and the official page it comes from (`rules` prints them), and
docs/LISTING.md maps them clause by clause. House rules are stricter than the portal
wherever a stricter choice costs nothing. For example, the portal tolerates an empty
`hooks` object, but this package has no `hooks` key at all.

Standard library only. The script is a packaging tool. It is never shipped inside the
plugin, which must contain no executable code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Callable
from urllib.parse import urlsplit

# -- names live here and in the plugin manifest; `rename` rewrites both ------------------

PLUGIN_SLUG = "truthstone-practices"

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Layout:
    """Where everything is. A parameter, so `selftest` can run against a scratch copy."""

    root: Path
    slug: str = PLUGIN_SLUG

    @property
    def plugin_dir(self) -> Path:
        return self.root / "plugins" / self.slug

    @property
    def codex_manifest(self) -> Path:
        return self.plugin_dir / ".codex-plugin" / "plugin.json"

    @property
    def claude_manifest(self) -> Path:
        return self.plugin_dir / ".claude-plugin" / "plugin.json"

    @property
    def legal_dir(self) -> Path:
        return self.root / "docs" / "legal"

    @property
    def listing(self) -> Path:
        return self.root / "docs" / "LISTING.md"

    @property
    def script(self) -> Path:
        return self.root / "scripts" / "companion_package.py"

    @property
    def dist(self) -> Path:
        return self.root / "dist" / "companion"


# -- rules and their sources ----------------------------------------------------------

SRC_SUBMIT = "https://developers.openai.com/plugins/deploy/submission"
SRC_ERRORS = "https://developers.openai.com/plugins/deploy/submission-errors"
SRC_GUIDE = "https://developers.openai.com/plugins/plugin-guidelines"
SRC_BUILD = "https://developers.openai.com/plugins/build/plugins"
SRC_SKILLS = "https://developers.openai.com/plugins/build/skills"
SRC_DESKTOP = "https://developers.openai.com/plugins/deploy/desktop-only"
SRC_CLAUDE = "https://developers.openai.com/plugins/guides/submit-claude-plugin"
SRC_ANTHROPIC = "https://claude.com/docs/plugins/pre-submission-checklist"
SRC_HOUSE = "house rule (docs/LISTING.md)"

RULES: dict[str, tuple[str, str]] = {
    # Archive
    "ZIP-FORMAT": ("Readable, non-empty ZIP of at most 100 MB", SRC_ERRORS),
    "ZIP-LIMITS": ("At most 5,000 entries, 512 MiB extracted, 100 MiB per entry", SRC_ERRORS),
    "ZIP-PATH": ("Entry paths are relative, '/'-separated, no '..', empty segments, outer "
                 "whitespace or >20 segments, unique after case and Unicode normalization",
                 SRC_ERRORS),
    "ZIP-ENTRY-TYPE": ("Regular files and directories only (no symlinks), unencrypted, "
                       "stored or deflated", SRC_ERRORS),
    "ZIP-ROOT": ("Exactly one plugin root, at the archive root or in one top-level directory "
                 "with no sibling files", SRC_ERRORS),
    "ZIP-ONE-MANIFEST": ("The ZIP carries only .codex-plugin/plugin.json, so the portal never "
                         "has to choose or convert between manifests",
                         SRC_HOUSE + "; see claude_format_normalized in " + SRC_ERRORS),
    # What a public, skills-only package must not contain
    "NO-HOOKS": ("No lifecycle hooks: no hooks/ directory, hooks.json or 'hooks' key",
                 SRC_SUBMIT + " ; " + SRC_BUILD),
    "NO-APPS": ("No app references: no .app.json and no 'apps' key", SRC_ERRORS),
    "NO-MCP": ("No MCP configuration: no .mcp.json, mcp.json or 'mcpServers' key "
               "(local MCP is limited to approved partners)", SRC_ERRORS + " ; " + SRC_DESKTOP),
    "NO-SCREENSHOTS": ("Skills-only ZIPs must not include interface.screenshots", SRC_ERRORS),
    "NO-LOCAL-EXECUTOR": ("No requires_local_executor flag (it routes the plugin to the "
                          "desktop-only, partner-reviewed path)", SRC_DESKTOP),
    "NO-EXECUTABLES": ("No scripts, binaries or executable bits; the plugin runs nothing itself",
                       SRC_CLAUDE + " (local execution needs partner contact) ; " + SRC_HOUSE),
    "NO-CLAUDE-ONLY": ("No Claude-only components (commands/, agents/, settings, output styles, "
                       "LSP, marketplace.json) inside the plugin", SRC_CLAUDE),
    "NO-SECRETS": ("No credentials, tokens, private keys or .env files", SRC_SUBMIT + " ; " + SRC_GUIDE),
    "NO-REVIEW-CREDENTIALS": ("No test_credentials or reviewer_instructions in the package",
                              SRC_SUBMIT),
    "NO-OS-JUNK": ("No .DS_Store, Thumbs.db, desktop.ini or __MACOSX entries", SRC_ANTHROPIC),
    "NO-PLACEHOLDERS": ("No unfilled {{PLACEHOLDER}} text or example.com links", SRC_HOUSE),
    # Manifest
    "MANIFEST-FILE": (".codex-plugin/plugin.json is a regular UTF-8 file holding a JSON object",
                      SRC_ERRORS),
    "NAME": ("name: lowercase letters, digits and single hyphens, at most 64 characters",
             SRC_SUBMIT + " ; " + SRC_ERRORS),
    "VERSION": ("version: semantic version, at most 64 characters", SRC_ERRORS),
    "DESCRIPTION": ("description: required, supported text, at most 1,024 characters", SRC_ERRORS),
    "AUTHOR": ("author.name required (<=120); email <=320; url HTTPS (<=2,048), no credentials",
               SRC_ERRORS),
    "HOMEPAGE": ("homepage: HTTPS URL of at most 2,048 characters", SRC_ERRORS),
    "SKILLS-PATH": ("skills: './skills/' and the directory exists", SRC_ERRORS),
    "INTERFACE": ("interface: required object (Codex format)", SRC_SUBMIT),
    "DISPLAY-NAME": ("displayName: one line, at most 30 characters, no 'MCP'/'Plugin' suffix",
                     SRC_ERRORS + " ; " + SRC_GUIDE),
    "SHORT-DESCRIPTION": ("shortDescription: one line, at most 30 characters", SRC_ERRORS),
    "LONG-DESCRIPTION": ("longDescription: required, at most 4,000 characters", SRC_ERRORS),
    "DEVELOPER-NAME": ("developerName: one line, at most 80 characters", SRC_ERRORS),
    "CATEGORY": ("category: 'Developer Tools' (one of the portal's categories)",
                 SRC_ERRORS + " ; " + SRC_HOUSE),
    "CAPABILITIES": ("capabilities: at most 20, each one line and at most 120 characters",
                     SRC_ERRORS),
    "DEFAULT-PROMPT": ("defaultPrompt: at most 3, each one line, at most 128 characters, unique "
                       "after normalization, no @mentions", SRC_ERRORS),
    "LISTING-URLS": ("Website, support, privacy and terms URLs: HTTPS, host, no credentials, "
                     "at most 1,024 characters; privacy and support present",
                     SRC_ERRORS + " ; " + SRC_GUIDE + " (privacy policy, support contact)"),
    "LISTING-URLS-LOCAL": ("Listing URLs that point into this repository name files that exist",
                           SRC_HOUSE),
    "BRAND-COLOR": ("brandColor >= 2:1 contrast with white; brandColorDark >= 2:1 with #212121",
                    SRC_ERRORS),
    "ASSET-PATH": ("logo and composerIcon present; every asset path starts with './', stays "
                   "inside the plugin and names a regular file", SRC_ERRORS),
    "IMAGE": ("PNG/JPEG/WebP/SVG, at most 5 MiB, square, 48-4,096 px; SVG numeric unitless "
              "dimensions and no script, external or embedded content",
              SRC_ERRORS + " ; " + SRC_SUBMIT),
    "TEXT": ("Listing text uses supported characters (no control, format or separator "
             "characters)", SRC_ERRORS),
    "EXTENSIONS": ("extensions.com.openai holds only supported keys with valid values",
                   SRC_SUBMIT),
    "LISTING-COPY": ("No comparisons, superlatives, percentages, guarantees, pricing or "
                     "endorsement language in listing text", SRC_GUIDE),
    # Skills
    "SKILLS-PRESENT": ("At least one valid skill at skills/<name>/SKILL.md", SRC_ERRORS),
    "SKILL-LAYOUT": ("Each entry under skills/ is a real, non-hidden directory with SKILL.md "
                     "directly inside it", SRC_ERRORS),
    "SKILL-FRONTMATTER": ("SKILL.md starts with closed YAML front matter holding a mapping",
                          SRC_ERRORS),
    "SKILL-NAME": ("Skill name: lowercase-hyphenated, at most 64 characters, equal to its "
                   "directory, unique", SRC_ERRORS + " ; " + SRC_HOUSE),
    "SKILL-DESCRIPTION": ("Skill description: one text value, supported text, at most 1,024 "
                          "characters", SRC_ERRORS + " ; " + SRC_ANTHROPIC),
    "SKILL-BODY": ("Skill instructions are not empty", SRC_ERRORS),
    "SKILL-IDENTITY": ("'<plugin>:<skill>' is at most 64 characters", SRC_ERRORS),
    "SKILL-AGENT-METADATA": ("agents/openai.yaml: interface.display_name and short_description; "
                             "policy and dependencies limited to supported keys; no tool "
                             "dependencies", SRC_ERRORS),
    "SKILL-NO-COMMAND-INJECTION": ("No inline command execution syntax (!`...`) in skills",
                                   SRC_ANTHROPIC + " ; " + SRC_HOUSE),
    "SKILL-NO-RISKY-LITERALS": ("Skills describe risky commands in prose, never as runnable "
                                "literals", SRC_GUIDE + " (skills are scanned) ; " + SRC_HOUSE),
    "SKILL-NEUTRAL": ("Skill instructions use provider-neutral language", SRC_CLAUDE),
    "SKILL-PRIORITY": ("Each skill states that explicit user instructions take priority",
                       SRC_SKILLS),
    # Package
    "README": ("README.md with at least 40 words outside code blocks", SRC_ANTHROPIC),
    "LICENSE": ("LICENSE file present", SRC_ANTHROPIC),
    "FILE-LIMITS": ("At most 512 files; non-image files at most 256 KiB", SRC_ANTHROPIC),
    # Source tree only
    "MANIFEST-SYNC": (".claude-plugin/plugin.json matches what `sync` derives from the Codex "
                      "manifest", SRC_HOUSE),
    "DIR-NAME": ("The plugin directory is named after the manifest name", SRC_HOUSE),
    "LEGAL-PLACEHOLDERS": ("(--final) docs/legal has no unfilled placeholders", SRC_HOUSE),
    "LISTING-URLS-ONLINE": ("(--online) every listing URL answers 200 over HTTPS",
                            SRC_SUBMIT + " (public URLs must be accessible)"),
}

CATEGORIES = (
    "Productivity", "Creativity", "Developer Tools", "Business & Operations",
    "Data & Analytics", "Communication", "Education & Research", "Security", "Finance",
    "Healthcare", "Travel", "Entertainment", "Other",
)
REQUIRED_CATEGORY = "Developer Tools"

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)
KEBAB = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
PLACEHOLDER = re.compile(r"\{\{[A-Z0-9_]+\}\}|\bexample\.(?:com|org|net)\b|lorem ipsum", re.I)
MENTION = re.compile(r"(?<![\w.])@[\w-]+")
INLINE_COMMAND = re.compile(r"!`")
PROVIDER_NAMES = re.compile(r"\b(?:Claude|Anthropic|Codex|ChatGPT|OpenAI|GPT-\d)\b")
PRIORITY_LINE = re.compile(r"explicit instructions.{0,120}take priority", re.I | re.S)

# Listing-copy red flags (SRC_GUIDE: no comparisons, unverifiable claims or promotions).
CLAIM_WORDS = re.compile(
    r"(?:#1\b|\b\d+(?:\.\d+)?\s?%|\b(?:best|number one|fastest|leading|world[- ]class|"
    r"top[- ]rated|unlike|better than|compared (?:to|with)|competitors?|guarantee[sd]?|"
    r"proven|never fails|eliminates?|bulletproof|free|discount|trial|promo(?:tion)?s?|"
    r"subscriptions?|pricing|official|endorsed|certified)\b)",
    re.I,
)

# The same literals Truthstone's own risky-command check looks for
# (src/truthstone/validate/checks.py, _DANGEROUS), plus a few more. Skills describe these
# in prose; a runnable literal in a skill is what skill scanners flag.
RISKY_LITERALS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\brm\s+-[a-zA-Z]*[rR]"), "recursive rm"),
    (re.compile(r"\bgit\s+push\b[^\n]*\s(?:--force|-f)\b(?![-\w])"), "force push"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "hard reset"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"), "git clean -f"),
    (re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", re.I), "destructive SQL"),
    (re.compile(r"\bTRUNCATE\s+TABLE\b", re.I), "destructive SQL"),
    (re.compile(r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b"), "pipe to shell"),
    (re.compile(r"\bchmod\s+(?:-R\s+)?777\b"), "world-writable permissions"),
    (re.compile(r"\b(?:mkfs|dd)\b[^\n]*of=/dev/"), "raw device write"),
    (re.compile(r"\bsudo\s"), "sudo"),
    (re.compile(r"--no-verify\b"), "verification bypass flag"),
    (re.compile(r"--dangerously"), "safety bypass flag"),
)

SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bghp_[A-Za-z0-9]{30,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}"), "GitHub token"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "API key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".svg")
SCRIPT_EXTENSIONS = (
    ".sh", ".bash", ".zsh", ".fish", ".py", ".pyc", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".rb", ".pl", ".php", ".ps1", ".psm1", ".bat", ".cmd", ".exe", ".bin", ".so", ".dylib",
    ".dll", ".jar", ".class", ".wasm", ".lua", ".go", ".rs", ".c", ".cpp", ".swift", ".app",
)
OS_JUNK = (".DS_Store", "Thumbs.db", "desktop.ini")
CLAUDE_ONLY = ("commands", "agents", "output-styles", "outputStyles", "settings.json",
               ".lsp.json", "bin")
MANIFEST_KEYS = {
    "name", "version", "description", "author", "homepage", "repository", "license",
    "keywords", "skills", "interface", "extensions", "id",
}
INTERFACE_KEYS = {
    "displayName", "shortDescription", "longDescription", "developerName", "category",
    "capabilities", "websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL",
    "defaultPrompt", "brandColor", "brandColorDark", "composerIcon", "composerIconDark",
    "logo", "logoDark",
}
ASSET_FIELDS = ("logo", "logoDark", "composerIcon", "composerIconDark")
URL_FIELDS = ("websiteURL", "supportURL", "privacyPolicyURL", "termsOfServiceURL")


# -- findings ---------------------------------------------------------------------------


@dataclass(slots=True)
class Finding:
    rule: str
    where: str
    message: str

    def render(self) -> str:
        return f"  [{self.rule}] {self.where}: {self.message}"


@dataclass
class Report:
    label: str
    findings: list[Finding] = field(default_factory=list)

    def add(self, rule: str, where: str, message: str) -> None:
        assert rule in RULES, rule
        self.findings.append(Finding(rule, where, message))

    @property
    def ok(self) -> bool:
        return not self.findings

    def rules_hit(self) -> set[str]:
        return {finding.rule for finding in self.findings}

    def print(self) -> None:
        if self.ok:
            print(f"PASS  {self.label}: {len(RULES)} rules known, 0 findings")
            return
        print(f"FAIL  {self.label}: {len(self.findings)} finding(s)")
        for finding in self.findings:
            print(finding.render())


# -- a plugin as a set of files, whether it came from a directory or a ZIP ---------------


@dataclass
class Package:
    label: str
    files: dict[str, bytes]
    modes: dict[str, int]
    dirs: set[str]
    links: set[str]
    from_zip: bool

    def text(self, path: str) -> str | None:
        data = self.files.get(path)
        if data is None:
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return None

    def top_dirs(self) -> set[str]:
        return {path.split("/", 1)[0] for path in self.files if "/" in path} | {
            directory.split("/", 1)[0] for directory in self.dirs
        }


def load_tree(directory: Path) -> Package:
    files: dict[str, bytes] = {}
    modes: dict[str, int] = {}
    dirs: set[str] = set()
    links: set[str] = set()
    for current, dirnames, filenames in os.walk(directory, followlinks=False):
        here = Path(current)
        for name in list(dirnames):
            rel = (here / name).relative_to(directory).as_posix()
            if (here / name).is_symlink():
                links.add(rel)
                dirnames.remove(name)
            else:
                dirs.add(rel)
        for name in filenames:
            full = here / name
            rel = full.relative_to(directory).as_posix()
            info = os.lstat(full)
            if stat.S_ISLNK(info.st_mode):
                links.add(rel)
                continue
            files[rel] = full.read_bytes()
            modes[rel] = info.st_mode
    return Package(str(directory), files, modes, dirs, links, from_zip=False)


def load_zip(path: Path, report: Report) -> Package | None:
    """Check the archive itself, then return the plugin it contains (rooted at its manifest)."""
    try:
        size = path.stat().st_size
    except OSError as exc:
        report.add("ZIP-FORMAT", str(path), f"cannot read: {exc}")
        return None
    if size > 100 * 1000 * 1000:
        report.add("ZIP-FORMAT", path.name, f"compressed size {size} bytes exceeds 100 MB")
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as exc:
        report.add("ZIP-FORMAT", path.name, f"not a valid ZIP: {exc}")
        return None

    with archive:
        infos = archive.infolist()
        if not infos:
            report.add("ZIP-FORMAT", path.name, "archive is empty")
            return None
        if len(infos) > 5000:
            report.add("ZIP-LIMITS", path.name, f"{len(infos)} entries exceeds 5,000")
        total = sum(info.file_size for info in infos)
        if total > 512 * 1024 * 1024:
            report.add("ZIP-LIMITS", path.name, f"extracted size {total} exceeds 512 MiB")

        files: dict[str, bytes] = {}
        modes: dict[str, int] = {}
        dirs: set[str] = set()
        links: set[str] = set()
        seen_exact: set[str] = set()
        seen_folded: dict[str, str] = {}

        for info in infos:
            raw = info.filename
            name = raw.rstrip("/")
            is_dir = raw.endswith("/")
            where = raw or "<empty name>"
            if not name:
                report.add("ZIP-PATH", where, "empty entry path")
                continue
            if name != name.strip():
                report.add("ZIP-PATH", where, "path begins or ends with whitespace")
            if "\\" in raw:
                report.add("ZIP-PATH", where, "path uses a backslash")
            if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
                report.add("ZIP-PATH", where, "absolute path")
            segments = name.split("/")
            if any(segment == "" for segment in segments):
                report.add("ZIP-PATH", where, "empty path segment")
            if any(segment == ".." for segment in segments):
                report.add("ZIP-PATH", where, "'..' path segment")
            if len(segments) > 20:
                report.add("ZIP-PATH", where, f"{len(segments)} segments exceeds 20")
            if len(raw.encode("utf-8")) > 1024:
                report.add("ZIP-PATH", where, "path longer than 1,024 bytes")
            if raw in seen_exact:
                report.add("ZIP-PATH", where, "duplicate entry")
            seen_exact.add(raw)
            folded = unicodedata.normalize("NFC", name).casefold()
            if folded in seen_folded and seen_folded[folded] != name:
                report.add("ZIP-PATH", where,
                           f"collides with '{seen_folded[folded]}' after case/Unicode normalization")
            seen_folded.setdefault(folded, name)

            mode = (info.external_attr >> 16) & 0xFFFF
            if info.flag_bits & 0x1:
                report.add("ZIP-ENTRY-TYPE", where, "entry is encrypted")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                report.add("ZIP-ENTRY-TYPE", where, f"unsupported compression {info.compress_type}")
            if mode and stat.S_ISLNK(mode):
                report.add("ZIP-ENTRY-TYPE", where, "symbolic link")
                links.add(name)
                continue
            if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                report.add("ZIP-ENTRY-TYPE", where, f"not a regular file or directory (mode {oct(mode)})")
                continue
            if info.file_size > 100 * 1024 * 1024:
                report.add("ZIP-LIMITS", where, "entry exceeds 100 MiB")
            if is_dir or (mode and stat.S_ISDIR(mode)):
                dirs.add(name)
                continue
            try:
                files[name] = archive.read(info)
            except Exception as exc:  # noqa: BLE001 - any unreadable entry is a finding
                report.add("ZIP-ENTRY-TYPE", where, f"unreadable: {exc}")
                continue
            modes[name] = mode

    for name in files:
        parts = name.split("/")
        for depth in range(1, len(parts)):
            parent = "/".join(parts[:depth])
            if parent in files:
                report.add("ZIP-PATH", name, f"'{parent}' is both a file and a directory")
            dirs.add(parent)

    # Locate the plugin root.
    manifests = [name for name in files if name.endswith(".codex-plugin/plugin.json")]
    if ".codex-plugin/plugin.json" in files:
        prefix = ""
    else:
        tops = {name.split("/", 1)[0] for name in files}
        candidates = [m for m in manifests if m.count("/") == 2]
        if len(tops) != 1 or len(candidates) != 1:
            report.add("ZIP-ROOT", path.name,
                       "no .codex-plugin/plugin.json at the archive root or in a single "
                       "top-level directory")
            return None
        prefix = candidates[0].split("/", 1)[0] + "/"
    if prefix:
        siblings = [name for name in files if not name.startswith(prefix)]
        if siblings:
            report.add("ZIP-ROOT", path.name, f"files beside the plugin directory: {siblings[:3]}")
    nested = [m for m in manifests if m != prefix + ".codex-plugin/plugin.json"]
    if nested:
        report.add("ZIP-ROOT", path.name, f"more than one plugin manifest: {nested[:3]}")

    def strip(name: str) -> str:
        return name[len(prefix):]

    return Package(
        label=path.name,
        files={strip(n): d for n, d in files.items() if n.startswith(prefix)},
        modes={strip(n): m for n, m in modes.items() if n.startswith(prefix)},
        dirs={strip(n) for n in dirs if n.startswith(prefix) and strip(n)},
        links={strip(n) for n in links if n.startswith(prefix)},
        from_zip=True,
    )


# -- small helpers -----------------------------------------------------------------------


def bad_characters(value: str, multiline: bool = False) -> list[str]:
    bad = []
    for char in value:
        if multiline and char == "\n":
            continue
        if unicodedata.category(char) in ("Cc", "Cf", "Zl", "Zp", "Cs", "Co", "Cn"):
            bad.append(f"U+{ord(char):04X}")
    return bad


def url_problems(value: object, limit: int) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return ["must be a non-empty string"]
    problems = []
    parts = urlsplit(value)
    if parts.scheme != "https":
        problems.append("must use https")
    if not parts.hostname:
        problems.append("must include a host")
    if parts.username or parts.password:
        problems.append("must not embed credentials")
    if any(char.isspace() for char in value) or bad_characters(value):
        problems.append("contains unsupported characters")
    if len(value) > limit:
        problems.append(f"longer than {limit} characters")
    return problems


def luminance(color: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def normalized_prompt(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def mask_code(markdown: str) -> str:
    """Markdown with fenced and indented code removed (for word counts and prose checks)."""
    out, fenced = [], False
    for line in markdown.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or line.startswith(("    ", "\t")):
            continue
        out.append(re.sub(r"`[^`]*`", " ", line))
    return "\n".join(out)


# -- image checks ------------------------------------------------------------------------

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    pos, idat, width, height, ended = 8, [], 0, 0, False
    depth = color = interlace = 0
    first = True
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated chunk header")
        length = int.from_bytes(data[pos:pos + 4], "big")
        kind = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            raise ValueError("truncated chunk")
        if zlib.crc32(kind + body) & 0xFFFFFFFF != int.from_bytes(crc, "big"):
            raise ValueError(f"bad CRC in {kind.decode('latin-1')} chunk")
        if first:
            if kind != b"IHDR" or length != 13:
                raise ValueError("first chunk is not IHDR")
            width = int.from_bytes(body[0:4], "big")
            height = int.from_bytes(body[4:8], "big")
            depth, color, interlace = body[8], body[9], body[12]
            first = False
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            ended = True
            break
        pos += 12 + length
    if not ended:
        raise ValueError("missing IEND chunk")
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color)
    if channels is None:
        raise ValueError(f"unknown colour type {color}")
    try:
        pixels = zlib.decompress(b"".join(idat))
    except zlib.error as exc:
        raise ValueError(f"image data does not decompress: {exc}") from exc
    if interlace == 0:
        stride = 1 + (width * channels * depth + 7) // 8
        if len(pixels) != stride * height:
            raise ValueError("pixel data does not match the declared dimensions")
    return width, height


def jpeg_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\xff\xd8"):
        raise ValueError("not a JPEG file")
    pos = 2
    frames = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            raise ValueError("corrupt marker")
        while pos + 1 < len(data) and data[pos + 1] == 0xFF:
            pos += 1
        marker = data[pos + 1]
        pos += 2
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9:
            break
        length = int.from_bytes(data[pos:pos + 2], "big")
        if marker in frames:
            return int.from_bytes(data[pos + 5:pos + 7], "big"), int.from_bytes(data[pos + 3:pos + 5], "big")
        pos += length
    raise ValueError("no frame header")


def webp_size(data: bytes) -> tuple[int, int]:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError("not a WebP file")
    chunk = data[12:16]
    if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
        return (int.from_bytes(data[26:28], "little") & 0x3FFF,
                int.from_bytes(data[28:30], "little") & 0x3FFF)
    if chunk == b"VP8L" and data[20:21] == b"\x2f":
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        return int.from_bytes(data[24:27], "little") + 1, int.from_bytes(data[27:30], "little") + 1
    raise ValueError("unrecognised WebP bitstream")


NUMBER = re.compile(r"^\s*[+]?(?:\d+(?:\.\d*)?|\.\d+)\s*$")


def svg_size(data: bytes) -> tuple[float, float]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("SVG is not valid UTF-8") from exc
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        raise ValueError("DOCTYPE and ENTITY declarations are not allowed")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ValueError(f"malformed XML: {exc}") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("root element is not <svg>")
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1]
        if tag in ("script", "foreignObject", "image", "iframe", "embed", "object"):
            raise ValueError(f"<{tag}> is not allowed")
        for attribute, value in element.attrib.items():
            local = attribute.rsplit("}", 1)[-1]
            if local.lower().startswith("on"):
                raise ValueError(f"event handler attribute '{local}'")
            if local == "href" and not value.startswith("#"):
                raise ValueError("external or embedded reference in href")
            if "url(" in value and re.search(r"url\(\s*['\"]?(?!#)", value):
                raise ValueError("external url() reference")
    width, height = root.get("width"), root.get("height")
    box = root.get("viewBox")
    if width is None and height is None and box is None:
        raise ValueError("needs a numeric viewBox or numeric width and height")
    size: tuple[float, float] | None = None
    if width is not None or height is not None:
        if width is None or height is None or not NUMBER.match(width) or not NUMBER.match(height):
            raise ValueError("width and height must both be unitless numbers")
        size = (float(width), float(height))
    if box is not None:
        parts = re.split(r"[\s,]+", box.strip())
        if len(parts) != 4 or not all(NUMBER.match(p) or re.match(r"^\s*-\d", p) for p in parts):
            raise ValueError("viewBox must be four numbers")
        box_size = (float(parts[2]), float(parts[3]))
        if box_size[0] != box_size[1]:
            raise ValueError(f"viewBox is not square: {box_size}")
        if size is None:
            size = box_size
    assert size is not None
    return size


def check_image(report: Report, package: Package, path: str, field_name: str) -> None:
    data = package.files[path]
    lower = path.lower()
    where = f"{field_name} -> {path}"
    if not lower.endswith(IMAGE_EXTENSIONS):
        report.add("IMAGE", where, "extension must be .png, .jpg, .jpeg, .webp or .svg")
        return
    if len(data) > 5 * 1024 * 1024:
        report.add("IMAGE", where, "larger than 5 MiB")
    try:
        if lower.endswith(".svg"):
            width, height = svg_size(data)
        else:
            detected = ("png" if data.startswith(PNG_SIGNATURE) else
                        "jpeg" if data.startswith(b"\xff\xd8") else
                        "webp" if data[:4] == b"RIFF" else "unknown")
            expected = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "webp": "webp"}[lower.rsplit(".", 1)[1]]
            if detected != expected:
                report.add("IMAGE", where, f"extension says {expected}, content is {detected}")
                return
            width, height = {"png": png_size, "jpeg": jpeg_size, "webp": webp_size}[detected](data)
            if max(width, height) > 4096:
                report.add("IMAGE", where, f"{width}x{height} exceeds 4,096 px")
    except ValueError as exc:
        report.add("IMAGE", where, str(exc))
        return
    if width != height:
        report.add("IMAGE", where, f"not square ({width:g}x{height:g})")
    if min(width, height) < 48:
        report.add("IMAGE", where, f"smaller than 48x48 ({width:g}x{height:g})")


# -- strict YAML subset (front matter and agents/openai.yaml) ---------------------------


class YamlSubsetError(ValueError):
    pass


def parse_scalar(raw: str) -> object:
    raw = raw.strip()
    if raw == "":
        return ""
    if raw[0] == '"':
        if len(raw) < 2 or raw[-1] != '"':
            raise YamlSubsetError("unterminated double-quoted string")
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YamlSubsetError(f"bad double-quoted string: {exc}") from exc
    if raw[0] == "'":
        if len(raw) < 2 or raw[-1] != "'":
            raise YamlSubsetError("unterminated single-quoted string")
        return raw[1:-1].replace("''", "'")
    if raw[0] == "[" and raw[-1] == "]":
        inner = raw[1:-1].strip()
        return [] if not inner else [parse_scalar(item) for item in inner.split(",")]
    if raw[0] in "{&*!|>%@`[]#,?-:" and not re.match(r"^-?\d", raw):
        raise YamlSubsetError(f"plain value may not start with {raw[0]!r}; quote it")
    if ": " in raw or raw.endswith(":") or " #" in raw:
        raise YamlSubsetError("plain value contains ': ' or ' #'; quote it")
    if raw in ("true", "false"):
        return raw == "true"
    return raw


def parse_yaml_subset(text: str, max_depth: int) -> dict[str, object]:
    """Block mappings and lists nested by two-space indentation, up to `max_depth` levels.

    Deliberately small: anything outside this subset is reported rather than guessed at,
    because the files it reads are ours and should stay this simple.
    """
    if "\t" in text:
        raise YamlSubsetError("tab characters are not allowed")
    root: dict[str, object] = {}
    # Each frame: (indent of the key that owns the container, the container).
    frames: list[tuple[int, dict[str, object] | list[object]]] = [(-1, root)]
    pending: tuple[dict[str, object], str, int] | None = None  # key whose value is nested
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent % 2:
            raise YamlSubsetError(f"line {number}: indentation must be a multiple of two spaces")
        stripped = line.strip()
        if pending is not None:
            parent, key, key_indent = pending
            pending = None
            if indent > key_indent:
                if len(frames) + 1 > max_depth:
                    raise YamlSubsetError(f"line {number}: nested deeper than {max_depth} level(s)")
                container: dict[str, object] | list[object] = [] if stripped.startswith("-") else {}
                parent[key] = container
                frames.append((key_indent, container))
            else:
                parent[key] = ""
        while len(frames) > 1 and indent <= frames[-1][0]:
            frames.pop()
        current = frames[-1][1]
        if stripped == "-" or stripped.startswith("- "):
            if not isinstance(current, list):
                raise YamlSubsetError(f"line {number}: list item without a list key")
            current.append(parse_scalar(stripped[1:]))
            continue
        if isinstance(current, list):
            raise YamlSubsetError(f"line {number}: expected '- item' inside a list")
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):(?:\s+(.*))?$", stripped)
        if not match:
            raise YamlSubsetError(f"line {number}: expected 'key: value'")
        key, value = match.group(1), match.group(2)
        if key in current:
            raise YamlSubsetError(f"line {number}: duplicate key '{key}'")
        if value is None or not value.strip():
            pending = (current, key, indent)
        else:
            current[key] = parse_scalar(value)
    if pending is not None:
        pending[0][pending[1]] = ""
    return root


def split_front_matter(text: str) -> tuple[dict[str, object], str]:
    if "\r" in text:
        raise YamlSubsetError("use LF line endings")
    if not text.startswith("---\n"):
        raise YamlSubsetError("must start with '---' front matter")
    end = text.find("\n---\n", 3)
    if end == -1:
        if text.endswith("\n---"):
            end = len(text) - 4
        else:
            raise YamlSubsetError("front matter is not closed with '---'")
    header = text[4:end + 1]
    body = text[end + 5:]
    data = parse_yaml_subset(header, max_depth=1)
    for key, value in data.items():
        if isinstance(value, (dict, list)):
            raise YamlSubsetError(f"'{key}' must be a single text value")
    return data, body


# -- the checks --------------------------------------------------------------------------


def check_package(package: Package, report: Report, layout: Layout | None = None) -> dict | None:
    """Every rule that applies to the plugin's own files, whichever form they arrived in."""
    files = package.files

    # Things a public, skills-only package must not contain.
    for link in sorted(package.links):
        report.add("ZIP-ENTRY-TYPE" if package.from_zip else "SKILL-LAYOUT", link,
                   "symbolic links are not allowed")
    for path in sorted(files):
        name = PurePosixPath(path).name
        parts = PurePosixPath(path).parts
        if name in OS_JUNK or "__MACOSX" in parts:
            report.add("NO-OS-JUNK", path, "operating-system junk file")
        if parts[0] == "hooks" or name in ("hooks.json",):
            report.add("NO-HOOKS", path, "lifecycle hook file")
        if name == ".app.json":
            report.add("NO-APPS", path, "app reference file")
        if name in (".mcp.json", "mcp.json"):
            report.add("NO-MCP", path, "MCP server configuration")
        if name == "marketplace.json" or parts[0] in CLAUDE_ONLY or name in CLAUDE_ONLY:
            report.add("NO-CLAUDE-ONLY", path, "component OpenAI does not import")
        if package.from_zip and parts[0] == ".claude-plugin":
            report.add("ZIP-ONE-MANIFEST", path, "the submission ZIP carries only the Codex manifest")
        if name.startswith(".env"):
            report.add("NO-SECRETS", path, "environment file")
        if name.lower().endswith(SCRIPT_EXTENSIONS) or "scripts" in parts[:-1]:
            report.add("NO-EXECUTABLES", path, "script or binary in the plugin")
        mode = package.modes.get(path, 0)
        if mode & 0o111:
            report.add("NO-EXECUTABLES", path, f"executable permission bits ({oct(mode & 0o777)})")
        text = package.text(path)
        if text is not None:
            for pattern, label in SECRET_PATTERNS:
                if pattern.search(text):
                    report.add("NO-SECRETS", path, f"looks like a {label}")
            if path.endswith((".md", ".json", ".yaml", ".yml", ".txt")) and PLACEHOLDER.search(text):
                report.add("NO-PLACEHOLDERS", path,
                           f"unfilled placeholder '{PLACEHOLDER.search(text).group(0)}'")
        if not path.lower().endswith(IMAGE_EXTENSIONS) and len(files[path]) > 256 * 1024:
            report.add("FILE-LIMITS", path, "non-image file larger than 256 KiB")
    if any(d == "hooks" or d.endswith("/hooks") for d in package.dirs):
        report.add("NO-HOOKS", "hooks/", "hooks directory")
    if len(files) > 512:
        report.add("FILE-LIMITS", package.label, f"{len(files)} files exceeds 512")

    readme = package.text("README.md")
    if readme is None:
        report.add("README", "README.md", "missing")
    elif len(re.findall(r"[A-Za-z0-9][\w'-]*", mask_code(readme))) < 40:
        report.add("README", "README.md", "fewer than 40 words outside code")
    if "LICENSE" not in files and "LICENSE.md" not in files and "LICENSE.txt" not in files:
        report.add("LICENSE", "LICENSE", "missing")

    manifest = check_manifest(package, report)
    if manifest is not None:
        check_skills(package, report, manifest)
    return manifest


def check_manifest(package: Package, report: Report) -> dict | None:
    where = ".codex-plugin/plugin.json"
    raw = package.files.get(where)
    if raw is None:
        report.add("MANIFEST-FILE", where, "missing")
        return None
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        report.add("MANIFEST-FILE", where, f"not valid UTF-8 JSON: {exc}")
        return None
    if not isinstance(manifest, dict):
        report.add("MANIFEST-FILE", where, "top level is not an object")
        return None

    for key in sorted(set(manifest) - MANIFEST_KEYS):
        rule = {"hooks": "NO-HOOKS", "apps": "NO-APPS", "mcpServers": "NO-MCP",
                "requires_local_executor": "NO-LOCAL-EXECUTOR"}.get(key, "MANIFEST-FILE")
        report.add(rule, f"{where}:{key}", "key not allowed in this package")

    name = manifest.get("name")
    if not isinstance(name, str) or not name:
        report.add("NAME", where, "name is required")
    else:
        if len(name) > 64:
            report.add("NAME", where, "longer than 64 characters")
        if not KEBAB.match(name):
            report.add("NAME", where, "use lowercase letters, digits and single hyphens")

    version = manifest.get("version")
    if not isinstance(version, str) or not SEMVER.match(version) or len(version) > 64:
        report.add("VERSION", where, f"not a semantic version: {version!r}")

    description = manifest.get("description")
    if not isinstance(description, str) or not description.strip():
        report.add("DESCRIPTION", where, "description is required")
    else:
        if len(description) > 1024:
            report.add("DESCRIPTION", where, f"{len(description)} characters exceeds 1,024")
        if bad_characters(description, multiline=True):
            report.add("TEXT", f"{where}:description", f"unsupported characters {bad_characters(description, True)}")

    author = manifest.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author["name"].strip():
        report.add("AUTHOR", where, "author.name is required")
    else:
        if len(author["name"]) > 120:
            report.add("AUTHOR", where, "author.name longer than 120 characters")
        if "email" in author and (not isinstance(author["email"], str) or not author["email"]
                                  or len(author["email"]) > 320):
            report.add("AUTHOR", where, "author.email must be a non-empty string of at most 320 characters")
        if "url" in author:
            for problem in url_problems(author["url"], 2048):
                report.add("AUTHOR", where, f"author.url {problem}")
    if "homepage" in manifest:
        for problem in url_problems(manifest["homepage"], 2048):
            report.add("HOMEPAGE", where, f"homepage {problem}")

    skills = manifest.get("skills")
    if skills not in ("./skills/", "./skills"):
        report.add("SKILLS-PATH", where, f"skills must be './skills/', got {skills!r}")

    check_extensions(manifest, report, where)

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        report.add("INTERFACE", where, "interface object is required")
        return manifest
    check_interface(package, interface, report, where)
    check_copy(manifest, report, where)
    return manifest


def check_extensions(manifest: dict, report: Report, where: str) -> None:
    extensions = manifest.get("extensions")
    if extensions is None:
        return
    if not isinstance(extensions, dict) or set(extensions) - {"com.openai"}:
        report.add("EXTENSIONS", where, "extensions may only hold 'com.openai'")
        return
    openai = extensions.get("com.openai")
    if not isinstance(openai, dict):
        report.add("EXTENSIONS", where, "extensions.com.openai must be an object")
        return
    for key in openai:
        if key in ("hooks",):
            report.add("NO-HOOKS", f"{where}:extensions.com.openai.{key}", "hooks are not allowed")
        elif key in ("apps",):
            report.add("NO-APPS", f"{where}:extensions.com.openai.{key}", "apps are not allowed")
        elif key == "requires_local_executor":
            report.add("NO-LOCAL-EXECUTOR", f"{where}:extensions.com.openai.{key}", "not allowed")
        elif key not in ("onboardingSkill", "review", "publication"):
            report.add("EXTENSIONS", f"{where}:extensions.com.openai.{key}", "unsupported key")
    review = openai.get("review")
    if isinstance(review, dict):
        for forbidden in ("test_credentials", "reviewer_instructions"):
            if forbidden in review:
                report.add("NO-REVIEW-CREDENTIALS", f"{where}:review.{forbidden}", "must not be in the package")
    publication = openai.get("publication")
    if publication is not None:
        if not isinstance(publication, dict):
            report.add("EXTENSIONS", where, "publication must be an object")
        else:
            notes = publication.get("release_notes")
            if notes is not None and (not isinstance(notes, str) or bad_characters(notes, True)):
                report.add("EXTENSIONS", where, "release_notes must be supported text")
            countries = publication.get("countries")
            if countries is not None and (
                not isinstance(countries, list)
                or not all(isinstance(c, str) and re.fullmatch(r"[A-Z]{2}", c) for c in countries)
            ):
                report.add("EXTENSIONS", where, "countries must be uppercase two-letter codes")
    skill = openai.get("onboardingSkill")
    if skill is not None and (not isinstance(skill, str) or not re.fullmatch(r"\./skills/[^/]+/SKILL\.md", skill)):
        report.add("EXTENSIONS", where, "onboardingSkill must be ./skills/<name>/SKILL.md")


def check_interface(package: Package, interface: dict, report: Report, where: str) -> None:
    for key in sorted(set(interface) - INTERFACE_KEYS):
        rule = "NO-SCREENSHOTS" if key == "screenshots" else "INTERFACE"
        report.add(rule, f"{where}:interface.{key}", "field not allowed in this package")

    def one_line(key: str, rule: str, limit: int, required: bool = True) -> str | None:
        value = interface.get(key)
        if value is None:
            if required:
                report.add(rule, where, f"interface.{key} is required")
            return None
        if not isinstance(value, str) or not value.strip():
            report.add(rule, where, f"interface.{key} must be non-empty text")
            return None
        if "\n" in value or "\r" in value:
            report.add(rule, where, f"interface.{key} must be one line")
        if len(value) > limit:
            report.add(rule, where, f"interface.{key} is {len(value)} characters; limit {limit}")
        if bad_characters(value):
            report.add("TEXT", f"{where}:interface.{key}", f"unsupported characters {bad_characters(value)}")
        return value

    display = one_line("displayName", "DISPLAY-NAME", 30)
    if display and re.search(r"(?:\bMCP(?: Server)?|\bPlugin)\s*$", display, re.I):
        report.add("DISPLAY-NAME", where, "don't append 'MCP', 'MCP Server' or 'Plugin' to the name")
    one_line("shortDescription", "SHORT-DESCRIPTION", 30)
    one_line("developerName", "DEVELOPER-NAME", 80)

    long_description = interface.get("longDescription")
    if not isinstance(long_description, str) or not long_description.strip():
        report.add("LONG-DESCRIPTION", where, "interface.longDescription is required")
    else:
        if len(long_description) > 4000:
            report.add("LONG-DESCRIPTION", where, f"{len(long_description)} characters exceeds 4,000")
        if bad_characters(long_description, multiline=True):
            report.add("TEXT", f"{where}:interface.longDescription",
                       f"unsupported characters {bad_characters(long_description, True)}")

    category = interface.get("category")
    if category not in CATEGORIES:
        report.add("CATEGORY", where, f"unknown category {category!r}")
    elif category != REQUIRED_CATEGORY:
        report.add("CATEGORY", where, f"this plugin lists under {REQUIRED_CATEGORY!r}")

    capabilities = interface.get("capabilities")
    if not isinstance(capabilities, list):
        report.add("CAPABILITIES", where, "interface.capabilities must be a list (use [] for none)")
    else:
        if len(capabilities) > 20:
            report.add("CAPABILITIES", where, f"{len(capabilities)} capabilities exceeds 20")
        for index, item in enumerate(capabilities):
            if not isinstance(item, str) or not item.strip() or "\n" in item or len(item) > 120:
                report.add("CAPABILITIES", where, f"capability {index + 1} must be one line of 1-120 characters")
            elif bad_characters(item):
                report.add("TEXT", f"{where}:capabilities[{index}]", "unsupported characters")

    prompts = interface.get("defaultPrompt")
    if prompts is not None:
        items = [prompts] if isinstance(prompts, str) else prompts
        if not isinstance(items, list) or not all(isinstance(p, str) for p in items):
            report.add("DEFAULT-PROMPT", where, "defaultPrompt must be a string or a list of strings")
        else:
            if len(items) > 3:
                report.add("DEFAULT-PROMPT", where, f"{len(items)} prompts exceeds 3")
            seen: set[str] = set()
            for index, prompt in enumerate(items, start=1):
                if not prompt.strip() or "\n" in prompt or len(prompt) > 128:
                    report.add("DEFAULT-PROMPT", where, f"prompt {index} must be one line of 1-128 characters")
                if MENTION.search(prompt):
                    report.add("DEFAULT-PROMPT", where, f"prompt {index} contains an @mention")
                key = normalized_prompt(prompt)
                if key in seen:
                    report.add("DEFAULT-PROMPT", where, f"prompt {index} duplicates an earlier prompt")
                seen.add(key)
                if bad_characters(prompt):
                    report.add("TEXT", f"{where}:defaultPrompt[{index - 1}]", "unsupported characters")

    for key in URL_FIELDS:
        if key in interface:
            for problem in url_problems(interface[key], 1024):
                report.add("LISTING-URLS", where, f"interface.{key} {problem}")
    for key in ("privacyPolicyURL", "supportURL"):
        if key not in interface:
            report.add("LISTING-URLS", where, f"interface.{key} is required by this package's policy")

    for key, background in (("brandColor", "#FFFFFF"), ("brandColorDark", "#212121")):
        value = interface.get(key)
        if value is None:
            continue
        if not isinstance(value, str) or not HEX_COLOR.match(value):
            report.add("BRAND-COLOR", where, f"interface.{key} must be #RRGGBB")
            continue
        ratio = contrast(value, background)
        if ratio < 2.0:
            report.add("BRAND-COLOR", where, f"interface.{key} {value} has {ratio:.2f}:1 against {background}; needs 2:1")

    for key in ASSET_FIELDS:
        value = interface.get(key)
        if value is None:
            if key in ("logo", "composerIcon"):
                report.add("ASSET-PATH", where, f"interface.{key} is required")
            continue
        if not isinstance(value, str) or not value.strip() or value != value.strip():
            report.add("ASSET-PATH", where, f"interface.{key} must be a path without outer whitespace")
            continue
        if bad_characters(value):
            report.add("ASSET-PATH", where, f"interface.{key} has control characters")
            continue
        if not value.startswith("./"):
            report.add("ASSET-PATH", where, f"interface.{key} must start with './'")
            continue
        relative = PurePosixPath(value[2:])
        if relative.is_absolute() or ".." in relative.parts or re.match(r"^[A-Za-z]:", value[2:]):
            report.add("ASSET-PATH", where, f"interface.{key} escapes the plugin")
            continue
        path = relative.as_posix()
        if path not in package.files:
            report.add("ASSET-PATH", where, f"interface.{key} names a missing file: {value}")
            continue
        check_image(report, package, path, f"interface.{key}")


def check_copy(manifest: dict, report: Report, where: str) -> None:
    interface = manifest.get("interface") or {}
    texts: list[tuple[str, str]] = [("description", manifest.get("description") or "")]
    for key in ("displayName", "shortDescription", "longDescription", "developerName"):
        if isinstance(interface.get(key), str):
            texts.append((f"interface.{key}", interface[key]))
    for key in ("capabilities", "defaultPrompt"):
        values = interface.get(key)
        if isinstance(values, str):
            values = [values]
        for index, value in enumerate(values or []):
            if isinstance(value, str):
                texts.append((f"interface.{key}[{index}]", value))
    notes = (((manifest.get("extensions") or {}).get("com.openai") or {}).get("publication") or {}).get("release_notes")
    if isinstance(notes, str):
        texts.append(("publication.release_notes", notes))
    for label, text in texts:
        for match in CLAIM_WORDS.finditer(text):
            report.add("LISTING-COPY", f"{where}:{label}", f"avoid '{match.group(0)}' (claims, comparisons, pricing)")
        if re.search(r"\b(?:by|from|with) OpenAI\b|\bOpenAI[- ](?:approved|endorsed)\b", text):
            report.add("LISTING-COPY", f"{where}:{label}", "must not imply OpenAI made or endorsed it")


def check_skills(package: Package, report: Report, manifest: dict) -> None:
    plugin_name = manifest.get("name") if isinstance(manifest.get("name"), str) else ""
    skill_dirs: dict[str, list[str]] = {}
    for path in package.files:
        parts = PurePosixPath(path).parts
        if parts[0] != "skills":
            continue
        if len(parts) == 2:
            report.add("SKILL-LAYOUT", path, "files directly under skills/ are not imported")
            continue
        skill_dirs.setdefault(parts[1], []).append(path)
    for link in package.links:
        if link.startswith("skills/"):
            report.add("SKILL-LAYOUT", link, "symbolic link under skills/")
    if not skill_dirs:
        report.add("SKILLS-PRESENT", "skills/", "no skills found")
        return

    names: dict[str, str] = {}
    for directory in sorted(skill_dirs):
        base = f"skills/{directory}"
        if directory.startswith("."):
            report.add("SKILL-LAYOUT", base, "skill directory names must not begin with '.'")
        skill_md = f"{base}/SKILL.md"
        if skill_md not in package.files:
            nested = [p for p in skill_dirs[directory] if p.endswith("/SKILL.md")]
            report.add("SKILL-LAYOUT", base, "SKILL.md must sit directly in the skill directory"
                       + (f" (found {nested[0]})" if nested else ""))
            continue
        text = package.text(skill_md)
        if text is None:
            report.add("SKILL-FRONTMATTER", skill_md, "not valid UTF-8")
            continue
        try:
            front, body = split_front_matter(text)
        except YamlSubsetError as exc:
            report.add("SKILL-FRONTMATTER", skill_md, str(exc))
            continue

        name = front.get("name")
        if not isinstance(name, str) or not name.strip():
            report.add("SKILL-NAME", skill_md, "name is required")
        else:
            if not KEBAB.match(name) or len(name) > 64:
                report.add("SKILL-NAME", skill_md, "use lowercase letters, digits and hyphens (max 64)")
            if name != directory:
                report.add("SKILL-NAME", skill_md, f"name '{name}' differs from its directory '{directory}'")
            if name in names:
                report.add("SKILL-NAME", skill_md, f"duplicates the skill in {names[name]}")
            names[name] = skill_md
            if len(f"{plugin_name}:{name}") > 64:
                report.add("SKILL-IDENTITY", skill_md, f"'{plugin_name}:{name}' exceeds 64 characters")
        description = front.get("description")
        if not isinstance(description, str) or not description.strip():
            report.add("SKILL-DESCRIPTION", skill_md, "description is required")
        else:
            if len(description) > 1024:
                report.add("SKILL-DESCRIPTION", skill_md, f"{len(description)} characters exceeds 1,024")
            if bad_characters(description):
                report.add("SKILL-DESCRIPTION", skill_md, "unsupported characters")
        if not body.strip():
            report.add("SKILL-BODY", skill_md, "instructions are empty")

        for path in sorted(skill_dirs[directory]):
            content = package.text(path)
            if content is None or not path.endswith(".md"):
                continue
            if INLINE_COMMAND.search(content):
                report.add("SKILL-NO-COMMAND-INJECTION", path, "inline command execution syntax '!`'")
            for pattern, label in RISKY_LITERALS:
                match = pattern.search(content)
                if match:
                    report.add("SKILL-NO-RISKY-LITERALS", path, f"runnable {label} literal: '{match.group(0)}'")
            neutral = PROVIDER_NAMES.search(content)
            if neutral:
                report.add("SKILL-NEUTRAL", path, f"provider-specific reference '{neutral.group(0)}'")
        if not PRIORITY_LINE.search(body):
            report.add("SKILL-PRIORITY", skill_md, "say that explicit user instructions take priority")

        agent = f"{base}/agents/openai.yaml"
        if agent in package.files:
            check_agent_metadata(package, report, agent)


def check_agent_metadata(package: Package, report: Report, path: str) -> None:
    text = package.text(path)
    if text is None:
        report.add("SKILL-AGENT-METADATA", path, "not valid UTF-8")
        return
    try:
        data = parse_yaml_subset(text, max_depth=3)
    except YamlSubsetError as exc:
        report.add("SKILL-AGENT-METADATA", path, str(exc))
        return
    interface = data.get("interface")
    if not isinstance(interface, dict):
        report.add("SKILL-AGENT-METADATA", path, "interface mapping is required")
        return
    for key in ("display_name", "short_description"):
        value = interface.get(key)
        if not isinstance(value, str) or not value.strip():
            report.add("SKILL-AGENT-METADATA", path, f"interface.{key} is required")
    for key in set(interface) - {"display_name", "short_description", "icon_small", "icon_large",
                                 "brand_color", "default_prompt"}:
        report.add("SKILL-AGENT-METADATA", path, f"unsupported interface key '{key}'")
    color = interface.get("brand_color")
    if color is not None and (not isinstance(color, str) or not HEX_COLOR.match(color)):
        report.add("SKILL-AGENT-METADATA", path, "brand_color must be #RRGGBB")
    policy = data.get("policy")
    if policy is not None:
        if not isinstance(policy, dict) or set(policy) - {"products", "allow_implicit_invocation"}:
            report.add("SKILL-AGENT-METADATA", path, "policy may hold only products and allow_implicit_invocation")
        else:
            products = policy.get("products")
            if products is not None and (not isinstance(products, list)
                                         or not set(products) <= {"CHAT", "CODEX"} or not products):
                report.add("SKILL-AGENT-METADATA", path, "products must list CHAT and/or CODEX")
            implicit = policy.get("allow_implicit_invocation")
            if implicit is not None and not isinstance(implicit, bool):
                report.add("SKILL-AGENT-METADATA", path, "allow_implicit_invocation must be true or false")
    if "dependencies" in data:
        report.add("SKILL-AGENT-METADATA", path, "no tool dependencies: this plugin has no MCP server")
    for key in set(data) - {"interface", "policy", "dependencies"}:
        report.add("SKILL-AGENT-METADATA", path, f"unsupported top-level key '{key}'")


# -- source-tree-only checks -------------------------------------------------------------


def derived_claude_manifest(codex: dict) -> dict:
    """The Claude Code manifest is derived, never edited by hand."""
    interface = codex.get("interface") or {}
    claude = {
        "name": codex.get("name"),
        "displayName": interface.get("displayName"),
        "version": codex.get("version"),
        "description": codex.get("description"),
        "author": codex.get("author"),
        "homepage": codex.get("homepage"),
        "repository": codex.get("repository"),
        "license": codex.get("license"),
        "keywords": codex.get("keywords"),
    }
    return {key: value for key, value in claude.items() if value is not None}


def check_source(layout: Layout, report: Report, final: bool, online: bool) -> None:
    package = load_tree(layout.plugin_dir)
    manifest = check_package(package, report, layout)
    if manifest is None:
        return
    if manifest.get("name") != layout.plugin_dir.name:
        report.add("DIR-NAME", str(layout.plugin_dir.relative_to(layout.root)),
                   f"directory should be named '{manifest.get('name')}'")
    try:
        claude = json.loads(layout.claude_manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("MANIFEST-SYNC", ".claude-plugin/plugin.json", f"unreadable: {exc}")
    else:
        if claude != derived_claude_manifest(manifest):
            report.add("MANIFEST-SYNC", ".claude-plugin/plugin.json",
                       "differs from the Codex manifest; run `companion_package.py sync`")

    repository = manifest.get("repository") or ""
    interface = manifest.get("interface") or {}
    for key in URL_FIELDS:
        url = interface.get(key)
        if not isinstance(url, str) or not repository or not url.startswith(repository + "/blob/"):
            continue
        local = url[len(repository) + len("/blob/"):].split("/", 1)
        if len(local) == 2 and not (layout.root / local[1]).is_file():
            report.add("LISTING-URLS-LOCAL", f"interface.{key}", f"{local[1]} does not exist in this checkout")

    if final:
        for path in sorted(layout.legal_dir.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for match in PLACEHOLDER.finditer(text):
                report.add("LEGAL-PLACEHOLDERS", str(path.relative_to(layout.root)),
                           f"fill in '{match.group(0)}'")
    if online:
        urls = [interface.get(key) for key in URL_FIELDS] + [manifest.get("homepage"),
                                                              (manifest.get("author") or {}).get("url")]
        for url in sorted({u for u in urls if isinstance(u, str)}):
            status = fetch_status(url)
            if status != 200:
                report.add("LISTING-URLS-ONLINE", url, f"answered {status}")


def fetch_status(url: str) -> int | str:
    request = urllib.request.Request(url, headers={"User-Agent": "companion-package-check/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - https only
            if not response.geturl().startswith("https://"):
                return "redirected off HTTPS"
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code
    except (urllib.error.URLError, TimeoutError) as exc:
        return f"error: {exc}"


# -- commands ----------------------------------------------------------------------------


def zip_members(layout: Layout) -> dict[str, bytes]:
    """What the submission ZIP contains: the plugin minus the Claude manifest and dotfiles."""
    package = load_tree(layout.plugin_dir)
    members = {}
    for path, data in package.files.items():
        parts = PurePosixPath(path).parts
        if parts[0] == ".claude-plugin" or path == ".codexignore":
            continue
        members[path] = data
    return members


def write_zip(target: Path, members: dict[str, bytes],
              special: Callable[[zipfile.ZipFile], None] | None = None) -> None:
    """Deterministic: sorted entries, fixed timestamps, 0644 regular files."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(members):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, members[path])
        if special is not None:
            special(archive)


def validate_zip(path: Path) -> Report:
    report = Report(f"ZIP {path.name}")
    package = load_zip(path, report)
    if package is not None:
        check_package(package, report)
    return report


def cmd_check(layout: Layout, final: bool, online: bool) -> int:
    report = Report(f"plugin directory {layout.plugin_dir.relative_to(layout.root)}"
                    + (" (final)" if final else "") + (" (online)" if online else ""))
    check_source(layout, report, final, online)
    report.print()
    return 0 if report.ok else 1


def cmd_build(layout: Layout, out: Path | None) -> int:
    source = Report(f"plugin directory {layout.plugin_dir.relative_to(layout.root)}")
    check_source(layout, source, final=False, online=False)
    source.print()
    if not source.ok:
        print("Not building: fix the plugin directory first.")
        return 1
    manifest = json.loads(layout.codex_manifest.read_text(encoding="utf-8"))
    target = (out or layout.dist) / f"{manifest['name']}-{manifest['version']}.zip"
    write_zip(target, zip_members(layout))
    report = validate_zip(target)
    report.print()
    if not report.ok:
        return 1
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    with zipfile.ZipFile(target) as archive:
        names = archive.namelist()
    print(f"Built {target} ({target.stat().st_size} bytes, {len(names)} files)")
    print(f"sha256 {digest}")
    for name in names:
        print(f"  {name}")
    return 0


def cmd_validate_zip(path: Path) -> int:
    report = validate_zip(path)
    report.print()
    return 0 if report.ok else 1


def cmd_sync(layout: Layout) -> int:
    codex = json.loads(layout.codex_manifest.read_text(encoding="utf-8"))
    layout.claude_manifest.parent.mkdir(parents=True, exist_ok=True)
    layout.claude_manifest.write_text(json.dumps(derived_claude_manifest(codex), indent=2,
                                                 ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {layout.claude_manifest.relative_to(layout.root)}")
    return 0


def cmd_rules() -> int:
    width = max(len(rule) for rule in RULES)
    for rule, (what, source) in RULES.items():
        print(f"{rule:<{width}}  {what}\n{'':<{width}}  source: {source}")
    return 0


# -- rename: one command for the names that appear in several files ---------------------

URL_OR_REPO = r"https?://[^\s)\"'>\]]+"


def rename_text(text: str, pairs: list[tuple[str, str]], protected: list[str],
                slug_pair: tuple[str, str]) -> str:
    """Replace human-facing names outside URLs and protected tokens; the slug everywhere."""
    pattern = re.compile("(" + "|".join([URL_OR_REPO] + [re.escape(p) for p in protected if p]) + ")")
    pieces = pattern.split(text)
    for index, piece in enumerate(pieces):
        if index % 2 == 1:
            continue
        for old, new in pairs:
            piece = piece.replace(old, new)
        pieces[index] = piece
    return "".join(pieces).replace(slug_pair[0], slug_pair[1])


def cmd_rename(layout: Layout, slug: str, display: str, developer: str | None,
               extra: list[str], repo: str | None, dry_run: bool) -> int:
    manifest = json.loads(layout.codex_manifest.read_text(encoding="utf-8"))
    old_slug, old_display = manifest["name"], manifest["interface"]["displayName"]
    old_developer = manifest["interface"].get("developerName")
    problems = []
    if not KEBAB.match(slug) or len(slug) > 64:
        problems.append("slug must be lowercase letters, digits and single hyphens (max 64)")
    if not display.strip() or len(display) > 30 or "\n" in display:
        problems.append("display name must be one line of at most 30 characters")
    if developer is not None and (not developer.strip() or len(developer) > 80):
        problems.append("developer name must be at most 80 characters")
    if problems:
        for problem in problems:
            print(f"error: {problem}")
        return 2

    pairs = [(old_display, display)]
    if developer and old_developer:
        pairs.append((old_developer, developer))
    for item in extra:
        old, _, new = item.partition("=")
        if not old or not new:
            print(f"error: --also expects OLD=NEW, got {item!r}")
            return 2
        pairs.append((old, new))
    repository = manifest.get("repository", "")
    owner_repo = repository.removeprefix("https://github.com/")
    protected = [owner_repo] if owner_repo != repository else []

    targets = [layout.codex_manifest, layout.plugin_dir / "README.md",
               layout.plugin_dir / "SECURITY.md", layout.listing, layout.script,
               *sorted(layout.legal_dir.glob("*.md"))]
    changes: list[tuple[Path, str]] = []
    for path in targets:
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        if path == layout.codex_manifest:
            data = json.loads(original)

            def walk(value: object) -> object:
                if isinstance(value, str):
                    return rename_text(value, pairs, protected, (old_slug, slug))
                if isinstance(value, list):
                    return [walk(item) for item in value]
                if isinstance(value, dict):
                    return {key: walk(item) for key, item in value.items()}
                return value

            data = walk(data)
            if developer:
                data["author"]["name"] = developer
                data["interface"]["developerName"] = developer
            updated = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        elif path == layout.script:
            updated = original.replace(f'PLUGIN_SLUG = "{old_slug}"', f'PLUGIN_SLUG = "{slug}"')
        else:
            updated = rename_text(original, pairs, protected, (old_slug, slug))
        if repo:
            updated = updated.replace(f"github.com/{owner_repo}", f"github.com/{repo}")
            if path != layout.codex_manifest:
                updated = updated.replace(owner_repo, repo)
        if updated != original:
            changes.append((path, updated))

    print(f"rename {old_slug!r} -> {slug!r}, {old_display!r} -> {display!r}")
    for path, _ in changes:
        print(f"  edit {path.relative_to(layout.root)}")
    new_dir = layout.plugin_dir.with_name(slug)
    if slug != old_slug:
        print(f"  move {layout.plugin_dir.relative_to(layout.root)} -> {new_dir.relative_to(layout.root)}")
    if dry_run:
        print("dry run: nothing written")
        return 0
    for path, updated in changes:
        path.write_text(updated, encoding="utf-8")
    if slug != old_slug:
        if (layout.root / ".git").exists() and shutil.which("git"):
            subprocess.run(["git", "-C", str(layout.root), "mv", str(layout.plugin_dir), str(new_dir)],
                           check=True)
        else:
            layout.plugin_dir.rename(new_dir)
    new_layout = Layout(layout.root, slug)
    cmd_sync(new_layout)
    print("Now update the marketplace entries (.agents/plugins/marketplace.json and "
          ".claude-plugin/marketplace.json) and run `check`.")
    return cmd_check(new_layout, final=False, online=False)


# -- selftest: every rule the validator claims, shown failing on purpose ----------------


def _set(manifest: dict, path: str, value: object) -> dict:
    """Set a nested key. Path segments are separated by '/', because 'com.openai' is one key."""
    target = manifest
    keys = path.split("/")
    for key in keys[:-1]:
        target = target.setdefault(key, {})
    target[keys[-1]] = value
    return manifest


def selftest(layout: Layout) -> int:
    base_members = zip_members(layout)
    base_manifest = json.loads(base_members[".codex-plugin/plugin.json"])
    skill = "skills/evidence-before-done/SKILL.md"
    skill_text = base_members[skill].decode("utf-8")
    tiny_svg = (b'<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" '
                b'viewBox="0 0 32 32"><rect width="32" height="32"/></svg>')

    def png(width: int, height: int) -> bytes:
        def chunk(kind: bytes, body: bytes) -> bytes:
            return (len(body).to_bytes(4, "big") + kind + body
                    + (zlib.crc32(kind + body) & 0xFFFFFFFF).to_bytes(4, "big"))
        rows = b"".join(b"\x00" + b"\x00\x00\x00\x00" * width for _ in range(height))
        header = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
        return (PNG_SIGNATURE + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(rows))
                + chunk(b"IEND", b""))

    def with_manifest(change: Callable[[dict], object]) -> Callable[[dict[str, bytes]], None]:
        def apply(members: dict[str, bytes]) -> None:
            manifest = json.loads(json.dumps(base_manifest))
            change(manifest)
            members[".codex-plugin/plugin.json"] = json.dumps(manifest).encode()
        return apply

    def add(path: str, data: bytes) -> Callable[[dict[str, bytes]], None]:
        return lambda members: members.__setitem__(path, data)

    def skill_edit(old: str, new: str) -> Callable[[dict[str, bytes]], None]:
        return lambda members: members.__setitem__(skill, skill_text.replace(old, new, 1).encode())

    def raw_entry(name: str, data: bytes = b"x", mode: int = stat.S_IFREG | 0o644):
        def special(archive: zipfile.ZipFile) -> None:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = mode << 16
            archive.writestr(info, data)
        return special

    long_text = "x" * 4001
    cases: list[tuple[str, str, Callable[[dict[str, bytes]], None] | None, Callable | None]] = [
        ("baseline", "", None, None),
        ("hooks file", "NO-HOOKS", add("hooks/hooks.json", b'{"hooks": {}}'), None),
        ("hooks key", "NO-HOOKS", with_manifest(lambda m: m.__setitem__("hooks", {})), None),
        ("extension hooks", "NO-HOOKS", with_manifest(lambda m: _set(m, "extensions/com.openai/hooks", "./hooks/hooks.json")), None),
        ("mcp file", "NO-MCP", add(".mcp.json", b'{"mcpServers": {}}'), None),
        ("mcp key", "NO-MCP", with_manifest(lambda m: m.__setitem__("mcpServers", "./.mcp.json")), None),
        ("app file", "NO-APPS", add(".app.json", b'{"apps": {}}'), None),
        ("apps key", "NO-APPS", with_manifest(lambda m: m.__setitem__("apps", "./.app.json")), None),
        ("screenshots", "NO-SCREENSHOTS", with_manifest(lambda m: _set(m, "interface/screenshots", [])), None),
        ("local executor", "NO-LOCAL-EXECUTOR", with_manifest(lambda m: m.__setitem__("requires_local_executor", True)), None),
        ("shell script", "NO-EXECUTABLES", add("skills/evidence-before-done/scripts/run.sh", b"echo hi\n"), None),
        ("exec bit", "NO-EXECUTABLES", None, raw_entry("assets/tool", b"x", stat.S_IFREG | 0o755)),
        ("claude command", "NO-CLAUDE-ONLY", add("commands/go.md", b"---\ndescription: x\n---\nx\n"), None),
        ("claude manifest in zip", "ZIP-ONE-MANIFEST", add(".claude-plugin/plugin.json", b"{}"), None),
        ("secret", "NO-SECRETS", add("assets/notes.txt", b"token ghp_" + b"a" * 36), None),
        ("env file", "NO-SECRETS", add(".env", b"KEY=1\n"), None),
        ("review credentials", "NO-REVIEW-CREDENTIALS", with_manifest(lambda m: _set(m, "extensions/com.openai/review/test_credentials", "x")), None),
        ("ds_store", "NO-OS-JUNK", add("assets/.DS_Store", b"\x00"), None),
        ("placeholder", "NO-PLACEHOLDERS", add("README.md", base_members["README.md"] + b"\nMail {{SUPPORT_EMAIL}}\n"), None),
        ("name format", "NAME", with_manifest(lambda m: m.__setitem__("name", "Truthstone_Practices")), None),
        ("version", "VERSION", with_manifest(lambda m: m.__setitem__("version", "1.0")), None),
        ("description length", "DESCRIPTION", with_manifest(lambda m: m.__setitem__("description", "x" * 1025)), None),
        ("author", "AUTHOR", with_manifest(lambda m: m.__setitem__("author", {"name": "x", "url": "http://x.test"})), None),
        ("homepage", "HOMEPAGE", with_manifest(lambda m: m.__setitem__("homepage", "http://x.test")), None),
        ("skills path", "SKILLS-PATH", with_manifest(lambda m: m.__setitem__("skills", "./other/")), None),
        ("display name length", "DISPLAY-NAME", with_manifest(lambda m: _set(m, "interface/displayName", "x" * 31)), None),
        ("display name suffix", "DISPLAY-NAME", with_manifest(lambda m: _set(m, "interface/displayName", "Guard Plugin")), None),
        ("short description", "SHORT-DESCRIPTION", with_manifest(lambda m: _set(m, "interface/shortDescription", "x" * 31)), None),
        ("long description", "LONG-DESCRIPTION", with_manifest(lambda m: _set(m, "interface/longDescription", long_text)), None),
        ("developer name", "DEVELOPER-NAME", with_manifest(lambda m: _set(m, "interface/developerName", "x" * 81)), None),
        ("category", "CATEGORY", with_manifest(lambda m: _set(m, "interface/category", "Dev Tools")), None),
        ("capability count", "CAPABILITIES", with_manifest(lambda m: _set(m, "interface/capabilities", ["c"] * 21)), None),
        ("capability length", "CAPABILITIES", with_manifest(lambda m: _set(m, "interface/capabilities", ["x" * 121])), None),
        ("prompt count", "DEFAULT-PROMPT", with_manifest(lambda m: _set(m, "interface/defaultPrompt", ["a", "b", "c", "d"])), None),
        ("prompt length", "DEFAULT-PROMPT", with_manifest(lambda m: _set(m, "interface/defaultPrompt", ["x" * 129])), None),
        ("prompt duplicate", "DEFAULT-PROMPT", with_manifest(lambda m: _set(m, "interface/defaultPrompt", ["Check this", "check   THIS"])), None),
        ("prompt mention", "DEFAULT-PROMPT", with_manifest(lambda m: _set(m, "interface/defaultPrompt", ["Ask @notes to help"])), None),
        ("url scheme", "LISTING-URLS", with_manifest(lambda m: _set(m, "interface/privacyPolicyURL", "http://x.test/p")), None),
        ("url missing", "LISTING-URLS", with_manifest(lambda m: m["interface"].pop("supportURL")), None),
        ("brand contrast", "BRAND-COLOR", with_manifest(lambda m: _set(m, "interface/brandColor", "#EEEEEE")), None),
        ("dark contrast", "BRAND-COLOR", with_manifest(lambda m: _set(m, "interface/brandColorDark", "#303030")), None),
        ("asset prefix", "ASSET-PATH", with_manifest(lambda m: _set(m, "interface/logo", "assets/logo.svg")), None),
        ("asset missing", "ASSET-PATH", with_manifest(lambda m: _set(m, "interface/logo", "./assets/none.svg")), None),
        ("asset escape", "ASSET-PATH", with_manifest(lambda m: _set(m, "interface/logo", "./../logo.svg")), None),
        ("logo required", "ASSET-PATH", with_manifest(lambda m: m["interface"].pop("logo")), None),
        ("svg too small", "IMAGE", add("assets/logo.svg", tiny_svg), None),
        ("svg units", "IMAGE", add("assets/logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg" width="64px" height="64px"/>'), None),
        ("svg not square", "IMAGE", add("assets/logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 48"/>'), None),
        ("svg script", "IMAGE", add("assets/logo.svg", b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><script>x()</script></svg>'), None),
        ("png not square", "IMAGE", lambda m: (m.__setitem__("assets/p.png", png(64, 48)),
                                               m.__setitem__(".codex-plugin/plugin.json", json.dumps(_set(json.loads(json.dumps(base_manifest)), "interface/logo", "./assets/p.png")).encode())), None),
        ("png too small", "IMAGE", lambda m: (m.__setitem__("assets/p.png", png(32, 32)),
                                              m.__setitem__(".codex-plugin/plugin.json", json.dumps(_set(json.loads(json.dumps(base_manifest)), "interface/logo", "./assets/p.png")).encode())), None),
        ("png wrong extension", "IMAGE", lambda m: (m.__setitem__("assets/p.jpg", png(64, 64)),
                                                    m.__setitem__(".codex-plugin/plugin.json", json.dumps(_set(json.loads(json.dumps(base_manifest)), "interface/logo", "./assets/p.jpg")).encode())), None),
        ("control character", "TEXT", with_manifest(lambda m: _set(m, "interface/shortDescription", "Verify​work")), None),
        ("extensions key", "EXTENSIONS", with_manifest(lambda m: _set(m, "extensions/com.openai/surprise", 1)), None),
        ("superlative", "LISTING-COPY", with_manifest(lambda m: _set(m, "interface/shortDescription", "The best checks")), None),
        ("percentage", "LISTING-COPY", with_manifest(lambda m: _set(m, "interface/longDescription", "Catches 98% of bugs.")), None),
        ("guarantee", "LISTING-COPY", with_manifest(lambda m: _set(m, "description", "Guaranteed correct code.")), None),
        ("no skills", "SKILLS-PRESENT", lambda m: [m.pop(k) for k in [k for k in m if k.startswith("skills/")]], None),
        ("loose skill file", "SKILL-LAYOUT", add("skills/README.md", b"x"), None),
        ("hidden skill", "SKILL-LAYOUT", add("skills/.hidden/SKILL.md", b"---\nname: hidden\ndescription: x\n---\nx\n"), None),
        ("nested skill", "SKILL-LAYOUT", add("skills/outer/inner/SKILL.md", b"---\nname: inner\ndescription: x\n---\nx\n"), None),
        ("no front matter", "SKILL-FRONTMATTER", skill_edit("---\nname:", "name:"), None),
        ("bad yaml", "SKILL-FRONTMATTER", skill_edit("license: Apache-2.0", "license: Apache: 2"), None),
        ("name mismatch", "SKILL-NAME", skill_edit("name: evidence-before-done", "name: evidence-first"), None),
        ("description missing", "SKILL-DESCRIPTION", lambda m: m.__setitem__(skill, re.sub(r"description: [^\n]*\n", "", skill_text, count=1).encode()), None),
        ("description too long", "SKILL-DESCRIPTION", lambda m: m.__setitem__(skill, re.sub(r"description: [^\n]*\n", "description: " + "y" * 1025 + "\n", skill_text, count=1).encode()), None),
        ("empty body", "SKILL-BODY", lambda m: m.__setitem__(skill, skill_text.split("\n---\n", 1)[0].encode() + b"\n---\n\n"), None),
        ("identity too long", "SKILL-IDENTITY", add("skills/" + "a" * 50 + "/SKILL.md", ("---\nname: " + "a" * 50 + "\ndescription: x\n---\nThe user's explicit instructions take priority.\n").encode()), None),
        ("inline command", "SKILL-NO-COMMAND-INJECTION", skill_edit("## Never", "Context: !`git status`\n\n## Never"), None),
        ("risky literal", "SKILL-NO-RISKY-LITERALS", skill_edit("## Never", "Run `rm -rf build` first.\n\n## Never"), None),
        ("provider name", "SKILL-NEUTRAL", skill_edit("## Never", "Claude should do this.\n\n## Never"), None),
        ("priority line", "SKILL-PRIORITY", lambda m: m.__setitem__(skill, re.sub(r"\nThe user's explicit instructions[^\n]*\n", "\n", skill_text).encode()), None),
        ("agent metadata", "SKILL-AGENT-METADATA", add("skills/evidence-before-done/agents/openai.yaml", b"interface:\n  short_description: x\n"), None),
        ("agent dependency", "SKILL-AGENT-METADATA", add("skills/evidence-before-done/agents/openai.yaml", b'interface:\n  display_name: "x"\n  short_description: "y"\ndependencies:\n  tools: []\n'), None),
        ("readme short", "README", add("README.md", b"# Tiny\n\nToo short.\n"), None),
        ("license missing", "LICENSE", lambda m: m.pop("LICENSE"), None),
        ("big file", "FILE-LIMITS", add("assets/big.txt", b"x" * (256 * 1024 + 1)), None),
        ("dotdot entry", "ZIP-PATH", None, raw_entry("../evil.txt")),
        ("backslash entry", "ZIP-PATH", None, raw_entry("assets\\evil.txt")),
        ("absolute entry", "ZIP-PATH", None, raw_entry("/etc/evil.txt")),
        ("case collision", "ZIP-PATH", None, raw_entry("readme.MD")),
        ("deep entry", "ZIP-PATH", None, raw_entry("/".join(["d"] * 21) + "/f.txt")),
        ("symlink entry", "ZIP-ENTRY-TYPE", None, raw_entry("assets/link", b"../../etc/passwd", stat.S_IFLNK | 0o777)),
        ("sibling outside root", "ZIP-ROOT", lambda m: m.update({f"plugin/{k}": m.pop(k) for k in list(m)} | {"stray.txt": b"x"}), None),
    ]

    failures = 0
    with tempfile.TemporaryDirectory() as scratch:
        for index, (label, expected, mutate, special) in enumerate(cases):
            members = dict(base_members)
            if mutate is not None:
                mutate(members)
            target = Path(scratch) / f"case-{index}.zip"
            write_zip(target, members, special)
            report = validate_zip(target)
            hit = report.rules_hit()
            if expected == "":
                passed = report.ok
                detail = "clean" if passed else f"unexpected findings: {sorted(hit)}"
            else:
                passed = expected in hit
                detail = f"caught by {expected}" if passed else f"NOT caught; got {sorted(hit) or 'nothing'}"
            failures += not passed
            print(f"{'ok  ' if passed else 'FAIL'} {label:<24} {detail}")

    # rename, against a scratch copy of the repository files it touches
    with tempfile.TemporaryDirectory() as scratch:
        copy = Path(scratch)
        shutil.copytree(layout.plugin_dir, copy / "plugins" / layout.slug)
        (copy / "docs").mkdir()
        if layout.legal_dir.is_dir():
            shutil.copytree(layout.legal_dir, copy / "docs" / "legal")
        if layout.listing.is_file():
            shutil.copy2(layout.listing, copy / "docs" / "LISTING.md")
        (copy / "scripts").mkdir()
        shutil.copy2(layout.script, copy / "scripts" / "companion_package.py")
        scratch_layout = Layout(copy, layout.slug)
        with open(os.devnull, "w") as quiet:
            stdout = sys.stdout
            sys.stdout = quiet
            try:
                code = cmd_rename(scratch_layout, "renamed-practices", "Renamed Practices", None, [], None, False)
            finally:
                sys.stdout = stdout
        renamed = Layout(copy, "renamed-practices")
        manifest = json.loads(renamed.codex_manifest.read_text(encoding="utf-8"))
        script = renamed.script.read_text(encoding="utf-8")
        passed = (code == 0 and manifest["name"] == "renamed-practices"
                  and manifest["interface"]["displayName"] == "Renamed Practices"
                  and 'PLUGIN_SLUG = "renamed-practices"' in script
                  and not (copy / "plugins" / layout.slug).exists()
                  and "Renamed Practices" in (renamed.plugin_dir / "README.md").read_text(encoding="utf-8")
                  and "github.com/tohin003/Truthstone" in renamed.codex_manifest.read_text(encoding="utf-8"))
        failures += not passed
        print(f"{'ok  ' if passed else 'FAIL'} {'rename round trip':<24} "
              f"{'names rewritten, URLs kept, checks pass' if passed else 'rename did not round-trip'}")

    total = len(cases) + 1
    print(f"\nselftest: {total - failures}/{total} passed")
    return 0 if failures == 0 else 1


# -- entry point -------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="validate the plugin directory")
    check.add_argument("--final", action="store_true", help="also require docs/legal without placeholders")
    check.add_argument("--online", action="store_true", help="also fetch every listing URL")
    build = sub.add_parser("build", help="build and validate the submission ZIP")
    build.add_argument("--out", type=Path, help="output directory (default dist/companion)")
    validate = sub.add_parser("validate-zip", help="validate an existing ZIP")
    validate.add_argument("zip", type=Path)
    sub.add_parser("sync", help="regenerate .claude-plugin/plugin.json")
    rename = sub.add_parser("rename", help="rename the plugin everywhere its names appear")
    rename.add_argument("--slug", required=True)
    rename.add_argument("--display", required=True)
    rename.add_argument("--developer", help="new developer/author name")
    rename.add_argument("--also", action="append", default=[], metavar="OLD=NEW",
                        help="extra text replacement outside URLs (repeatable)")
    rename.add_argument("--repo", metavar="OWNER/REPO", help="rewrite GitHub URLs to a renamed repository")
    rename.add_argument("--dry-run", action="store_true")
    sub.add_parser("rules", help="list every rule and its source")
    sub.add_parser("selftest", help="prove each rule rejects a violating package")
    args = parser.parse_args(argv)

    layout = Layout(ROOT)
    if args.command == "check":
        return cmd_check(layout, args.final, args.online)
    if args.command == "build":
        return cmd_build(layout, args.out)
    if args.command == "validate-zip":
        return cmd_validate_zip(args.zip)
    if args.command == "sync":
        return cmd_sync(layout)
    if args.command == "rename":
        return cmd_rename(layout, args.slug, args.display, args.developer, args.also, args.repo, args.dry_run)
    if args.command == "rules":
        return cmd_rules()
    if args.command == "selftest":
        return selftest(layout)
    return 2


if __name__ == "__main__":
    sys.exit(main())
