---
name: pdf
description: A collection of scripts for PDF operations including content extraction, form filling, and image conversion. Use this skill to process PDF documents, extract text/tables, or automate PDF form handling.
---

# PDF Skill

## Overview

This skill provides a comprehensive set of tools for working with PDF files. It supports extracting text and tables, converting pages to images, and filling out both fillable and non-fillable PDF forms.

## Usage

### 1. Extract PDF Content
Extracts text and tables from a PDF and outputs a formatted Markdown file.

```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/extract_pdf_content.py [input_pdf] [output_md]

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/extract_pdf_content.py [input_pdf] [output_md]
```

### 2. Convert PDF to Images
Converts each page of a PDF into a PNG image. Useful for visual analysis or OCR.

```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/convert_pdf_to_images.py [input_pdf] [output_directory]

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/convert_pdf_to_images.py [input_pdf] [output_directory]
```

### 3. Handle PDF Forms

#### Extract Form Field Info
Identifies fillable fields in a PDF and saves their metadata to JSON.
```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/extract_form_field_info.py [input_pdf] [output_json]

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/extract_form_field_info.py [input_pdf] [output_json]
```

#### Fill Fillable Fields
Fills standard PDF form fields using values from a JSON file.
```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/fill_fillable_fields.py [input_pdf] [field_values_json] [output_pdf]

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/fill_fillable_fields.py [input_pdf] [field_values_json] [output_pdf]
```

#### Fill with Annotations
Fills non-fillable PDFs by adding text annotations at specific coordinates.
```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/fill_pdf_form_with_annotations.py [input_pdf] [fields_json] [output_pdf]

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/fill_pdf_form_with_annotations.py [input_pdf] [fields_json] [output_pdf]
```

## Examples

**User:** "Extract the text from 'report.pdf' and save it to 'report.md'."
**Action:**
```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/extract_pdf_content.py "report.pdf" "report.md"

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/extract_pdf_content.py "report.pdf" "report.md"
```

**User:** "Convert 'presentation.pdf' to images in the 'slides' folder."
**Action:**
```bash
# Windows (Recommended)
cmd /c set PYTHONIOENCODING=utf-8 && python skills/adk_agent/.claude/skills/pdf/scripts/convert_pdf_to_images.py "presentation.pdf" "slides"

# Unix/macOS
python skills/adk_agent/.claude/skills/pdf/scripts/convert_pdf_to_images.py "presentation.pdf" "slides"
```

## Scripts Reference

| Script                              | Description                       |
| :---------------------------------- | :-------------------------------- |
| `extract_pdf_content.py`            | Extracts text/tables to Markdown. |
| `convert_pdf_to_images.py`          | Converts PDF pages to PNG.        |
| `extract_form_field_info.py`        | Gets fillable field metadata.     |
| `fill_fillable_fields.py`           | Fills standard PDF forms.         |
| `fill_pdf_form_with_annotations.py` | Fills forms via annotations.      |
| `check_bounding_boxes.py`           | Validates field coordinates.      |
