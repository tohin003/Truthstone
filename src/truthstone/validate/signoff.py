"""Developer sign-off the agent cannot give itself (IMPROVEMENTS.md A1b).

A1 made an irreversible action ask every time: Truthstone cannot see whether the developer
said yes, so it never assumes they did. Where the host has a native ask (Claude Code) the
ask *is* the sign-off. Where the host's ask fails open (Codex 0.166) the ladder renders the
sign-off as a deny telling the agent to ask the user and re-run — and the re-run was denied
again, every time. The instruction was false: an irreversible command could never run
under a Codex agent, even after the developer said yes.

What was missing is a channel the developer controls and the agent does not:

1. **A code per held action.** Every sign-off decision carries a short code bound to the
   session and the exact action (`action_key`): a shell command normalised (whitespace
   collapsed outside quotes, after tokenising), or a file tool's effect (write or delete)
   and its normalised target path. The same action in the same session always gets the
   same code, so a retry is asked under the code the developer already saw; a different
   command or target gets a different code, and a grant never transfers.
2. **The request is recorded** (the store's `signoffs` table).
3. **The developer grants it once**, in either of two ways:
   * a prompt in the same session whose first non-empty line is the reply
     (`approve K7M2QX`; `reply_codes` says exactly what is accepted, and why);
   * `truthstone approve K7M2QX` in a terminal. `codex exec` has no next prompt, so
     this is its only path.
4. **The validator consumes it** (`settle`): the next attempt at exactly that action,
   within `SIGNOFF_TTL_S` of the grant, is allowed — once. The attempt after it asks again.

This is the one place Truthstone fails *closed*: no store, a degraded store, a failed
write, an unknown code or an expired grant all mean "no grant", and the action stays
held. Everything else here still fails open: a defect in this module never breaks a
prompt or a decision; it only means nothing was granted.

The agent cannot use either channel. A prompt is typed by the developer; every shell
route to a grant that Truthstone can see — `truthstone approve`, a command carrying a
sign-off reply, resuming an agent session from the shell — needs a sign-off of its own
(`checks.self_protection`, A9). That is a tripwire, not a sandbox: an agent running as the
developer's own user can still forge a grant on purpose (`docs/CODEX.md` says how).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from typing import Any

from truthstone.core.enums import DecisionAction
from truthstone.core.events import SHELL_TOOLS, AgentEvent
from truthstone.core.models import SIGNOFF_TTL_S, Decision
from truthstone.validate import checks, shell

log = logging.getLogger(__name__)

# -- the knobs the user decides (see the A1b commit message for the rationale) -----------

# How long a grant stays usable: one run, within this many seconds of the developer's yes.
GRANT_TTL_S = SIGNOFF_TTL_S

# A reply is the developer's whole first non-empty line, after copy-paste debris (quotes,
# backticks, emphasis) and a final full stop are dropped:
#
#     approve K7M2QX            Approve k7m2qx.            `approve K7M2QX`
#     yes, approve K7M2QX       I approve K7M2QX           approve K7M2QX P3N8RT
#     approve K7M2QX, thanks
#
# Anything else on that line ("approve K7M2QX but use --soft", "don't approve K7M2QX",
# "what does approve K7M2QX do?") is not a reply, and nor is a code anywhere else in the
# prompt. A grant must be an act, not a mention.
_ACK = r"(?:(?:yes|ok|okay|sure)\b[\s,.:;!-]*)?(?:i\s+)?"
_SEPARATOR = r"(?:\s*[,&]\s*|\s+and\s+|\s+)"
_COURTESY = r"(?:[\s,.;:!-]+(?:please|thanks|thank\s+you))?"
_CODES = rf"{checks.SIGNOFF_CODE_SHAPE}(?:{_SEPARATOR}{checks.SIGNOFF_CODE_SHAPE})*"
_REPLY = re.compile(rf"{_ACK}approved?(?:\s*:\s*|\s+)(?P<codes>{_CODES}){_COURTESY}", re.IGNORECASE)
_DEBRIS = str.maketrans("", "", "`'\"*_")
_MAX_REPLY_LINE = 200

# -- codes --------------------------------------------------------------------------------

# Crockford's base-32 alphabet: no I, L, O or U, so a code survives being read aloud or
# retyped. A typed code is read the same way: O is zero, I and L are one.
ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
CODE_LENGTH = 6
_TYPED = str.maketrans("OIL", "011")
_CODE_TOKEN = re.compile(checks.SIGNOFF_CODE_SHAPE, re.IGNORECASE)

VIA_PROMPT = "prompt"
VIA_TERMINAL = "terminal"
_VIA_TEXT = {VIA_PROMPT: "a reply in the session", VIA_TERMINAL: "`truthstone approve`"}


def code_for(session_id: str, key: str) -> str:
    """The code of one action in one session: 6 characters of a SHA-256 in `ALPHABET`.

    Always at least one digit and one letter, so a code never reads as a word or a number
    (`checks.SIGNOFF_CODE_SHAPE`, which the self-protection tripwire also looks for).
    Deterministic: the same action in the same session gets the same code after a daemon
    restart too. Not a secret — the grant channel is what the agent cannot reach.
    """
    code = ""
    for salt in range(64):
        digest = hashlib.sha256(f"{salt}\x00{session_id}\x00{key}".encode()).digest()
        value = int.from_bytes(digest[:8], "big")
        code = "".join(ALPHABET[(value >> (5 * i)) & 31] for i in range(CODE_LENGTH))
        if any(c.isdigit() for c in code) and any(c.isalpha() for c in code):
            return code
    return code  # 64 misses in a row: about 1e-62


def normalise_code(text: str) -> str | None:
    """A code as typed -> as issued (case-insensitive; O→0, I/L→1), or None."""
    if not isinstance(text, str):
        return None
    value = text.strip().upper().translate(_TYPED)
    if len(value) == CODE_LENGTH and all(c in ALPHABET for c in value):
        return value
    return None


def codes_in(text: str | None) -> list[str]:
    """Every code named in `text` (a `Decision.signoff_code`, a CLI argument), in order."""
    if not isinstance(text, str):
        return []
    found = (normalise_code(token) for token in re.split(r"[\s,]+", text))
    return list(dict.fromkeys(code for code in found if code))


# -- the action a code is bound to ---------------------------------------------------------


def normalised_command(command: str) -> str:
    """One spelling per shell command, so a retry with different spacing is the same
    action, and nothing that changes what runs is lost.

    Each simple command becomes its words (quotes kept) joined by one space; the
    separators between commands (`;`, `&&`, `|`, a newline, ...) and here-document bodies
    are kept verbatim. So `git  reset --hard` is `git reset --hard`, but `echo "a  b"` is
    not `echo "a b"` and `rm -rf a\\nb` is not `rm -rf a b`. A command too long to scan
    whole (`shell.MAX_SCAN`) is its own key, unnormalised.

    Read from `shell.parse`, which is cached: the risk checks have just parsed this very
    command, so the key costs one pass over its words.
    """
    if len(command) > shell.MAX_SCAN:
        return command
    parsed = shell.parse(command)
    out: list[str] = []
    for part in parsed.parts:
        if part.depth:
            continue  # nested `sh -c` strings and bodies: already in their own piece's text
        if out:
            out.append(part.piece.before or ";")
        out.append(" ".join(word.raw for word in shell.words(part.piece.text)))
    bodies = "".join(f"\n<<{doc.word}\n{doc.body}" for doc in parsed.heredocs)
    return " ".join(item for item in out if item) + bodies


def action_key(event: AgentEvent) -> str:
    """What a code is bound to: the exact action, in the core's vocabulary.

    * a shell tool: the normalised full command;
    * a file tool: its effect (`write` or `delete`) and the normalised target path — a
      Codex patch splits into Edit, MultiEdit or Write by its hunks, and the developer
      approved changing that file, not a hunk count;
    * anything else: the tool and its arguments, verbatim.
    """
    if event.tool in SHELL_TOOLS:
        command = event.arg("command")
        return "shell\x00" + normalised_command(command if isinstance(command, str) else "")
    target = checks._raw_target(event)
    if target:
        effect = "delete" if event.is_delete else "write"
        return f"{effect}\x00{_normalised_path(target, event.workspace)}"
    return f"{event.tool or ''}\x00{json.dumps(event.arguments, sort_keys=True, default=str)}"


def _normalised_path(raw: str, workspace: str) -> str:
    return os.path.normpath(os.path.join(workspace or ".", os.path.expanduser(raw)))


def _digest(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8", "surrogatepass")).hexdigest()[:32]


def summary(event: AgentEvent) -> str:
    """The held action in a line, for the developer (stored redacted and bounded)."""
    if event.tool in SHELL_TOOLS:
        command = event.arg("command")
        return " ".join(command[:1_000].split())[:300] if isinstance(command, str) else str(event.tool)
    target = checks._raw_target(event)
    if target:
        return f"{'delete' if event.is_delete else 'write'} {_normalised_path(target, event.workspace)}"
    return str(event.tool or "action")


# -- the validator's side: consume a grant, or ask ------------------------------------------


def settle(event: AgentEvent, store: Any, decision: Decision) -> Decision:
    """A sign-off decision, settled against the developer's grants. Never raises.

    * a live grant for this exact action: consumed, and the action is ALLOWED, once. The
      decision keeps its findings (the census still counts what was approved) and says who
      signed off and how;
    * otherwise the request is recorded and the decision carries its code;
    * no usable store (None, degraded, busy, failed): the decision as it was, with no
      code. Still held — the one place Truthstone fails closed.
    """
    if not decision.signoff_required or decision.action is not DecisionAction.REQUEST_REVIEW:
        return decision
    try:
        key = action_key(event)
        session_id = event.session_id or ""
        code = code_for(session_id, key)
        if store is None:
            log.warning("truthstone: no store for sign-off %s; the action stays held", code)
            return decision
        status, grant = store.signoff_settle(session_id, code, _digest(key), summary(event), GRANT_TTL_S)
    except Exception:  # fail closed: no grant was found, so the action stays held
        log.exception("truthstone: sign-off lookup failed; the action stays held")
        return decision
    if status == "granted" and grant is not None:
        via = _VIA_TEXT.get(str(grant.get("granted_via")), "the developer")
        return Decision(
            action=DecisionAction.ALLOW,
            level=decision.level,
            findings=decision.findings,
            reason=f"Signed off by the developer (code {code}, through {via}): allowed once.",
            signoff_code=code,
        )
    if status == "requested":
        return decision.model_copy(update={"signoff_code": code})
    log.warning(
        "truthstone: sign-off request %s could not be recorded (%s); the action stays held "
        "and cannot be approved until storage works",
        code,
        getattr(store, "degraded_reason", "") or status,
    )
    return decision


# -- the developer's side: a reply in the session -------------------------------------------


def reply_codes(prompt: str | None) -> list[str]:
    """The codes a prompt signs off, or [] when the prompt is not a sign-off reply.

    Only the first non-empty line counts, and only when the whole line is the reply
    (`_REPLY`). Anchoring is what makes it precise: a prompt that quotes, questions,
    negates or qualifies a code — or carries one anywhere else — grants nothing.
    """
    if not isinstance(prompt, str):
        return []
    first = next((line for line in prompt.splitlines() if line.strip()), "")
    if not first or len(first) > _MAX_REPLY_LINE:
        return []
    line = " ".join(first.translate(_DEBRIS).split()).rstrip(".!")
    match = _REPLY.fullmatch(line)
    if match is None:
        return []
    found = (normalise_code(token) for token in _CODE_TOKEN.findall(match.group("codes")))
    return list(dict.fromkeys(code for code in found if code))


def note_prompt(store: Any, event: AgentEvent) -> None:
    """Record the developer's sign-off when this prompt is the reply. Never raises.

    The engine calls this first thing on every prompt (`Guard._on_user_prompt`). A grant
    is recorded only for a code outstanding in *this* session — a code from another
    session, one already used, or one never issued grants nothing — and a prompt with no
    session id grants nothing (there is no "this session"); `truthstone approve` remains.
    """
    try:
        codes = reply_codes(event.prompt_text)
        if not codes:
            return
        if store is None or not event.session_id:
            log.warning("truthstone: sign-off reply %s ignored: no store or no session", " ".join(codes))
            return
        for code in codes:
            status, _ = store.signoff_grant(code, VIA_PROMPT, session_id=event.session_id)
            if status == "granted":
                log.info("truthstone: the developer signed off %s in the session", code)
            else:
                log.warning("truthstone: sign-off reply %s granted nothing (%s)", code, status)
    except Exception:  # a prompt is never broken by this; nothing was granted
        log.exception("truthstone: reading a sign-off reply failed; nothing was granted")


# -- the developer's side: the terminal ------------------------------------------------------


def grant_from_terminal(store: Any, code: str) -> tuple[str, dict[str, Any] | None]:
    """`truthstone approve CODE`: the newest outstanding request with this code in the
    project. Same statuses as `ProjectStore.signoff_grant`."""
    return store.signoff_grant(code, VIA_TERMINAL)
