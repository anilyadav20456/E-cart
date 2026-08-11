try:
    from xhtml2pdf import pisa
except Exception:
    pisa = None

from io import BytesIO

def generate_pdf(template_html):
    if pisa is None:
        return None
    pdf = BytesIO()
    try:
        pisa_status = pisa.CreatePDF(template_html, dest=pdf, encoding='utf-8')
        if pisa_status.err:
            return None
        return pdf
    except Exception:
        return None
