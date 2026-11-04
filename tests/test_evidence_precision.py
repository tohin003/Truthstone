"""Evidence-engine precision: names that exist must never be challenged (E1).

Two false positives were verified against real code, and replaying a second real
repository found two more of the same family:

* `from pkg import Thing` was challenged when `pkg/__init__.py` re-exported it with
  `from .impl import *` (the `*` was recorded as a name and never followed);
* names bound by unpacking (`LOW, HIGH = 1, 10`, `self.a, self.b = a, b`) were
  invisible, as were `for`/`with`/`:=` targets at module and class level;
* `from .impl import Thing as Public` recorded `Thing`, never `Public`;
* `from .models import X` was checked against a top-level `models` module rather than
  the importer's own package.

Each test pairs the fix with a hallucination next to it that must still be caught, so
precision is not bought with recall. Undecidable modules (a computed `__all__`, PEP 562
`__getattr__`, namespace writes, unresolvable or too-deep stars) make no claim at all.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from agentguard import evidence
from agentguard.core.enums import EventType, Verdict
from agentguard.core.events import AgentEvent
from agentguard.repo import RepoIndex, symbols_python


def _repo(root: Path, files: dict[str, str]) -> RepoIndex:
    (root / "pyproject.toml").parent.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text('[project]\nname = "lab"\ndependencies = []\n')
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
    return RepoIndex(root).build()


def _challenged(index: RepoIndex, path: str, content: str) -> set[str]:
    """Subjects of the challenge-level findings a fresh Write of `content` produces."""
    event = AgentEvent(
        event=EventType.PRE_TOOL_USE,
        agent="claude-code",
        workspace=str(index.root),
        session_id="s1",
        tool="Write",
        arguments={"file_path": path, "content": textwrap.dedent(content)},
    )
    return {
        finding.subject
        for finding in evidence.check(event, index)
        if finding.verdict == Verdict.CONTRADICTED
    }


@pytest.fixture
def lab(tmp_path) -> Path:
    return tmp_path / "lab"


# -- star re-exports ------------------------------------------------------------------------


def test_star_reexport_supported(lab):
    index = _repo(
        lab,
        {
            "src/shop/__init__.py": "",
            "src/shop/models/__init__.py": "from .impl import *\nfrom shop.models.more import *\n",
            "src/shop/models/impl.py": """
                class Thing:
                    pass

                def helper():
                    return 1

                def _private():
                    return 2
            """,
            "src/shop/models/more.py": "VERSION = 3\n",
        },
    )

    assert _challenged(index, "src/shop/api.py", "from shop.models import Thing, helper, VERSION\n") == set()
    # Still caught: a name no star brings in, and a private one (`import *` skips it).
    assert _challenged(index, "src/shop/api.py", "from shop.models import Missing\n") == {"Missing"}
    assert _challenged(index, "src/shop/api.py", "from shop.models import _private\n") == {"_private"}


def test_star_chains_are_followed_up_to_the_depth_bound(lab):
    files = {"src/chain/__init__.py": ""}
    for i in range(12):
        nxt = f"from .m{i + 1} import *\n" if i < 11 else "DEEP = 1\n"
        files[f"src/chain/m{i}.py"] = nxt
    index = _repo(lab, files)

    # Three hops resolve completely: found, and a hallucination beside it is caught.
    assert _challenged(index, "src/chain/api.py", "from chain.m8 import DEEP\n") == set()
    assert _challenged(index, "src/chain/api.py", "from chain.m8 import NOPE\n") == {"NOPE"}
    # Eleven hops pass the bound of 8: undecidable, so no claim either way.
    assert _challenged(index, "src/chain/api.py", "from chain.m0 import NOPE\n") == set()


def test_unresolvable_or_cyclic_stars_are_undecidable(lab):
    index = _repo(
        lab,
        {
            "src/pkg/__init__.py": "",
            "src/pkg/ext.py": "from os.path import *\n",
            "src/pkg/a.py": "from .b import *\nA = 1\n",
            "src/pkg/b.py": "from .a import *\nB = 1\n",
        },
    )

    assert _challenged(index, "src/pkg/api.py", "from pkg.ext import anything\n") == set()
    assert _challenged(index, "src/pkg/api.py", "from pkg.a import anything\n") == set()


# -- `__all__` and PEP 562 --------------------------------------------------------------------


def test_literal_all_decides(lab):
    index = _repo(
        lab,
        {
            "src/pkg/__init__.py": "from .impl import *\n",
            "src/pkg/impl.py": """
                __all__ = ["Thing", "_exported_private"]

                class Thing:
                    pass

                def helper():
                    return 1

                def _exported_private():
                    return 2
            """,
        },
    )

    assert _challenged(index, "src/api.py", "from pkg import Thing, _exported_private\n") == set()
    # `helper` is public but not in `__all__`, so `import *` does not bring it in.
    assert _challenged(index, "src/api.py", "from pkg import helper\n") == {"helper"}
    # `__all__` only shapes `import *`: importing from impl directly still works.
    assert _challenged(index, "src/api.py", "from pkg.impl import helper\n") == set()


@pytest.mark.parametrize(
    "all_source",
    [
        '__all__ = ["Thing"] + ["helper"]\n',
        '__all__ = ["Thing"]\n__all__ += ["helper"]\n',
        '__all__ = ["Thing"]\n__all__.extend(["helper"])\n',
        'if True:\n    __all__ = ["Thing"]\n',
        'from .names import __all__\n',
        '__all__ = ["Thing"]\n__all__ = ["Other"]\n',
    ],
    ids=["computed", "augmented", "extended", "conditional", "imported", "reassigned"],
)
def test_computed_all_is_undecidable(lab, all_source):
    index = _repo(
        lab,
        {
            "src/pkg/__init__.py": "from .impl import *\n",
            "src/pkg/names.py": '__all__ = ["Thing"]\n',
            "src/pkg/impl.py": all_source + "\nclass Thing:\n    pass\n",
        },
    )

    assert _challenged(index, "src/api.py", "from pkg import Invented\n") == set()


def test_module_getattr_undecidable(lab):
    index = _repo(
        lab,
        {
            "src/lazy/__init__.py": """
                def __getattr__(name):
                    import importlib
                    return importlib.import_module(f"lazy._{name}")
            """,
            "src/lazy2/__init__.py": """
                import lazy_loader as lazy

                __getattr__, __dir__, __all__ = lazy.attach(__name__, ["thing"])
            """,
            "src/plain/__init__.py": "VALUE = 1\n",
        },
    )

    assert _challenged(index, "src/api.py", "from lazy import anything\n") == set()
    assert _challenged(index, "src/api.py", "from lazy2 import anything\n") == set()
    assert _challenged(index, "src/api.py", "from plain import anything\n") == {"anything"}


@pytest.mark.parametrize(
    "writer",
    [
        'globals()["Generated"] = 1\n',
        "globals().update({'Generated': 1})\n",
        "import sys\nsetattr(sys.modules[__name__], 'Generated', 1)\n",
        "exec('Generated = 1')\n",
    ],
    ids=["globals-subscript", "globals-update", "sys-modules", "exec"],
)
def test_a_module_that_writes_its_own_namespace_is_undecidable(lab, writer):
    index = _repo(lab, {"src/gen/__init__.py": writer})

    assert _challenged(index, "src/api.py", "from gen import Generated\n") == set()


# -- unpacking and other binding forms --------------------------------------------------------


def test_tuple_constant_supported(lab):
    index = _repo(
        lab,
        {
            "src/limits.py": """
                LOW, HIGH = 1, 10
                [FIRST, *REST] = [1, 2, 3]
                for LOOP in range(1):
                    pass
                with open(__file__) as HANDLE:
                    pass
                if (WALRUS := 5) > 1:
                    pass
                type Alias = int

                def configure():
                    global CONFIGURED
                    CONFIGURED = True
            """,
        },
    )

    names = "LOW, HIGH, FIRST, REST, LOOP, HANDLE, WALRUS, Alias, CONFIGURED"
    assert _challenged(index, "src/api.py", f"from limits import {names}\n") == set()
    assert _challenged(index, "src/api.py", "from limits import MEDIUM\n") == {"MEDIUM"}


def test_unpacked_attributes_are_known(lab):
    index = _repo(
        lab,
        {
            "src/shop/__init__.py": "",
            "src/shop/campaign.py": """
                class Limits:
                    LOW, HIGH = 1, 10

                class Campaign:
                    def __init__(self, command, backend):
                        self.command, self.backend = command, backend
                        self.checks, (self.names, *self.rest) = [], (set(), 1)
            """,
        },
    )

    supported = """
        from shop.campaign import Campaign, Limits

        def run(command, backend):
            campaign = Campaign(command, backend)
            campaign.checks.append(Limits.LOW + Limits.HIGH)
            return campaign.backend, campaign.names, campaign.rest
    """
    assert _challenged(index, "src/shop/api.py", supported) == set()
    invented = """
        from shop.campaign import Campaign, Limits

        def run(command, backend):
            return Campaign(command, backend).observations, Limits.MEDIUM
    """
    assert _challenged(index, "src/shop/api.py", invented) == {"Campaign.observations", "Limits.MEDIUM"}


def test_class_defined_in_the_edit_counts_unpacked_attributes(lab):
    """The same binding forms in the file being written (`pyanalysis`), not the index."""
    index = _repo(lab, {"src/other.py": "X = 1\n"})

    content = textwrap.dedent(
        """
        class Limits:
            LOW, HIGH = 1, 10
            for STEP in range(1):
                pass

        class Pair:
            def __init__(self, a, b):
                self.left, self.right = a, b

        def go():
            return Limits.LOW, Limits.HIGH, Limits.STEP, Pair(1, 2).left, Pair(1, 2).right
        """
    )
    assert _challenged(index, "src/new.py", content) == set()
    assert _challenged(index, "src/new.py", content + "\nVALUE = Limits.MEDIUM\n") == {"Limits.MEDIUM"}


# -- aliases and relative imports -------------------------------------------------------------


def test_aliased_reexport_supported(lab):
    index = _repo(
        lab,
        {
            "src/pkg/__init__.py": "from .impl import Thing as PublicThing\nimport json as codec\n",
            "src/pkg/impl.py": "class Thing:\n    pass\n",
        },
    )

    assert _challenged(index, "src/api.py", "from pkg import PublicThing, codec\n") == set()
    assert _challenged(index, "src/api.py", "from pkg import PrivateThing\n") == {"PrivateThing"}


def test_relative_import_resolves_against_its_own_package(lab):
    index = _repo(
        lab,
        {
            "src/models.py": "class Unrelated:\n    pass\n",
            "src/shop/__init__.py": "from .billing import models as billing_models\n",
            "src/shop/billing/__init__.py": "",
            "src/shop/billing/models.py": "class Invoice:\n    pass\n",
        },
    )

    path = "src/shop/billing/api.py"
    assert _challenged(index, path, "from .models import Invoice\nfrom . import models\n") == set()
    assert _challenged(index, path, "from ..billing.models import Invoice\n") == set()
    assert _challenged(index, path, "from .models import Receipt\n") == {"Receipt"}
    # A relative module that does not resolve (no such sibling) is not knowable here.
    assert _challenged(index, path, "from .ledger import Entry\n") == set()


# -- the extractor directly -------------------------------------------------------------------


def test_extractor_reports_bindings_and_exports():
    source = textwrap.dedent(
        """
        from .impl import Thing as Public, other
        from .stars import *
        import pkg.sub as alias, os.path
        __all__ = ["Public", "other"]
        A, (B, *C) = 1, (2, 3)
        """
    )
    symbols, imports, clean, exports = symbols_python.extract_module(source, "pkg/__init__.py")

    assert clean
    assert {s.name for s in symbols if s.parent is None} >= {"A", "B", "C", "__all__"}
    assert [record.bound for record in imports] == [["Public", "other"], [], ["alias"], ["os"]]
    assert imports[1].is_star
    assert exports is not None
    assert exports.all_names == ("Public", "other")
    assert not (exports.all_dynamic or exports.getattr_hook or exports.dynamic_namespace)
    # The historical 3-tuple API is unchanged.
    assert symbols_python.extract(source, "pkg/__init__.py") == (symbols, imports, True)
    assert symbols_python.extract_module("def broken(:\n", "x.py") == ([], [], False, None)
