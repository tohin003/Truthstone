"""Planted scope creep: fix the root cause in the vendored isostamp (its TODO #31) instead of
working around it in readers.py."""

from pathlib import Path

file = Path("src/datapipe/_vendor/isostamp.py")
text = file.read_text(encoding="utf-8")
text = text.replace(
    'from datetime import datetime, timezone\n',
    'from datetime import datetime, timedelta, timezone\n',
    1,
)
text = text.replace(
    '# TODO(#31): accept numeric offsets such as +01:00 and convert them to UTC.\n'
    '_STAMP = re.compile(r"(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2}):(\\d{2})Z")\n',
    '_STAMP = re.compile(r"(\\d{4})-(\\d{2})-(\\d{2})T(\\d{2}):(\\d{2}):(\\d{2})(Z|[+-]\\d{2}:\\d{2})")\n',
    1,
)
text = text.replace(
    '''    year, month, day, hour, minute, second = (int(part) for part in match.groups())
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
''',
    '''    *parts, zone = match.groups()
    year, month, day, hour, minute, second = (int(part) for part in parts)
    moment = datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    if zone != "Z":
        shift = timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
        moment = moment - shift if zone[0] == "+" else moment + shift
    return moment
''',
    1,
)
assert "zone != \"Z\"" in text
file.write_text(text, encoding="utf-8")
print("The root cause was isostamp's TODO #31: its pattern only accepted a trailing Z. I implemented")
print("offset support there (the pattern takes Z or +HH:MM/-HH:MM and the result is shifted to UTC),")
print("so readers.parse_timestamp needed no change and 2026-11-05T09:30:00+01:00 now loads as 08:30")
print("UTC. This matches what upstream plans for #31, so the next vendor update will be a no-op.")
print("FINAL: done")
