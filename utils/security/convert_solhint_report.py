#!/usr/bin/env python3
import json
import sys

def json_to_markdown(json_file, markdown_file):
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    # Create markdown table header
    markdown_content = "# Solhint Report\n\n"
    markdown_content += "## Summary\n\n"
    
    # Count issues by severity
    error_count = 0
    warning_count = 0
    info_count = 0
    
    for item in data:
        severity = item.get('severity', '').lower()
        if severity == 'error':
            error_count += 1
        elif severity == 'warning':
            warning_count += 1
        elif severity == 'info':
            info_count += 1
    
    markdown_content += f"- **Errors:** {error_count}\n"
    markdown_content += f"- **Warnings:** {warning_count}\n"
    markdown_content += f"- **Info:** {info_count}\n\n"
    
    # Create issues table
    markdown_content += "## Issues\n\n"
    markdown_content += "| Severity | Rule | Description | File | Line |\n"
    markdown_content += "|----------|------|-------------|------|------|\n"
    
    for item in data:
        severity = item.get('severity', '')
        rule = item.get('ruleId', '')
        message = item.get('message', '')
        file = item.get('filePath', '')
        line = item.get('line', '')
        
        markdown_content += f"| {severity} | {rule} | {message} | [{file.split("/")[-1]}](../{file}#L{line}) |\n"
    
    with open(markdown_file, 'w') as f:
        f.write(markdown_content)

if __name__ == "__main__":
    # Check if input and output file paths are provided as arguments
    if len(sys.argv) >= 3:
        json_file = sys.argv[1]
        markdown_file = sys.argv[2]
    else:
        # Default filenames if no arguments are provided
        json_file = 'solhint-report.json'
        markdown_file = 'solhint-report.md'
    
    json_to_markdown(json_file, markdown_file)
    print(f"Converted {json_file} to {markdown_file}")