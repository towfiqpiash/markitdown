import sys
from markitdown import MarkItDown
from fpdf import FPDF

# Create a dummy PDF
pdf = FPDF()
pdf.add_page()
pdf.set_font("Arial", size=12)
pdf.cell(200, 10, txt="Welcome to MarkItDown", ln=True, align='C')
pdf.output("test.pdf")

# Convert it
md = MarkItDown()
try:
    result = md.convert("test.pdf")
    print(result.text_content)
except Exception as e:
    print(f"Error: {e}")
