# Hyphenation for wrap_text

- Since 1.2.0 a word longer than the width gets a line of its own. In the print layout's
  narrow columns that wastes whole lines on German headlines: "Bundesverfassungsgericht"
  alone is 24 characters.
- Plan: hyphenate(word) -> syllables; wrap_text may then break at a syllable and add "-".
- Liang's algorithm needs the TeX pattern file for German (hyph-de-1996, about 30k patterns).
  Its license is the LPPL: ask legal before vendoring it.
- patterns-de.txt: 18 newsroom words, every break checked against the Duden by hand. Keep
  them as the acceptance cases.
- Open: hyphenate names? Not for now (the desk says never split a surname).
