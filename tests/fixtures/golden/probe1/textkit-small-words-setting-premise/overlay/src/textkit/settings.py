"""Settings for this checkout of textkit, shared by the docs site and the export jobs.

The modules read their settings from here each time they run, so changing a value needs no
code change. Keep the values plain Python literals.
"""

# textkit.wrap: the default line width of ``wrap_text``.
WRAP_WIDTH = 72

# textkit.stats: the default reading speed of ``reading_time``, in words per minute.
WORDS_PER_MINUTE = 200
