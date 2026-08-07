# Template execution contract: รายงานโครงงาน 5 บท

## Reference set

- Chapter 1: `C:\Users\Ult_Orange\Desktop\เอกสาร\บทที่1_จัดหน้าแล้ว.docx`; SHA-256 `D0183CF86B987AB3FFAA0CD85E2D620DEDCDDF5891F6D1922EB40F2C41384605`; 6 rendered pages; 1 section.
- Chapter 2: `C:\Users\Ult_Orange\Desktop\เอกสาร\บทที่2_จัดหน้าแล้ว.docx`; SHA-256 `1749DFA4753E999D2117CDDE7BA1781A087D33844746CD8F6645477131D1B8C5`; 9 rendered pages; 1 section.
- Chapter 3: `C:\Users\Ult_Orange\Desktop\เอกสาร\บทที่3_จัดหน้าแล้ว.docx`; SHA-256 `38D26607CE5F903AFCE32F7D04CC4337712D493851EDF9D64EE5FEA92151680D`; 9 rendered pages; 1 section.
- Chapter 4: `C:\Users\Ult_Orange\Desktop\เอกสาร\บทที่4_จัดหน้าแล้ว.docx`; SHA-256 `49E8729386105A599CBD361AFD4E945276A563DA61604CEB29C59D0475B1B08B`; 7 rendered pages; 1 section.
- Chapter 5: `C:\Users\Ult_Orange\Desktop\เอกสาร\บทที่5_จัดหน้าแล้ว.docx`; SHA-256 `EB5F7FAC43ABA5B52653AE5322358D5FD5B5AA46183778B944AB6B6E2D8A7423`; 7 rendered pages; 1 section.
- Render evidence: `C:\Users\Ult_Orange\Desktop\Update2\qa\template_old\ch1` through `ch5`; section/style evidence is stored alongside the renders.

## Page system

- A4 portrait, 21.0 × 29.7 cm.
- Margins: left 3.81 cm, right 2.54 cm, top 3.81 cm, bottom 2.54 cm.
- One section per chapter. First page is treated as a chapter opener; subsequent pages carry centered page numbers in the footer.
- No running header. No multi-column or landscape pattern.

## Typography and paragraph roles

- Source body font: TH Sarabun New, approximately 16 pt; black.
- Chapter number and chapter title: centered, bold, approximately 18–20 pt; title block positioned in the upper-middle of the opening page.
- Heading 1: bold, approximately 18 pt, left aligned, no first-line indent, kept with following paragraph.
- Heading 2/3: bold, approximately 16 pt, left aligned, no first-line indent, kept with following paragraph.
- Body: approximately 16 pt, first-line indent about 1.25 cm, generous Thai line spacing; source often uses full justification. The new version may use left alignment where full justification creates visibly stretched Thai spacing.
- Chapter opener: one or two introductory paragraphs followed by an indented section map, then a page break.
- Captions: centered, approximately 14 pt, directly adjacent to the related figure or table.

## Lists and tables

- Numbered objectives, scopes, procedures, and recommendations use hanging indents and chapter-based numbering.
- Tables use pale blue header fill, medium gray grid lines, repeated header rows, vertically centered cells, and a centered caption.
- Column widths are content-driven. Narrative columns are wider than identifiers or numeric values. Rows expand automatically; no fixed row heights.
- Table outer width aligns with the body text area, with modest cell padding.

## Components and content flow

- Recurring chapter opener: chapter number, subtitle, introduction, section map.
- Chapter 1: background, objectives, scope, method summary, benefits, resources, schedule, definitions, report structure.
- Chapter 2: conceptual foundations, technology, feature extraction, temporal representation, model, evaluation concepts, related work, references.
- Chapter 3: research/development method, requirements, architecture, data collection, feature extraction, dataset status, training, real-time flow, UI/TTS, evaluation plan, quality/ethics.
- Chapter 4: dataset results, reproducible evaluation, per-class results, functional implementation, evidence gaps, summary.
- Chapter 5: summary against objectives, discussion, limitations, recommendations, final conclusion.
- Figures appear in Chapters 2–4. For the new work, requested illustration positions must remain as labeled placeholders rather than invented screenshots.

## Slot map

- All narrative paragraphs, chapter headings, section maps, table content, figure descriptions, and captions are rewrite slots because the user requested conversion from the former static-frame system to the current HandVox motion-clip system.
- Page geometry, chapter opener pattern, heading ladder, footer page-number treatment, table palette, table caption placement, and overall formal report rhythm are preserve/recreate slots.
- Old project facts (63 features, CSV frame data, 15 labels, 4,500 samples, old accuracy, old screenshots, TensorFlow/Keras claims) must be removed rather than preserved.
- Figure positions are editable slots. They must be replaced by clear blank placeholders describing the exact screenshot, diagram, or chart the user should insert.
- References may be replaced or expanded when needed to support the new technical scope.

## Text and package coverage

- Reviewed body paragraphs, all table cells, inline drawings, section properties, footer PAGE fields, styles, image relationships, and footnote/endnote inventories.
- No footnotes or endnotes. No content controls. Page-number fields exist in footer parts. Chapters 2–4 contain inline images; Chapters 1 and 5 do not.
- The retained references remain read-only. The deliverables are new files, so opaque source parts are not copied; visual components listed above are recreated intentionally.

## Fidelity gates

- Keep A4 geometry, asymmetric thesis margins, chapter-opening page, formal Thai heading hierarchy, pale-blue tables, centered captions, and centered footer page numbers.
- Maintain consistent terminology and numeric facts across all five chapters.
- Do not carry forward old static-frame metrics or images.
- Render every final page and verify there is no clipping, overlap, broken table, orphaned heading, or unlabeled image gap.
- Confirm reference hashes remain unchanged before delivery.
