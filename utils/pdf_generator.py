import sys
import types
import importlib.machinery
import traceback
from io import BytesIO

# Safely handle broken/incompatible server pyhanko packages (e.g. on PythonAnywhere)
# by creating a dynamic MagicModule finder that allows xhtml2pdf to import cleanly.
class MagicModule(types.ModuleType):
    def __init__(self, name):
        super().__init__(name)
        self.__path__ = []
    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        val = MagicModule(f"{self.__name__}.{name}")
        setattr(self, name, val)
        sys.modules[f"{self.__name__}.{name}"] = val
        return val

class CustomMetaPathFinder:
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith('pyhanko') or fullname.startswith('pyhanko_certvalidator'):
            mod = MagicModule(fullname)
            sys.modules[fullname] = mod
            return importlib.machinery.ModuleSpec(fullname, None, is_package=True)
        return None

if not any(isinstance(f, CustomMetaPathFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, CustomMetaPathFinder())

pisa = None
pisa_import_error = None

try:
    from xhtml2pdf import pisa
except Exception as err:
    pisa = None
    pisa_import_error = str(err)
    print(f"[PDF Generator] xhtml2pdf import failed: {err}", file=sys.stderr)

def generate_pdf(template_html):
    global pisa, pisa_import_error
    if pisa is None:
        try:
            from xhtml2pdf import pisa
        except Exception as err:
            pisa_import_error = str(err)
            print(f"[PDF Generator] xhtml2pdf retry import failed: {err}", file=sys.stderr)
            return None

    pdf = BytesIO()
    try:
        pisa_status = pisa.CreatePDF(template_html, dest=pdf, encoding='utf-8')
        pdf_bytes = pdf.getvalue()
        if len(pdf_bytes) > 100:
            return pdf

        if pisa_status and pisa_status.err:
            print(f"[PDF Generator] pisa.CreatePDF error code: {pisa_status.err}", file=sys.stderr)
            return None
        return pdf
    except Exception as e:
        print(f"[PDF Generator] Exception during pisa.CreatePDF: {e}", file=sys.stderr)
        traceback.print_exc()
        return None
