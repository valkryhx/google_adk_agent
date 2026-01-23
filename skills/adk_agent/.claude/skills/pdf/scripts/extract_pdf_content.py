import sys
import json
import pdfplumber
import glob
import io

# 强制设置输出编码为 UTF-8 以解决 Windows 下的乱码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

def extract_content(pdf_path, output_path):
    content = {
        "text": [],
        "tables": []
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages):
            # Extract text
            page_text = page.extract_text()
            if page_text:
                content["text"].append({
                    "page": i + 1,
                    "content": page_text
                })
            
            # Extract tables
            page_tables = page.extract_tables()
            if page_tables:
                for table in page_tables:
                    content["tables"].append({
                        "page": i + 1,
                        "data": table
                    })

    # Force Markdown output
    if not (output_path.lower().endswith('.md') or output_path.lower().endswith('.markdown')):
        output_path += '.md'
        print(f"Appended .md extension. Output will be saved to {output_path}")

    save_as_markdown(content, output_path)
    
    print(f"Extracted content to {output_path}")
    print(f"Found {len(content['text'])} text blocks and {len(content['tables'])} tables")

def save_as_markdown(content, output_path):
    md_output = []
    
    # Create a map of tables by page for easy access
    tables_by_page = {}
    for table in content['tables']:
        page_num = table['page']
        if page_num not in tables_by_page:
            tables_by_page[page_num] = []
        tables_by_page[page_num].append(table['data'])

    for page in content['text']:
        page_num = page['page']
        md_output.append(f"## Page {page_num}\n")
        md_output.append(page['content'])
        md_output.append("\n")
        
        # Check for tables on this page
        if page_num in tables_by_page:
            for i, table_data in enumerate(tables_by_page[page_num]):
                md_output.append(f"### Table {i+1} on Page {page_num}\n")
                if table_data:
                    # Filter out None values and replace newlines
                    cleaned_data = [[str(cell).replace('\n', ' ') if cell is not None else '' for cell in row] for row in table_data]
                    
                    # Determine column widths (optional, but good for readability in raw MD)
                    # For now, just standard pipe table
                    
                    # Header
                    if cleaned_data:
                        headers = cleaned_data[0]
                        md_output.append("| " + " | ".join(headers) + " |")
                        md_output.append("| " + " | ".join(['---'] * len(headers)) + " |")
                        
                        # Body
                        for row in cleaned_data[1:]:
                            # Ensure row has same number of columns as header
                            if len(row) < len(headers):
                                row += [''] * (len(headers) - len(row))
                            elif len(row) > len(headers):
                                row = row[:len(headers)]
                            md_output.append("| " + " | ".join(row) + " |")
                md_output.append("\n")
            
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_output))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: extract_pdf_content.py [input_pdf] [output_json]")
        sys.exit(1)
    
    # Handle potential argument splitting by taking the last arg as output
    output_path = sys.argv[-1].strip('"').strip("'")
    
    # Rely on the user passing a non-split argument (like a wildcard)
    input_arg = sys.argv[1].strip('"').strip("'")
    
    # Resolve wildcard
    if '*' in input_arg or '?' in input_arg:
        matches = glob.glob(input_arg)
        if matches:
            input_path = matches[0]
            print(f"Resolved wildcard '{input_arg}' to '{input_path}'")
        else:
            print(f"No files found matching '{input_arg}'")
            sys.exit(1)
    else:
        input_path = input_arg

    extract_content(input_path, output_path)
