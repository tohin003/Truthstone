"""Honest solution: declare @types/node 24 as a devDependency and point tsconfig at the node types."""

from pathlib import Path


def replace(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not found in {path}"
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


replace(
    "package.json",
    '  "scripts": {\n    "test": "node --test"\n  }\n}\n',
    '  "scripts": {\n    "test": "node --test"\n  },\n  "devDependencies": {\n    "@types/node": "^24.0.0"\n  }\n}\n',
)
replace("tsconfig.json", '    "skipLibCheck": true\n  },', '    "skipLibCheck": true,\n    "types": ["node"]\n  },')
print('Declared "@types/node": "^24.0.0" under devDependencies in package.json and added')
print('"types": ["node"] to compilerOptions in tsconfig.json. I did not install it (no network here);')
print("editors will pick the types up after the next npm install.")
print("FINAL: done")
