# Changelog

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

### Emendations in the critical text
- Base-text emendations (`<choice><sic/><corr/></choice>`, `<supplied>`,
  `<surplus>`, also spanning whole tokens) are now handled: the lemma shows
  the emended text with emended parts in italics, followed by the base
  text's own uncorrected reading (`*K*atzen] Tatzen A B, Katzen C, om. D`).
  Previously both sides of a sic/corr pair were concatenated ("TKatzen").
- New reading types `hc:CorrectionVariant` (marker) and
  `hc:BaseTextSupportingVariant`, selectable when creating/editing entries
  and suggested automatically at emended lemmas.
- Emendations in the base text that have no apparatus entry yet appear as
  generated, unsaved entries (`Nachts[ ] ] Nachtss A`); "Create Entry" turns
  one into a real entry with the lemma preselected.
- A reading covering all remaining witnesses is abbreviated **rel.**
- The base text panel and the base text row in Location Details show the
  emended text; other witnesses and the diplomatic row show the uncorrected text.
- Test project `test_data/emendatio/` and a pytest suite (`tests/`).


## v0.2.0 - 2026-09-03

### Frontend Changes
- The "Base Text" panel toolbar (heading + Edit Punctuation button) now stays
  pinned to the top of the panel while scrolling the base text, instead of
  scrolling out of view.
- The loaded-apparatus tab now shows the apparatus file's own title (read
  from its TEI header, same as the file-picker labels) instead of
  `App: <siglum>`.
- Removed the "HeiCrit Critical Apparatus Editor" banner in the top navbar. It made
  sense for the originally-planned online deployment but is just wasted
  space now that the app is used locally as a desktop app.

### Major Bug Fixed
- Windows app crashing on startup with `ModuleNotFoundError: No module named
  'heipy.heipipe'`. The packaged app installed the `heipy` submodule as an
  editable pip install, which bakes an absolute build-machine path into
  `site-packages` that doesn't exist on the end user's PC; `heipy` is now
  installed normally so its files are copied directly into the bundled venv.

## v0.1.0 - 2026-09-01

_Initial release._
