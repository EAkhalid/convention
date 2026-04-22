import os
import io
import qrcode
from datetime import datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader, PdfWriter
from pyhanko.sign import signers
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter

# ... (tes autres imports) ...
from reportlab.lib.utils import ImageReader

def ajouter_tampon_visuel(input_pdf_path, output_pdf_path, texte, x, y, qr_data=None, target_page=0, image_signature_path=None):
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=A4)
    can.setFont("Helvetica-Bold", 9)
    can.setFillColorRGB(0.1, 0.2, 0.5)
    
    # 1. Dessiner l'image de la signature (PNG) si elle est fournie
    if image_signature_path and os.path.exists(image_signature_path):
        img = ImageReader(image_signature_path)
        # On la dessine juste au-dessus du texte (y + 10)
        can.drawImage(img, x, y + 10, width=80, preserveAspectRatio=True, mask='auto')

    # 2. Écrire les lignes de texte en dessous
    for i, ligne in enumerate(texte.split('\n')):
        can.drawString(x, y - (i * 12), ligne)
        
    # 3. Ajouter le QR Code (pour le doyen)
    if qr_data:
        qr = qrcode.make(qr_data)
        qr_io = io.BytesIO()
        qr.save(qr_io, format='PNG')
        qr_io.seek(0)
        qr_image = ImageReader(qr_io)
        can.drawImage(qr_image, x, y - 90, width=60, height=60)
        
    can.save()
    packet.seek(0)
    
    # ... (le reste de la fonction reste identique : merge_page, etc.) ...
    new_pdf = PdfReader(packet)
    existing_pdf = PdfReader(input_pdf_path)
    output = PdfWriter()
    for i, page in enumerate(existing_pdf.pages):
        if i == target_page:
            page.merge_page(new_pdf.pages[0])
        output.add_page(page)
    with open(output_pdf_path, "wb") as outputStream:
        output.write(outputStream)


def signer_document_pdf(input_pdf_path, output_pdf_path, p12_path, p12_password, reason, location, signer_name, x_coord=100, y_coord=100, qr_data=None, page_number=1, image_signature_path=None):
    # ...
    try:
        temp_pdf_path = input_pdf_path.replace('.pdf', '_temp.pdf')
        date_signature = datetime.now().strftime("%d/%m/%Y %H:%M")
        texte_tampon = f"Approuvé par : {signer_name}\nRôle : {location}\nDate : {date_signature}"
        target_page_index = int(page_number) - 1
        
        # On passe le chemin de l'image à la fonction de dessin
        ajouter_tampon_visuel(input_pdf_path, temp_pdf_path, texte_tampon, x=x_coord, y=y_coord, qr_data=qr_data, target_page=target_page_index, image_signature_path=image_signature_path)
        
        # ... (le reste de la signature pyHanko reste identique) ...
        
        # Étape B : Appliquer le scellé cryptographique avec pyHanko (via les fichiers .pem)
        keystore_dir = os.path.dirname(p12_path)
        key_path = os.path.join(keystore_dir, 'test_key.pem')
        cert_path = os.path.join(keystore_dir, 'test_cert.pem')
        
        signer = signers.SimpleSigner.load(
            key_file=key_path, 
            cert_file=cert_path
        )
        
        with open(temp_pdf_path, 'rb') as doc:
            # Utiliser IncrementalPdfFileWriter pour ne pas écraser les signatures précédentes
            pdf_writer = IncrementalPdfFileWriter(doc)
            signature_meta = signers.PdfSignatureMetadata(
                field_name=f'Signature_{location.replace(" ", "_")}', 
                location=location,
                reason=reason,
            )
            out_stream = signers.sign_pdf(
                pdf_writer, 
                signature_meta=signature_meta, 
                signer=signer
            )
            
            with open(output_pdf_path, 'wb') as out_file:
                out_file.write(out_stream.read())
                
        # Nettoyage du fichier temporaire
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
            
        return True
    
    except Exception as e:
        print(f"Erreur lors de la signature ({location}) : {e}")
        return False
def apposer_tampons_multiples(input_pdf_path, output_pdf_path, convention, vice_doyen_user, start_x, y, target_page):
    """L'administrateur dessine les 3 tampons visuels : Encadrant, Coordinateur, et Vice-Doyen."""
    try:
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=A4)
        can.setFont("Helvetica-Bold", 9)
        can.setFillColorRGB(0.1, 0.2, 0.5)
        
        date_str = datetime.now().strftime("%d/%m/%Y")

        # --- TAMPON 1 : ENCADRANT (À la position cliquée) ---
        can.drawString(start_x, y, "L'Encadrant")
        can.drawString(start_x, y - 12, f"Pr. {convention.enseignant.last_name}")
        can.drawString(start_x, y - 24, f"Date: {date_str}")
        if convention.enseignant.signature_image and os.path.exists(convention.enseignant.signature_image.path):
            img = ImageReader(convention.enseignant.signature_image.path)
            can.drawImage(img, start_x, y + 10, width=70, preserveAspectRatio=True, mask='auto')

        # --- TAMPON 2 : COORDINATEUR (Décalé au centre) ---
        coord_x = start_x + 160
        can.drawString(coord_x, y, "La Coordination")
        can.drawString(coord_x, y - 12, "Filière validée")
        can.drawString(coord_x, y - 24, f"Date: {date_str}")
        # Si tu as une image pour le coordinateur, on pourrait l'ajouter ici de la même manière

        # --- TAMPON 3 : VICE-DOYEN (Décalé à droite) ---
        admin_x = start_x + 320
        can.drawString(admin_x, y, "Le Vice-Doyen")
        if vice_doyen_user:
            can.drawString(admin_x, y - 12, f"Pr. {vice_doyen_user.last_name}")
            
            # On dessine la vraie signature PNG du Vice-Doyen
            if vice_doyen_user.signature_image and os.path.exists(vice_doyen_user.signature_image.path):
                img = ImageReader(vice_doyen_user.signature_image.path)
                can.drawImage(img, admin_x, y + 10, width=70, preserveAspectRatio=True, mask='auto')
                
        can.drawString(admin_x, y - 24, f"Date: {date_str}")

        can.save()
        packet.seek(0)
        
        # Fusionner avec le PDF
        new_pdf = PdfReader(packet)
        existing_pdf = PdfReader(input_pdf_path)
        output = PdfWriter()
        
        for i, page in enumerate(existing_pdf.pages):
            if i == target_page:
                page.merge_page(new_pdf.pages[0])
            output.add_page(page)
            
        with open(output_pdf_path, "wb") as outputStream:
            output.write(outputStream)
            
        return True
    except Exception as e:
        print(f"Erreur lors de la préparation Admin : {e}")
        return False


def apposer_3_tampons_libres(input_pdf_path, output_pdf_path, convention, vice_doyen_user, coords):
    """L'administrateur place 3 tampons librement, potentiellement sur des pages différentes."""
    try:
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=A4)
        can.setFont("Helvetica-Bold", 9)
        date_str = datetime.now().strftime("%d/%m/%Y")

        existing_pdf = PdfReader(input_pdf_path)
        num_pages = len(existing_pdf.pages)

        # On parcourt TOUTES les pages du PDF original
        for i in range(num_pages):
            current_page_number = i + 1  # Les pages commencent à 1 pour l'utilisateur

            # --- 1. TAMPON ENCADRANT (BLEU) ---
            if 'encadrant' in coords and coords['encadrant'][2] == current_page_number:
                x, y, _ = coords['encadrant']
                can.setFillColorRGB(0.1, 0.4, 0.8)
                can.drawString(x, y, "L'Encadrant")
                can.drawString(x, y - 12, f"Pr. {convention.enseignant.last_name}")
                can.drawString(x, y - 24, f"Date: {date_str}")
                if convention.enseignant.signature_image and os.path.exists(convention.enseignant.signature_image.path):
                    img = ImageReader(convention.enseignant.signature_image.path)
                    can.drawImage(img, x, y + 10, width=70, preserveAspectRatio=True, mask='auto')

            # --- 2. TAMPON COORDINATEUR (VERT) ---
            if 'coordinateur' in coords and coords['coordinateur'][2] == current_page_number:
                x, y, _ = coords['coordinateur']
                can.setFillColorRGB(0.1, 0.6, 0.2)
                can.drawString(x, y, "La Coordination")
                can.drawString(x, y - 12, "Filière validée")
                can.drawString(x, y - 24, f"Date: {date_str}")

            # --- 3. TAMPON VICE-DOYEN (VIOLET) ---
            if 'doyen' in coords and coords['doyen'][2] == current_page_number:
                x, y, _ = coords['doyen']
                can.setFillColorRGB(0.1, 0.1, 0.3)
                can.drawString(x, y, "Le Vice-Doyen")
                if vice_doyen_user:
                    can.drawString(x, y - 12, f"Pr. {vice_doyen_user.last_name}")
                    if vice_doyen_user.signature_image and os.path.exists(vice_doyen_user.signature_image.path):
                        img = ImageReader(vice_doyen_user.signature_image.path)
                        can.drawImage(img, x, y + 10, width=70, preserveAspectRatio=True, mask='auto')
                can.drawString(x, y - 24, f"Date: {date_str}")

            # On passe à la page suivante du calque
            can.showPage() 

        can.save()
        packet.seek(0)
        
        # Fusion page par page
        new_pdf = PdfReader(packet)
        output = PdfWriter()
        
        for i in range(num_pages):
            page = existing_pdf.pages[i]
            page.merge_page(new_pdf.pages[i])
            output.add_page(page)
            
        with open(output_pdf_path, "wb") as outputStream:
            output.write(outputStream)
            
        return True
    except Exception as e:
        print(f"Erreur PDF Admin : {e}")
        return False
