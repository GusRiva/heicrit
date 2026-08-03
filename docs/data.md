# HeiCrit Data Model

This document describes the data model used by HeiCrit: how TEI/XML source files are structured, how they reference each other, and what data structures the backend produces for the frontend.

---

## 1. Overview

Three kinds of file work together:

```
apparatus/edition_app.xml   ←  lists all witnesses; contains <app> entries
    │  corresp="…/synoptic_map.xml"
    ↓
synopses/synoptic_map.xml   ←  aligns every location across every witness
    │  target="a:l_5 ba:l_5 bb:l_5 …"
    ↓
texts/Witness_A.xml         ←  tokenised witness text (words have xml:id)
texts/Witness_Ba.xml
…
```

The **apparatus file** is the entry point. It declares all witnesses, defines short prefixes for them, and records textual variants. The **synoptic map** is a global alignment table that maps each location in the base text (Leithandschrift) to the corresponding element in every other witness. The **witness text files** contain the actual word-for-word text, each token tagged with a unique `xml:id`.

---

## 2. Witness Text Files (`texts/*.xml`)

Each manuscript copy is encoded as a standalone TEI document. Words are tokenised so the apparatus can reference them by ID.

### Structure

```xml
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <sourceDesc>
        <msDesc>
          <msIdentifier>
            <idno ana="hc:EditorialSiglum">A</idno>  <!-- editorial abbreviation -->
          </msIdentifier>
        </msDesc>
      </sourceDesc>
    </fileDesc>
  </teiHeader>
  <text ana="hc:CompleteExpression">
    <body>
      <lg ana="hc:Couplet" xml:id="lg_1">
        <l n="5" xml:id="l_5">
          <w xml:id="w_5_1">
            <choice><orig>D</orig><reg>d</reg></choice>ienſtman
          </w>
          <c> </c>
          <w xml:id="w_5_2">was</w>
          <c> </c>
          <w xml:id="w_5_3">er</w>
          <c> </c>
          <w xml:id="w_5_4">zu<choice><orig>ͦ</orig><reg>o</reg></choice></w>
        </l>
        <l n="6" xml:id="l_6">
          <w xml:id="w_6_1">Er</w>
          <c> </c>
          <w xml:id="w_6_2">nam</w>
          …
        </l>
      </lg>
    </body>
  </text>
</TEI>
```

### Elements

| Element | Attributes | Purpose |
|---------|-----------|---------|
| `<lg>` | `xml:id="lg_N"` | Line group (couplet, stanza) |
| `<l>` | `n="N"`, `xml:id="l_N"` | Line; the `@n` number matches `@loc` in apparatus entries |
| `<w>` | `xml:id="w_N_M"` | Word token at position M in line N; **the primary reference target** |
| `<pc>` | `xml:id="pc_N_M"` | Punctuation token (period, comma, …) |
| `<c>` | — | Whitespace separator; not addressable, not selectable |
| `<choice>` | — | Editorial choice between two forms |
| `<orig>` | — | Diplomatic form (exactly as in manuscript) |
| `<reg>` | — | Regularised/normalised form |
| `<titlePart>` | `xml:id="titlePart_N"` | Title elements; same ID scheme |

### ID Conventions

```
l_5        line 5
w_5_1      word 1 in line 5
w_5_2      word 2 in line 5
pc_5_3     punctuation at position 3 in line 5
gap_leaf_1 placeholder for a missing leaf (lacuna)
```

---

## 3. Apparatus File (`apparatus/*.xml`)

The apparatus file is the central file of a project. It declares all witnesses and contains all textual variants.

### Overall Structure

```xml
<TEI xmlns="http://www.tei-c.org/ns/1.0">
  <teiHeader>
    <fileDesc>
      <sourceDesc>
        <listWit> … </listWit>        <!-- witness declarations -->
      </sourceDesc>
    </fileDesc>
    <encodingDesc>
      <listPrefixDef> … </listPrefixDef>   <!-- prefix → file mapping -->
    </encodingDesc>
  </teiHeader>
  <text>
    <body>
      <listApp corresp="../synopses/synoptic_map.xml">
        <app …> … </app>             <!-- apparatus entries -->
        <app …> … </app>
      </listApp>
    </body>
  </text>
</TEI>
```

### Witness Declarations (`listWit`)

```xml
<listWit>
  <witness xml:id="A" ana="hc:Leithandschrift">
    <ptr target="../texts/AH_A.xml"/>
    <idno ana="hc:EditorialSiglum">A</idno>
  </witness>
  <witness xml:id="Ba">
    <ptr target="../texts/AH_Ba.xml"/>
    <idno ana="hc:EditorialSiglum">Ba</idno>
  </witness>
  <witness xml:id="Bb">
    <ptr target="../texts/AH_Bb.xml"/>
    <idno ana="hc:EditorialSiglum">Bb</idno>
  </witness>
</listWit>
```

| Attribute / Element | Meaning |
|--------------------|---------|
| `witness/@xml:id` | Internal identifier; used in `wit="#A"` references |
| `witness/@ana="hc:Leithandschrift"` | Marks the base manuscript (exactly one per project) |
| `ptr/@target` | Relative path to the witness text file |
| `idno[@ana="hc:EditorialSiglum"]` | The siglum printed in the apparatus (A, Ba, Bb …) |

The order of `<witness>` elements in `listWit` defines the display order of witnesses throughout the application.

### Prefix Definitions (`listPrefixDef`)

```xml
<listPrefixDef>
  <prefixDef ident="a"  matchPattern="(.+)"
             replacementPattern="../texts/AH_A.xml/$1"
             ana="hc:SynopticTextPrefixDefinition"/>
  <prefixDef ident="ba" matchPattern="(.+)"
             replacementPattern="../texts/AH_Ba.xml/$1"
             ana="hc:SynopticTextPrefixDefinition"/>
  <prefixDef ident="bb" matchPattern="(.+)"
             replacementPattern="../texts/AH_Bb.xml/$1"
             ana="hc:SynopticTextPrefixDefinition"/>
</listPrefixDef>
```

Each `prefixDef` maps a short prefix to the witness file it belongs to. The prefix is used in all `corresp` and `target` attributes throughout the project (see §4). `ana="hc:SynopticTextPrefixDefinition"` marks definitions that participate in the synoptic map.

### Apparatus Entries (`<app>`)

```xml
<!-- Single-token variant -->
<app loc="6" corresp="a:l_6">
  <lem wit="#A"       corresp="a:w_6_1">Er</lem>
  <rdg wit="#Ba #Bb"  corresp="ba:w_6_1 bb:w_6_1">der</rdg>
</app>

<!-- Multi-token variant: lemma spans a range -->
<app loc="5" corresp="a:l_5">
  <lem wit="#A"      corresp="a:range(w_5_1, w_5_4)">Dienſtman wars er zuͦ</lem>
  <rdg wit="#Ba #Bb" corresp="ba:range(w_5_1, w_5_4) bb:range(w_5_1, w_5_4)">
    Vn̄ was ein dinſteman von
  </rdg>
</app>

<!-- Two independent variants at the same location -->
<app loc="6" corresp="a:l_6">
  <lem wit="#A"      corresp="a:w_6_4">mange</lem>
  <rdg wit="#Ba #Bb" corresp="ba:w_6_4 bb:w_6_4">eine</rdg>
</app>
```

| Element / Attribute | Meaning |
|--------------------|---------|
| `app/@loc` | Location number (matches `<l @n>` in the Leithandschrift) |
| `app/@corresp` | Reference to the line in the Leithandschrift (`leiths_prefix:l_N`) |
| `lem` | The lemma — the reading adopted by the editor (from the Leithandschrift) |
| `lem/@wit` | Witness(es) supporting the lemma, preceded by `#` |
| `lem/@corresp` | Exact token(s) in the Leithandschrift text this lemma covers |
| `rdg` | A variant reading from one or more other witnesses |
| `rdg/@wit` | Witnesses supporting this reading, space-separated, each preceded by `#` |
| `rdg/@corresp` | Token(s) in each witness's text that correspond to this reading |

Multiple `<app>` elements may share the same `@loc` and `@corresp` when there are several independent points of variation within one line.

---

## 4. Reference Notation

All `@corresp` and `@target` values use a unified prefix-colon notation:

```
prefix:reference
```

where `prefix` is the short identifier defined in `prefixDef` and `reference` is an element `xml:id` or a special expression.

### Patterns

| Pattern | Meaning |
|---------|---------|
| `a:l_5` | Witness `a`, element with `xml:id="l_5"` |
| `ba:w_6_1` | Witness `ba`, word element `w_6_1` |
| `a:range(w_5_1, w_5_4)` | Witness `a`, all tokens from `w_5_1` to `w_5_4` inclusive |
| `c:gap_leaf_1` | Witness `c` has a lacuna here (whole leaf missing); displayed as *om.* |
| `e:left(l_29)` | Witness `e` aligns with the beginning of line `l_29` (partial-page reference) |
| `e:right(l_59)` | Witness `e` aligns with the end of line `l_59` |
| `a:titlePart_1` | Witness `a`, title element |

**Multiple references in one attribute** are space-separated. In `rdg/@corresp` this is common when the same reading variant appears at corresponding positions in several witnesses:

```
corresp="ba:w_6_1 bb:w_6_1"       ← w_6_1 in Ba, w_6_1 in Bb
corresp="ba:w_7_2 ba:w_7_3 bb:w_7_2 bb:w_7_3"  ← two tokens in each witness
```

### Insertion and deletion references

`left(w_N_M)` and `right(w_N_M)` appear in two distinct contexts with **different meanings**:

| Context | `left(id)` meaning |
|---------|-------------------|
| Synoptic map `<link @target>` | Witness aligns with the left margin of line `id` (pagination difference) |
| Apparatus `<lem/@corresp>` or `<rdg/@corresp>` | Position marker: entry concerns the gap **before** token `id` |

In the apparatus, `left(w_N_M)` is a **position marker**, not a token ID. It means "the gap immediately before token `w_N_M`" — a synoptic alignment position where this witness has no word.

**Example — A lacks a word that Ba/Bb have:**

```xml
<!-- Ba and Bb have "einem" before their "ieſlichen" (ba:w_7_2 / bb:w_7_2).
     A has nothing at that position. The entry is anchored to the gap
     before A's w_7_2 ("miſlichen"). The lem content is classical apparatus
     context notation ("vor miſlichen" = "before miſlichen"), not variant text. -->
<app loc="7" corresp="a:l_7">
    <lem wit="#A"      corresp="a:left(w_7_2)"><emph>vor</emph> miſlichen</lem>
    <rdg wit="#Ba #Bb" corresp="ba:w_7_2 bb:w_7_2">einem</rdg>
</app>
```

Reading the entry: at the gap before A's `w_7_2`, A has nothing; Ba and Bb have "einem". This records an **omission in A** (or equivalently, an addition in Ba/Bb).

The sibling `<rdg>` points to a regular token (`ba:w_7_2`), not a `left()` position, because Ba/Bb do have a word there — their token numbering is shifted by one relative to A precisely because they have the extra word.

**Mapping to HTML spans** — `a:left(w_7_2)` corresponds to the `syn-token-pre` span with `data-token-id="w_7_2"` in A's row of the synoptic comparison view. That span represents the empty insertion slot before the word.

| Reference syntax | HTML span class | `data-token-id` |
|-----------------|-----------------|----------------|
| `prefix:left(w_N_M)` | `syn-token-pre` | `w_N_M` |
| `prefix:w_N_M` | `syn-tei-w` | `w_N_M` |
| `prefix:right(w_N_M)` | `syn-token-post` | `w_N_M` |

---

## 5. Synoptic Map (`synopses/synoptic_map.xml`)

The synoptic map is a stand-off alignment document. It enumerates every location in the edition and lists the corresponding element in every witness.

### Structure

```xml
<TEI xmlns="http://www.tei-c.org/ns/1.0" ana="hc:SynopticMap">
  <teiHeader>
    <encodingDesc>
      <listPrefixDef>
        <!-- same prefixDef elements as apparatus -->
      </listPrefixDef>
    </encodingDesc>
  </teiHeader>
  <standOff>
    <link n="1"  target="a:l_1  ba:l_1  bb:l_1  c:gap_leaf_1 e:left(l_29)"/>
    <link n="5"  target="a:l_5  ba:l_5  bb:l_5  c:gap_leaf_1 e:left(l_29)"/>
    <link n="6"  target="a:l_6  ba:l_6  bb:l_6  c:gap_leaf_1 e:left(l_29)"/>
    <link n="62a" target="a:l_62a ba:l_62a …"/>   <!-- sub-location -->
    …
  </standOff>
</TEI>
```

### `<link>` element

| Attribute | Meaning |
|-----------|---------|
| `@n` | Sequential location number; may be fractional (62a, 78b) for insertions |
| `@target` | Space-separated list of witness references, one per witness; the first entry anchors on the Leithandschrift |

The synoptic map is referenced by the apparatus file via `listApp/@corresp="../synopses/synoptic_map.xml"`. It is loaded separately by the backend and drives the Location Details panel.

---

## 6. Python Data Structures (Backend)

The backend (`apparatus.py`, `synoptic_map.py`) parses the XML and exposes structured data through the API.

### Apparatus entry (`apparatus.get_entries()`)

```python
{
    'id': int,          # 1-based, sequential within the apparatus file
    'loc': str,         # e.g. "5" or "62a"
    'corresp': str,     # e.g. "a:l_5"  (anchors to leithandschrift line)
    'lemma': {
        'text': str,    # plain text content of <lem>
        'attributes': { # all XML attributes of <lem>
            'wit':     '#A',
            'corresp': 'a:range(w_5_1, w_5_4)',
            # …
        }
    } | None,
    'readings': [
        {
            'text': str,
            'attributes': {
                'wit':     '#Ba #Bb',
                'corresp': 'ba:range(w_5_1, w_5_4) bb:range(w_5_1, w_5_4)',
            }
        },
        # … one dict per <rdg> element
    ],
    'is_placeholder': bool  # True if synthesised from synoptic map (no <app> in file)
}
```

**Placeholder entries**: When the synoptic map contains a location that has no `<app>` entry in the apparatus file, the frontend merge creates a placeholder entry with `is_placeholder: True`. This ensures navigation covers every synoptic location even when no variant has been recorded yet.

### Witness mapping (`apparatus.get_witness_to_prefix_mapping()`)

```python
{
    'A': {
        'synoptic_prefix': 'a',            # prefix used in corresp/target attributes
        'target_file':     '../texts/AH_A.xml',
        'siglum':          'A'
    },
    'Ba': {
        'synoptic_prefix': 'ba',
        'target_file':     '../texts/AH_Ba.xml',
        'siglum':          'Ba'
    },
    # …
}
```

Keys are the `witness/@xml:id` values from `listWit`.

### Synoptic loci (`synoptic_map.get_loci()`)

```python
{
    'a:l_5': {
        'n':      '5',
        'target': ['a:l_5', 'ba:l_5', 'bb:l_5', 'c:gap_leaf_1', 'e:left(l_29)']
    },
    'a:l_6': {
        'n':      '6',
        'target': ['a:l_6', 'ba:l_6', 'bb:l_6', 'c:gap_leaf_1', 'e:left(l_29)']
    },
    # …
}
```

The dict key is always `{leiths_prefix}:{element_id}` matching the first entry in `@target`.

### Witness info (`synoptic_map.get_wits()`)

```python
{
    'a':  { 'file_name': '../texts/AH_A.xml',  'elements_count': int, 'siglum': 'A' },
    'ba': { 'file_name': '../texts/AH_Ba.xml', 'elements_count': int, 'siglum': 'Ba' },
    # …
}
```

---

## 7. Token Model in the Synoptic Comparison View

When the frontend requests `/api/synoptic/compare`, the backend retrieves the XML element for each witness at that location and converts it to HTML using `process_synoptic_unit_for_comparison()`. The result is a flat sequence of `<span>` elements:

```html
<!-- For line 6 of witness A -->
<span class="syn-token syn-token-pre"  data-token-id="w_6_1"> </span>
<span class="syn-token syn-tei-w"      data-token-id="w_6_1">Er</span>
<span class="syn-token syn-token-pre"  data-token-id="w_6_2"> </span>
<span class="syn-token syn-tei-w"      data-token-id="w_6_2">nam</span>
<span class="syn-token syn-token-pre"  data-token-id="w_6_3"> </span>
<span class="syn-token syn-tei-w"      data-token-id="w_6_3">ime</span>
…
<span class="syn-token syn-token-post"> </span>
```

### Span classes

| Class | Purpose |
|-------|---------|
| `syn-token` | Applied to all interactive token spans |
| `syn-token-pre` | The **space before** a token. Represents the *insertion/deletion position* immediately preceding this word. Selecting it in creation mode records that a word was added before this token (or that this token is absent in this witness). |
| `syn-tei-w` | An actual **word** token (`<w>` in the source XML) |
| `syn-tei-pc` | A **punctuation** token (`<pc>` in the source XML) |
| `syn-token-post` | Trailing space after the last token on the line |

### `data-token-id`

All three span types (`syn-token-pre`, `syn-tei-w`, `syn-tei-pc`) carry the same `data-token-id` value, matching the `xml:id` of the corresponding source XML element. This allows the frontend to:

- Locate the correct token in any witness given a `prefix:token_id` reference
- Apply apparatus highlighting to the right element
- Build `corresp` values for new apparatus entries

### Apparatus highlighting

Highlighting targets the span that matches the `corresp` reference type:

- Plain `prefix:w_N_M` → highlight the `syn-tei-w` span (the word itself)
- `prefix:left(w_N_M)` → highlight the `syn-token-pre` span before that word (the empty gap)
- `prefix:right(w_N_M)` → highlight the `syn-token-post` span after that word
- `prefix:range(w_N_M, w_N_K)` → highlight all word spans in the range

The CSS classes used are:

| Class | Colour | Applied to |
|-------|--------|-----------|
| `highlight-lemma` | green | Lemma token(s) / gap in the Leithandschrift row |
| `highlight-reading-1` | orange | First reading's token(s) in witness rows |
| `highlight-reading-2` | purple | Second reading (when multiple readings exist) |
| `has-apparatus` | light grey | Any token that has any apparatus entry at this location |

### Creation mode and pre-space selection

When the user activates **New Variant** mode, all `syn-token` spans become clickable. Selecting a `syn-token-pre` means: "the variant I am recording affects the *position before* this word" — for instance, a word that is present in one witness but absent in another, or an addition. The selected tokens (pre-spaces and words) are collected, their `data-token-id` values assembled into `corresp` strings, and eventually written into the apparatus XML as new `<lem>` / `<rdg>` elements.

---

## 8. API Endpoints (summary)

| Endpoint | Method | What it does |
|----------|--------|-------------|
| `/api/apparatus/parse` | POST | Parse apparatus file; store global `Apparatus` object |
| `/api/witnesses/load` | POST | Extract witness mappings from parsed apparatus |
| `/api/synoptic/load` | POST | Load synoptic map with witness data |
| `/api/maintext/generate` | POST | Run pipeline; produce HTML of Leithandschrift |
| `/api/project/finalize` | POST | Return all combined project data |
| `/api/synoptic/compare` | POST | Render tokens for a given `data_link` (e.g. `"a:l_6 ba:l_6"`) |
| `/api/apparatus/save` | POST | Insert new `<app>` entries into the apparatus XML file |
| `/api/apparatus/entry/<id>` | PUT | Update an existing entry in the in-memory apparatus |
| `/api/sigla-mapping` | GET | Return the witness-to-prefix mapping |
