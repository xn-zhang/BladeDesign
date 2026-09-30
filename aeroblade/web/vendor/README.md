# Conversation rendering libraries

Pinned browser distributions, served locally so the workbench does not require a CDN at runtime:

- Marked 15.0.12: https://github.com/markedjs/marked — MIT, see marked-LICENSE.txt.
- DOMPurify 3.2.7: https://github.com/cure53/DOMPurify — Apache-2.0 OR MPL-2.0, see purify-LICENSE.txt.
- KaTeX 0.16.22: https://github.com/KaTeX/KaTeX — MIT, see katex-LICENSE.txt.

Downloaded from the corresponding versioned npm distributions via jsDelivr. KaTeX produces native MathML, so no external fonts are required. Markdown HTML is sanitized before insertion; KaTeX runs with trust disabled. Remote images are excluded from rendered messages.
