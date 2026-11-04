"""Mutation benchmark: does the evidence engine actually detect hallucinations?

The live benchmark could not answer this. Thirty agent sessions produced three
"hallucinations", all of them artefacts of a broken oracle, because a capable model
would not take the bait. Measuring a detector by waiting for an agent to make mistakes is
a bad experiment: it measures the agent, and it costs a quota.

So measure the detector directly. Take real code that works, introduce a hallucination
programmatically, and ask Truthstone whether it notices:

    recall    = seeded hallucinations flagged / seeded hallucinations
    precision = real flags / all flags   (the unmutated file must stay silent)

Zero agent sessions, hundreds of cases instead of thirty, and every case has a known
ground truth because the mutation is what created it.

**The mutations are only the ones Truthstone could in principle catch** — a reference to
something that genuinely does not exist in the repository. That is a real limit on what
this measures: it reports how well the detector finds what it was designed to find, not
how often agents hallucinate in ways it was never built for. Stated here rather than
discovered by a reader.

Two corrections from the Stage 1 audit (IMPROVEMENTS.md M4):

* **Precision was vacuous.** It re-wrote each clean file with its own content, and the
  engine only checks claims an edit *introduces*, so 0 claims were checked and a false
  positive was impossible. Precision is now measured by a *fresh-file replay*: each clean
  file's content is written as a new module beside it, so every claim in it is new and
  checked. The number of claims checked is reported, and precision is refused when it is 0.
* **The sample was self-selected**: the first 400 sites in index order (one file supplied
  63). Sites are now drawn at random with a fixed seed, at most ``per_file`` per file, and
  recall is reported per kind, including instance-attribute sites (``self.x``) — the
  SPEC §14 case the old sample never contained.
"""

from __future__ import annotations

import ast
import random
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from truthstone.core.enums import EventType
from truthstone.core.events import AgentEvent
from truthstone.evidence import check as evidence_check
from truthstone.evidence import extractors
from truthstone.repo.index import RepoIndex


@dataclass(slots=True)
class Mutation:
    path: str
    kind: str
    original: str
    mutated: str
    subject: str  # the hallucinated name the detector should flag


@dataclass(slots=True)
class Result:
    total: int = 0
    caught: int = 0
    missed: list[Mutation] = None  # type: ignore[assignment]
    # Fresh-file replay of the unmutated files (precision).
    false_positives: int = 0  # findings raised on real, working code
    false_positive_files: int = 0
    clean_files: int = 0
    clean_claims: int = 0  # claims the replay actually checked; 0 means precision is unmeasured
    by_kind: dict[str, list[int]] = field(default_factory=dict)  # kind -> [total, caught]
    files_sampled: int = 0
    false_positive_examples: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.caught / self.total if self.total else 0.0

    @property
    def precision(self) -> float | None:
        """None when no clean claim was checked: a precision over nothing is not 100%."""
        if not self.clean_claims:
            return None
        flags = self.caught + self.false_positives
        return self.caught / flags if flags else 1.0


def _known_types(index: RepoIndex) -> dict[str, set[str]]:
    """Classes whose full attribute set Truthstone can be confident about."""
    out: dict[str, set[str]] = {}
    for name, records in index.symbols_by_name.items():
        for record in records:
            if record.kind == "class" and record.bases_known and index.is_parsed(record.path):
                attrs = index.attributes_of(record.qualname)
                if attrs:
                    out[name] = attrs
    return out


#: Benchmark fixtures and task material are not the code under measurement.
DEFAULT_EXCLUDE = ("bench/", "tests/fixtures/")


def _candidates(
    index: RepoIndex, rng: random.Random, exclude: tuple[str, ...] = DEFAULT_EXCLUDE
) -> dict[str, list[Mutation]]:
    """Every mutation site in the repository, grouped by file."""
    types = _known_types(index)
    by_file: dict[str, list[Mutation]] = {}

    for path, record in index.files.items():
        if record.lang != "python" or record.is_test or not index.is_parsed(path):
            continue
        if path.startswith(exclude):
            continue
        try:
            source = (index.root / path).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, ValueError):
            continue
        sites = by_file.setdefault(path, [])
        lines = source.splitlines(keepends=True)

        # `self.attr` inside a class whose members are fully known: the instance case.
        for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name in types):
            for node in ast.walk(cls):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "self"
                    and node.attr in types[cls.name]
                    and not node.attr.startswith("__")
                ):
                    line = lines[node.lineno - 1]
                    needle = f"self.{node.attr}"
                    if needle not in line:
                        continue
                    invented = f"{node.attr}_{rng.randint(1000, 9999)}_missing"
                    mutated_line = line.replace(needle, f"self.{invented}", 1)
                    mutated = "".join([*lines[: node.lineno - 1], mutated_line, *lines[node.lineno:]])
                    sites.append(Mutation(path, "attribute_on_self", source, mutated, f"self.{invented}"))

        for node in ast.walk(tree):
            # `X.attr` where X is a class we fully understand -> rename attr to something
            # that exists nowhere. A real call site, a genuinely absent member.
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in types
                and node.attr in types[node.value.id]
                and not node.attr.startswith("__")
            ):
                owner = node.value.id
                invented = f"{node.attr}_{rng.randint(1000, 9999)}_missing"
                line = source.splitlines()[node.lineno - 1]
                if f"{owner}.{node.attr}" not in line:
                    continue
                sites.append(
                    Mutation(
                        path=path,
                        kind="attribute_on_type",
                        original=source,
                        mutated=source.replace(f"{owner}.{node.attr}", f"{owner}.{invented}", 1),
                        subject=f"{owner}.{invented}",
                    )
                )

            # `from <real module> import <name that is not there>`
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                if index.resolve_module(node.module) is None or not node.names:
                    continue
                real = node.names[0].name
                invented = f"{real}_{rng.randint(1000, 9999)}_missing"
                sites.append(
                    Mutation(
                        path=path,
                        kind="symbol_exists",
                        original=source,
                        mutated=source.replace(
                            f"import {real}", f"import {invented}", 1
                        ),
                        subject=invented,
                    )
                )

    return {path: sites for path, sites in by_file.items() if sites}


def generate(
    index: RepoIndex,
    limit: int = 400,
    seed: int = 7,
    per_file: int = 5,
    kinds: tuple[str, ...] = ("attribute_on_type", "symbol_exists", "attribute_on_self"),
) -> list[Mutation]:
    """A seeded, stratified sample of mutation sites: at most ``per_file`` per file.

    Files are visited in a shuffled order, one site per file per round, so no single
    module can dominate the sample the way the old index-order prefix let one file supply
    63 of 400 sites.
    """
    rng = random.Random(seed)
    by_file = {
        path: [m for m in sites if m.kind in kinds]
        for path, sites in _candidates(index, rng).items()
    }
    by_file = {path: sites for path, sites in by_file.items() if sites}
    for sites in by_file.values():
        rng.shuffle(sites)
    order = sorted(by_file)
    rng.shuffle(order)
    sample: list[Mutation] = []
    for round_index in range(per_file):
        for path in order:
            if len(sample) >= limit:
                return sample
            if round_index < len(by_file[path]):
                sample.append(by_file[path][round_index])
    return sample


def replay_path(path: str) -> str:
    """Where a clean file is replayed as a brand-new module: beside it, same package."""
    original = PurePosixPath(path)
    return str(original.with_name(f"_agb_replay_{original.stem}{original.suffix}"))


def _event(index: RepoIndex, path: str, content: str) -> AgentEvent:
    return AgentEvent(
        event=EventType.PRE_TOOL_USE,
        agent="bench",
        workspace=str(index.root),
        session_id="mutation",
        tool="Write",
        arguments={"file_path": path, "content": content},
    )


def evaluate(index: RepoIndex, mutations: list[Mutation]) -> Result:
    """Every mutation is a known hallucination; every original is known-clean."""
    result = Result(missed=[])
    seen_clean: set[str] = set()

    for mutation in mutations:
        result.total += 1
        tally = result.by_kind.setdefault(mutation.kind, [0, 0])
        tally[0] += 1
        findings = evidence_check(_event(index, mutation.path, mutation.mutated), index)
        subjects = {f.subject for f in findings}
        bare = mutation.subject.rsplit(".", 1)[-1]
        if any(bare in s or s == mutation.subject for s in subjects):
            result.caught += 1
            tally[1] += 1
        else:
            result.missed.append(mutation)

        # Precision: replay the unmutated file as a *new* module, so every claim in it is
        # new and checked. Re-writing it in place checks nothing (0 new claims), which
        # is how the old benchmark arrived at a vacuous 100%. Counted once per file.
        if mutation.path not in seen_clean:
            seen_clean.add(mutation.path)
            result.clean_files += 1
            event = _event(index, replay_path(mutation.path), mutation.original)
            claims, _ = extractors.claims_for_event(event, index.root)
            result.clean_claims += len(claims)
            flags = evidence_check(event, index)
            if flags:
                result.false_positives += len(flags)
                result.false_positive_files += 1
                result.false_positive_examples.extend(f"{mutation.path}: {f.subject}" for f in flags[:3])

    result.files_sampled = len(seen_clean)
    return result


def render(result: Result) -> str:
    precision = result.precision
    lines = [
        f"Mutation benchmark · {result.total} seeded hallucinations across {result.files_sampled} files "
        "(seeded, stratified sample)",
        "",
        f"  recall     {result.recall * 100:5.1f}%   ({result.caught}/{result.total} caught)",
    ]
    for kind, (total, caught) in sorted(result.by_kind.items()):
        lines.append(f"    {kind:<20}{caught}/{total}  ({caught / total * 100:5.1f}%)")
    if precision is None:
        lines.append("  precision  not measured: the clean replay checked 0 claims")
    else:
        lines.append(
            f"  precision  {precision * 100:5.1f}%   ({result.false_positives} false positive(s) over "
            f"{result.clean_claims} claims in {result.clean_files} clean files, fresh-file replay)"
        )
    lines.append("")
    if result.false_positive_examples:
        lines.append("false positives on real code:")
        lines.extend(f"  {example}" for example in result.false_positive_examples[:5])
        lines.append("")
    if result.missed:
        lines.append("examples of what it missed:")
        for mutation in result.missed[:5]:
            lines.append(f"  {mutation.path}: {mutation.subject} ({mutation.kind})")
    return "\n".join(lines)


def run(repo: Path, limit: int = 400, seed: int = 7, per_file: int = 5) -> Result:
    index = RepoIndex(repo).build()
    mutations = generate(index, limit=limit, seed=seed, per_file=per_file)
    return evaluate(index, mutations)
