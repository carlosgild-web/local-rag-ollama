"""Generates the .docx / .pdf corpus fixtures that need binary libraries.

Run once with the backend venv active, from backend/:
    python tests/corpus/generate_extra.py

Only re-run if you intend to regenerate these fixtures from scratch --
the committed binary files are the actual fixtures used by tests.
"""

from pathlib import Path

import docx
import pymupdf
from PIL import Image, ImageDraw, ImageFont

CORPUS_DIR = Path(__file__).parent
WINDOWS_ARIAL = Path("C:/Windows/Fonts/arial.ttf")


def build_docx():
    doc = docx.Document()
    doc.add_heading("Home Network Setup Guide", level=1)
    doc.add_paragraph(
        "Setting up a reliable home network starts with placing the router "
        "in a central, open location rather than tucked inside a closet or "
        "behind large furniture, since walls and metal objects weaken the "
        "wireless signal."
    )
    doc.add_heading("Choosing a Channel", level=2)
    doc.add_paragraph(
        "Wireless routers can broadcast on several channels, and neighboring "
        "networks on the same channel cause interference. Most routers can "
        "scan and pick the least congested channel automatically, which is "
        "usually the simplest fix for a slow connection."
    )
    doc.add_heading("Securing the Network", level=2)
    doc.add_paragraph(
        "A strong, unique password and WPA3 encryption, if the router "
        "supports it, keep a home network reasonably secure. The default "
        "administrator password should always be changed on first setup."
    )
    doc.save(CORPUS_DIR / "home-network-setup.docx")

    doc = docx.Document()
    doc.add_heading("Guía de Configuración de Red Doméstica", level=1)
    doc.add_paragraph(
        "Configurar una red doméstica confiable comienza por colocar el "
        "router en un lugar central y despejado, en lugar de dentro de un "
        "clóset o detrás de muebles grandes, ya que las paredes y los "
        "objetos metálicos debilitan la señal inalámbrica."
    )
    doc.add_heading("Elegir un Canal", level=2)
    doc.add_paragraph(
        "Los routers inalámbricos pueden transmitir en varios canales, y las "
        "redes vecinas en el mismo canal causan interferencia. La mayoría de "
        "los routers pueden escanear y elegir automáticamente el canal menos "
        "congestionado, lo cual suele ser la solución más simple para una "
        "conexión lenta."
    )
    doc.add_heading("Asegurar la Red", level=2)
    doc.add_paragraph(
        "Una contraseña fuerte y única, junto con cifrado WPA3 si el router "
        "lo admite, mantienen una red doméstica razonablemente segura. La "
        "contraseña de administrador predeterminada siempre debe cambiarse "
        "en la primera configuración."
    )
    doc.save(CORPUS_DIR / "configuracion-red-hogar.docx")


def build_text_pdf():
    text = (
        "Energy Saving Tips for the Home\n\n"
        "Small, consistent changes around the house often save more energy "
        "over a year than one expensive upgrade.\n\n"
        "Switching to LED bulbs uses roughly 75 percent less energy than "
        "incandescent bulbs and lasts many times longer, which also reduces "
        "how often bulbs need replacing.\n\n"
        "Sealing drafts around windows and doors keeps heated or cooled air "
        "inside, reducing how hard a heating or cooling system has to work "
        "to maintain a comfortable temperature.\n\n"
        "Unplugging chargers and electronics that are not in use eliminates "
        "the small but constant draw known as standby power, which adds up "
        "across many devices in a household."
    )
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(pymupdf.Rect(50, 50, 550, 750), text, fontsize=12)
    document.save(CORPUS_DIR / "energy-saving-tips.pdf")
    document.close()


def build_scanned_pdf():
    """A page with text baked into an image and no text layer, to exercise
    the OCR fallback path for low-text-yield pages."""
    text = (
        "Consejos para Ahorrar Energia en Casa\n\n"
        "Cambiar a bombillas LED consume aproximadamente 75 por ciento menos\n"
        "energia que las bombillas incandescentes y dura muchas veces mas,\n"
        "lo cual tambien reduce la frecuencia con la que hay que reemplazarlas.\n\n"
        "Sellar las corrientes de aire alrededor de ventanas y puertas\n"
        "mantiene el aire climatizado dentro de la casa, reduciendo el\n"
        "esfuerzo del sistema de calefaccion o aire acondicionado.\n\n"
        "Desconectar cargadores y aparatos que no se estan usando elimina\n"
        "el consumo en espera, que se acumula entre muchos dispositivos."
    )
    image = Image.new("RGB", (900, 1165), color="white")
    draw = ImageDraw.Draw(image)
    font = (
        ImageFont.truetype(str(WINDOWS_ARIAL), 20)
        if WINDOWS_ARIAL.exists()
        else ImageFont.load_default()
    )
    draw.multiline_text((40, 40), text, fill="black", font=font, spacing=10)

    img_path = CORPUS_DIR / "_scanned_page.jpg"
    image.save(img_path, format="JPEG", quality=85)

    document = pymupdf.open()
    page = document.new_page(width=image.width, height=image.height)
    page.insert_image(pymupdf.Rect(0, 0, image.width, image.height), filename=str(img_path))
    document.save(CORPUS_DIR / "consejos-ahorro-energia-scanned.pdf")
    document.close()
    img_path.unlink()


if __name__ == "__main__":
    build_docx()
    build_text_pdf()
    build_scanned_pdf()
    print("Generated corpus fixtures.")
