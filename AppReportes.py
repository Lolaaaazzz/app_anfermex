# reportes.py
# App de reportes ANFERMEX
# - Plantillas con EXACTAMENTE N filas en blanco (0–500) y luego TOTALES
# - Banda amarilla en TOTALES, MINA SANTA FE, columna "No.", encabezados con salto
# - Cargas, Descargas (sin EMPRESA), Empresas, Operadores, filtros básicos

import tkinter as tk
from tkinter import ttk
from tkcalendar import DateEntry
import mysql.connector
from datetime import datetime, timedelta, date
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
import os
import re
import traceback
import threading

# -----------------------------
# Config BD y recursos
# -----------------------------
DB_CONFIG = {
    'host': '127.0.0.1',
    'user': 'root',
    'password': 'ALdrinruiz01',
    'database': 'sedena'
}
LOGO_PATH = "ANFERMEX MINERIA.jpg"

# -----------------------------
# Estilos reportlab
# -----------------------------
_styles = getSampleStyleSheet()
WRAP_CELL_STYLE = ParagraphStyle(
    "WrapCell", parent=_styles["BodyText"],
    fontName="Helvetica", fontSize=7, leading=9, alignment=0
)
WRAP_HEADER_STYLE = ParagraphStyle(
    "WrapHeader", parent=_styles["BodyText"],
    fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=1  # títulos centrados
)
TICKET_CELL_STYLE = ParagraphStyle(
    "TicketCell", parent=_styles["BodyText"],
    fontName="Helvetica", fontSize=8, leading=9, alignment=1  # centrado
)

def envolver_encabezados(datos, columnas, reemplazos=None):
    """Convierte los encabezados (fila 0) a Paragraph y permite insertar saltos <br/> por columna."""
    if not datos:
        return datos
    hdr = list(datos[0])
    if reemplazos:
        for idx, txt in list(reemplazos.items()):
            if 0 <= idx < len(hdr):
                hdr[idx] = Paragraph(str(txt), WRAP_HEADER_STYLE)
    for col in columnas:
        if 0 <= col < len(hdr):
            txt = hdr[col]
        else:
            continue
        if not isinstance(txt, Paragraph):
            hdr[col] = Paragraph(str(txt if txt is not None else ""), WRAP_HEADER_STYLE)
    datos[0] = hdr
    return datos

def aplicar_wrap_en_columnas(datos, columnas_wrap, fila_header=0):
    if not datos:
        return datos
    env = []
    for i, fila in enumerate(datos):
        nueva = []
        es_total = False
        if fila and not isinstance(fila[0], Paragraph):
            es_total = str(fila[0]).strip().upper().startswith("TOTAL")
        for j, celda in enumerate(fila):
            if isinstance(celda, Paragraph):
                nueva.append(celda); continue
            if j in columnas_wrap and not es_total:
                style = WRAP_HEADER_STYLE if i == fila_header else WRAP_CELL_STYLE
                nueva.append(Paragraph("" if celda is None else str(celda), style))
            else:
                nueva.append("" if celda is None else str(celda))
        env.append(nueva)
    return env

def ajustar_anchos_a_pagina(anchos, es_horizontal, left=0.5*inch, right=0.5*inch):
    if not anchos:
        return anchos
    page_width_in = 11.0 if es_horizontal else 8.5
    disponible = page_width_in*inch - (left + right)
    total = sum(anchos)
    if total <= 0:
        return anchos
    scale = disponible / total
    return [w*scale for w in anchos]

def quitar_rango_fechas_titulo(titulo):
    """Elimina ' (dd/mm/yyyy - dd/mm/yyyy)' del título si existe."""
    return re.sub(r"\s*\(\d{2}/\d{2}/\d{4}\s*-\s*\d{2}/\d{2}/\d{4}\)\s*", "", titulo).strip()

def insertar_filas_en_blanco(datos, n):
    """
    Inserta EXACTAMENTE n filas en blanco después del header (fila 0),
    NUMERANDO la primera columna 'No.' desde 1..n.
    """
    n = max(0, min(500, int(n or 0)))
    if not datos:
        return datos
    cols = len(datos[0])
    out = [datos[0]]
    for i in range(1, n + 1):
        fila = [""] * cols
        fila[0] = str(i)  # numerar columna "No."
        out.append(fila)
    return out

# --- util para encajar texto en una sola línea dentro del ancho disponible
def ticket_paragraph(texto, max_width_pts, min_size=5, max_size=8, font="Helvetica"):
    """
    Devuelve un Paragraph centrado con el tamaño de fuente más grande posible
    (entre min_size y max_size) que quepa en max_width_pts en una sola línea.
    """
    txt = "" if texto is None else str(texto)
    if txt == "":
        return Paragraph("", TICKET_CELL_STYLE)

    size = max_size
    while size >= min_size:
        w = pdfmetrics.stringWidth(txt, font, size)
        if w <= max_width_pts:
            break
        size -= 0.5  # bajamos de a 0.5pt para mayor precisión
    # Envolvemos con etiqueta <font size="">
    html = f'<font size="{size:.1f}">{txt}</font>'
    return Paragraph(html, TICKET_CELL_STYLE)

# -----------------------------
# Canvas con membrete
# -----------------------------
class LetterheadCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        self.report_type_footer = kwargs.pop('report_type_footer', 'REPORTE GENERAL')
        self.header_subtitle = kwargs.pop('header_subtitle', None)
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.page_num = 0
        self.logo_path = LOGO_PATH

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()
        self.page_num += 1

    def save(self):
        num_pages = len(self._saved_page_states)
        for i, state in enumerate(self._saved_page_states):
            self.__dict__.update(state)
            self.page_num = i + 1
            self.draw_header_footer(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_header_footer(self, total_pages):
        self.saveState()
        page_width, page_height = self._pagesize

        # Header con logo (si existe)
        if os.path.exists(self.logo_path):
            try:
                logo_width = page_width - 2 * inch
                logo_height = 1.5 * inch
                x = (page_width - logo_width) / 2
                self.drawImage(self.logo_path, x, page_height - 1.5 * inch,
                               width=logo_width, height=logo_height,
                               preserveAspectRatio=True, anchor='n', mask='auto')
            except Exception as e:
                print(f"Error al cargar el logo: {e}")

        # Subtítulo (si se definió)
        if self.header_subtitle:
            self.setFont("Helvetica-Bold", 11)
            self.setFillColor(colors.black)
            self.drawCentredString(page_width / 2.0, page_height - 1.75 * inch, self.header_subtitle)

        # Footer
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawRightString(page_width - 0.75 * inch, 0.35 * inch, f"Página {self.page_num} de {total_pages}")
        self.drawString(0.75 * inch, 0.35 * inch, self.report_type_footer)
        self.restoreState()

# -----------------------------
# Generación PDF
# -----------------------------
def generar_reporte_pdf(nombre_archivo, titulo_principal, datos_tabla, anchos_columnas, pie_pagina_texto, es_horizontal=True, header_subtitle=None):
    try:
        page_size = landscape(letter) if es_horizontal else letter
        doc = SimpleDocTemplate(
            nombre_archivo, pagesize=page_size,
            topMargin=2.0*inch, bottomMargin=0.8*inch,
            leftMargin=0.5*inch, rightMargin=0.5*inch
        )
        story = []
        style_titulo = ParagraphStyle(
            'ReportTitle', parent=_styles['h2'],
            fontName="Helvetica-Bold", fontSize=14, alignment=1, spaceAfter=0.2*inch
        )
        story.append(Paragraph(titulo_principal, style_titulo))

        anchos_columnas = ajustar_anchos_a_pagina(anchos_columnas, es_horizontal, left=0.5*inch, right=0.5*inch)
        tabla = Table(datos_tabla, colWidths=anchos_columnas, repeatRows=1)

        style = [
            ('BACKGROUND', (0,0), (-1,0), colors.Color(0.85, 0.85, 0.85)),
            ('TEXTCOLOR', (0,0), (-1,0), colors.black),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('FONTNAME', (0,0), (-1,0), "Helvetica-Bold"),
            ('FONTSIZE', (0,0), (-1,0), 9),
            ('BOTTOMPADDING', (0,0), (-1,0), 8),
            ('TOPPADDING', (0,0), (-1,0), 8),

            ('FONTSIZE', (0,1), (-1,-1), 8),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
        ]

        # Fila de totales
        for i, row in enumerate(datos_tabla):
            if not row:
                continue
            first = row[0]
            txt = first.getPlainText().strip().upper() if isinstance(first, Paragraph) else str(first).strip().upper()
            if txt.startswith("TOTALES:") or txt.startswith("TOTAL:"):
                style.extend([
                    ('BACKGROUND', (0, i), (-1, i), colors.yellow),
                    ('TEXTCOLOR', (0, i), (-1, i), colors.black),
                    ('FONTNAME', (0, i), (-1, i), "Helvetica-Bold"),
                    ('FONTSIZE', (0, i), (-1, i), 8),
                    ('ALIGN', (0, i), (0, i), 'LEFT'),
                ])
                span_end = getattr(generar_reporte_pdf, "_total_span_end_col", None)
                if isinstance(span_end, int) and span_end >= 0:
                    style.append(('SPAN', (0, i), (span_end, i)))

        # Alineaciones finas
        if hasattr(generar_reporte_pdf, "_alineaciones"):
            style.extend(generar_reporte_pdf._alineaciones)
            generar_reporte_pdf._alineaciones = []

        tabla.setStyle(TableStyle(style))
        story.append(tabla)

        canvas_maker = lambda *args, **kwargs: LetterheadCanvas(
            *args, report_type_footer=pie_pagina_texto,
            header_subtitle=header_subtitle, **kwargs
        )
        doc.build(story, canvasmaker=canvas_maker)
        return True
    except Exception:
        traceback.print_exc()
        return False

# -----------------------------
# DB helpers
# -----------------------------
def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

# -----------------------------
# CARGAS (SIN EMPRESA)
# -----------------------------
def obtener_datos_cargas(fecha_inicio, fecha_fin, search_text=None):
    titulo = f"REPORTE DE CARGAS ({fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')})"
    encabezados = ["No","FOL.","FECHA","HORA","OPERADOR","TEL. OPERADOR",
                   "PLACAS TRACTO.","GÓNDOLA 1","GÓNDOLA 2","DESTINO","M³ CARGADOS"]
    anchos = [0.45*inch, 0.60*inch, 0.85*inch, 0.70*inch,
              1.35*inch, 0.95*inch, 0.95*inch, 0.85*inch, 0.85*inch, 1.10*inch, 0.90*inch]

    sql = """
        SELECT 
            c.folio, c.fecha_carga, c.hora_carga,
            COALESCE(c.nombre_operador,"") AS operador,
            COALESCE(o.numero_telefono,"") AS tel_operador,
            c.placas_tractocamion, c.placas_gondola1, c.placas_gondola2,
            c.destino, c.total_m3_cargados
        FROM cargasdescargas c
        LEFT JOIN operadores o ON o.numero_operador = c.id_operador
        WHERE c.fecha_carga BETWEEN %s AND %s
        ORDER BY c.fecha_carga, c.hora_carga, c.folio;
    """

    total_m3 = 0.0
    try:
        con = get_connection(); cur = con.cursor()
        cur.execute(sql, (fecha_inicio, fecha_fin))
        filas = cur.fetchall()

        datos = [encabezados]
        no = 1
        for f in filas:
            (folio, fecha, hora, operador, tel,
             placa_tr, g1, g2, destino, m3) = f
            datos.append([
                str(no),
                str(folio or "-"),
                fecha.strftime("%d/%m/%Y") if fecha else "-",
                str(hora or "-"),
                str(operador or "-"),
                str(tel or "-"),
                str(placa_tr or "-"),
                str(g1 or "-"),
                str(g2 or "-"),
                str(destino or "-"),
                f"{float(m3 or 0):.2f}",
            ])
            total_m3 += float(m3 or 0)
            no += 1

        if filas:
            datos.append(["TOTALES:"] + [""]*9 + [f"{total_m3:,.2f}"])

        datos = envolver_encabezados(
            datos, list(range(len(encabezados))),
            reemplazos={6:"PLACAS<br/>TRACTO.",7:"GÓNDOLA<br/>1",8:"GÓNDOLA<br/>2",10:"M³<br/>CARGADOS"}
        )
        datos = aplicar_wrap_en_columnas(datos, columnas_wrap={4,9})

        generar_reporte_pdf._alineaciones = [
            ('ALIGN', (0,0), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (3,-1), 'CENTER'),
            ('ALIGN', (4,1), (4,-1), 'LEFT'),
            ('ALIGN', (5,1), (5,-1), 'CENTER'),
            ('ALIGN', (6,1), (8,-1), 'CENTER'),
            ('ALIGN', (9,1), (9,-1), 'LEFT'),
            ('ALIGN', (10,1), (10,-1), 'CENTER'),
        ]
        generar_reporte_pdf._total_span_end_col = 9
        return titulo, datos, anchos, "REPORTE DE CARGAS"
    finally:
        try: cur.close()
        except: pass
        try: con.close()
        except: pass

# -----------------------------
# DESCARGAS (SIN EMPRESA) + tickets encajados en una línea
# -----------------------------
def obtener_datos_descargas(fecha_inicio, fecha_fin, search_text=None):
    titulo = f"REPORTE DE DESCARGAS ({fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')})"
    encabezados = [
        "No", "FOL.", "FECHA", "DESTINO",
        "OPERADOR",
        "PLACAS G1", "PLACAS G2",
        "M³ CARG. MINA.", "M³ DESC. G1", "M³ DESC. G2", "M³ TOTAL DESC.",
        "TICKET G1", "TICKET G2",
    ]
    anchos = [
        0.45*inch, 0.60*inch, 0.85*inch, 1.00*inch,
        1.25*inch,
        0.75*inch, 0.75*inch,
        0.75*inch, 0.75*inch, 0.75*inch, 0.85*inch,
        1.35*inch, 1.35*inch,
    ]

    # Para calcular el font-size correcto necesitamos el ancho real (tras escalar a la página)
    anchos_reales = ajustar_anchos_a_pagina(anchos, True, left=0.5*inch, right=0.5*inch)
    # Restamos un padding aproximado (6pt por lado)
    ticket1_max = max(0, anchos_reales[11] - 12)
    ticket2_max = max(0, anchos_reales[12] - 12)

    sql = """
        SELECT 
            c.folio, d.fecha_descarga, d.destino, d.nombre_operador_descarga,
            d.placas_gondola1_descarga, d.placas_gondola2_descarga,
            d.m3_cargados, d.m3_descargados_g1, d.m3_descargados_g2, d.m3_descargados,
            d.codigo_barras_ticket_descarga, d.codigo_barras_ticket_descarga_1
        FROM descargas d
        JOIN cargasdescargas c ON d.id_carga = c.id_carga
        WHERE d.fecha_descarga BETWEEN %s AND %s
        ORDER BY d.fecha_descarga, c.folio;
    """

    total_cargado = total_g1 = total_g2 = total_descargado_final = 0.0
    try:
        con = get_connection(); cur = con.cursor()
        cur.execute(sql, (fecha_inicio, fecha_fin))
        filas = cur.fetchall()

        datos = [encabezados]
        no = 1
        for fila in filas:
            (folio, fecha, destino, operador, g1, g2, m_carg, m_g1, m_g2, m_tot, t1, t2) = fila

            # Operador: si viene "1 - Nombre | tel", limpiamos prefijo numérico y teléfono
            op = str(operador or "-")
            op = re.sub(r"^\s*\d+\s*[-.\)]\s*", "", op)          # quita "1 -", "1.", "1)"
            op = re.sub(r"\s*\|.*$", "", op)                     # quita " | 555-..."
            op = op.strip()

            # Tickets: en UNA sola línea, ajustando el tamaño para que quepa
            p_t1 = ticket_paragraph(t1, ticket1_max)
            p_t2 = ticket_paragraph(t2, ticket2_max)

            datos.append([
                str(no),
                str(folio or "-"),
                fecha.strftime("%d/%m/%Y") if fecha else "-",
                str(destino or "-"),
                op,
                str(g1 or "-"),
                str(g2 or "-"),
                f"{float(m_carg or 0):.2f}",
                f"{float(m_g1 or 0):.2f}",
                f"{float(m_g2 or 0):.2f}",
                f"{float(m_tot or 0):.2f}",
                p_t1,
                p_t2,
            ])
            total_cargado += float(m_carg or 0); total_g1 += float(m_g1 or 0); total_g2 += float(m_g2 or 0); total_descargado_final += float(m_tot or 0)
            no += 1

        if filas:
            datos.append(["TOTALES:"] + [""]*6 + [
                f"{total_cargado:,.2f}", f"{total_g1:,.2f}", f"{total_g2:,.2f}", f"{total_descargado_final:,.2f}",
            ] + ["",""])

        datos = envolver_encabezados(
            datos, list(range(len(encabezados))),
            reemplazos={
                5:"PLACAS<br/>G1", 6:"PLACAS<br/>G2",
                7:"M³ CARG.<br/>MINA.", 8:"M³ DESC.<br/>G1",
                9:"M³ DESC.<br/>G2", 10:"M³ TOTAL<br/>DESC."
            }
        )
        datos = aplicar_wrap_en_columnas(datos, columnas_wrap={3,4})

        generar_reporte_pdf._alineaciones = [
            ('ALIGN', (0,0), (2,-1), 'CENTER'),
            ('ALIGN', (3,1), (4,-1), 'LEFT'),
            ('ALIGN', (5,1), (10,-1), 'CENTER'),  # placas y métricas
            ('ALIGN', (11,1), (12,-1), 'CENTER'), # tickets (Paragraph centrado)
        ]
        generar_reporte_pdf._total_span_end_col = 6
        return titulo, datos, anchos, "REPORTE DETALLADO DE DESCARGAS"
    finally:
        try: cur.close()
        except: pass
        try: con.close()
        except: pass

# -----------------------------
# EMPRESAS (sin cambios funcionales)
# -----------------------------
def obtener_datos_empresas(search_text=None):
    titulo = "CATÁLOGO DE EMPRESAS"
    encabezados = ["No.","ID","NOMBRE DE LA EMPRESA","PLAZO CRÉDITO (DÍAS)","BANCO","NÚMERO DE CUENTA"]
    anchos = [0.45*inch, 0.7*inch, 2.4*inch, 1.2*inch, 1.2*inch, 2.0*inch]

    sql = """
        SELECT id_empresa, nombre_empresa, plazo_credito_dias, banco, numero_cuenta_bancaria
        FROM empresas
        ORDER BY nombre_empresa;
    """
    try:
        con = get_connection(); cur = con.cursor()
        cur.execute(sql)
        filas = cur.fetchall()
        datos = [encabezados]
        no = 1
        for f in filas:
            datos.append([
                str(no),
                str(f[0] or "-"), str(f[1] or "-"), str(f[2] or "-"),
                str(f[3] or "-"), str(f[4] or "-")
            ]); no += 1
        datos.append(["TOTAL:", str(len(filas)), "", "", "", ""])

        datos = envolver_encabezados(datos, list(range(len(encabezados))))
        datos = aplicar_wrap_en_columnas(datos, columnas_wrap=set())
        generar_reporte_pdf._alineaciones = [
            ('ALIGN', (0,0), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'LEFT'),
            ('ALIGN', (3,1), (5,-1), 'CENTER'),
        ]
        generar_reporte_pdf._total_span_end_col = None
        return titulo, datos, anchos, "CATÁLOGO DE EMPRESAS"
    finally:
        try: cur.close()
        except: pass
        try: con.close()
        except: pass

def obtener_datos_operadores(search_text=None, empresa_filtro=None):
    titulo = "CATÁLOGO DE OPERADORES"
    encabezados = ["No.", "NÚMERO OP.", "NOMBRE OPERADOR", "TELÉFONO", "EMPRESA", "PLACAS TRACTO", "GÓNDOLA 1", "GÓNDOLA 2", "CAPACIDAD (M³)"]
    anchos = [0.45*inch, 0.9*inch, 2.0*inch, 1.1*inch, 1.6*inch, 1.1*inch, 1.1*inch, 1.1*inch, 1.1*inch]

    base_sql = """
        SELECT o.numero_operador, o.nombre_operador, o.numero_telefono,
               e.nombre_empresa, o.placas_tractocamion, o.placas_gondola1, o.placas_gondola2, o.capacidad_carga_m3
        FROM operadores o
        JOIN empresas e ON o.id_empresa = e.id_empresa
        {where}
        ORDER BY o.nombre_operador;
    """
    whs, params = [], []
    if empresa_filtro and empresa_filtro != "Todas":
        whs.append("e.nombre_empresa = %s"); params.append(empresa_filtro)
    if search_text:
        like = f"%{search_text.strip()}%"
        whs.append("(o.nombre_operador LIKE %s OR o.numero_operador LIKE %s OR e.nombre_empresa LIKE %s)")
        params += [like, like, like]
    where = "WHERE " + " AND ".join(whs) if whs else ""
    sql = base_sql.format(where=where)

    try:
        con = get_connection(); cur = con.cursor()
        cur.execute(sql, tuple(params))
        filas = cur.fetchall()

        datos = [encabezados]
        no = 1
        for f in filas:
            (num_op, nombre, tel, empresa, tracto, g1, g2, cap) = f
            datos.append([
                str(no),
                str(num_op or "-"),
                str(nombre or "-"),
                str(tel or "-"),
                str(empresa or "-"),
                str(tracto or "-"),
                str(g1 or "-"),
                str(g2 or "-"),
                f"{float(cap or 0):.2f}",
            ]); no += 1

        datos.append(["TOTAL:", str(len(filas))] + [""]*(len(encabezados)-2))
        datos = envolver_encabezados(datos, list(range(len(encabezados))))
        datos = aplicar_wrap_en_columnas(datos, columnas_wrap={2,4})
        generar_reporte_pdf._alineaciones = [
            ('ALIGN', (0,0), (1,-1), 'CENTER'),
            ('ALIGN', (2,1), (2,-1), 'LEFT'),
            ('ALIGN', (3,1), (3,-1), 'CENTER'),
            ('ALIGN', (4,1), (4,-1), 'LEFT'),
            ('ALIGN', (5,1), (7,-1), 'CENTER'),
            ('ALIGN', (8,1), (8,-1), 'CENTER'),
        ]
        generar_reporte_pdf._total_span_end_col = None
        return titulo, datos, anchos, "CATÁLOGO DE OPERADORES"
    finally:
        try: cur.close()
        except: pass
        try: con.close()
        except: pass

# -----------------------------
# GUI
# -----------------------------
class ReportApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Generador de Reportes ANFERMEX")
        self.root.geometry("900x560")
        self.root.configure(bg="#F0F0F0")

        style = ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('TLabel', background='#F0F0F0', font=('Helvetica', 10))
        style.configure('TButton', font=('Helvetica', 10, 'bold'), padding=5)
        style.configure('TFrame', background='#F0F0F0')
        style.configure('Header.TLabel', font=('Helvetica', 14, 'bold'), foreground='#004A5A')

        self.create_widgets()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        controls_frame = ttk.Frame(main_frame, padding="10")
        controls_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))

        status_frame = ttk.Frame(main_frame, padding="10")
        status_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(controls_frame, text="Panel de Control de Reportes", style='Header.TLabel').grid(row=0, column=0, columnspan=4, pady=(0,20), sticky="w")

        ttk.Label(controls_frame, text="Tipo de Reporte:").grid(row=1, column=0, sticky="w", pady=(0,5))
        self.report_type_var = tk.StringVar()
        self.report_type_combo = ttk.Combobox(controls_frame, textvariable=self.report_type_var,
                                              values=["Cargas","Descargas","Empresas","Operadores"], state="readonly", width=16)
        self.report_type_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(0,5))
        self.report_type_combo.bind("<<ComboboxSelected>>", self.on_report_select)

        ttk.Label(controls_frame, text="Periodo:").grid(row=2, column=0, sticky="w", pady=(0,5))
        self.period_var = tk.StringVar()
        self.period_combo = ttk.Combobox(controls_frame, textvariable=self.period_var,
                                         values=["Diario","Semanal","Mensual","Rango Personalizado"], state="readonly", width=16)
        self.period_combo.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(0,5))
        self.period_combo.bind("<<ComboboxSelected>>", self.on_period_select)

        self.date_frame = ttk.Frame(controls_frame)
        self.date_frame.grid(row=3, column=0, columnspan=4, pady=10, sticky="ew")
        self.label_fecha1 = ttk.Label(self.date_frame, text="Fecha Inicio:")
        self.cal_start = DateEntry(self.date_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')
        self.label_fecha2 = ttk.Label(self.date_frame, text="Fecha Fin:")
        self.cal_end = DateEntry(self.date_frame, width=12, background='darkblue', foreground='white', borderwidth=2, date_pattern='y-mm-dd')

        # Filtros catálogos
        self.filters_frame = ttk.LabelFrame(controls_frame, text="Filtros (catálogos)")
        self.filters_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(8,8))
        self.filters_frame.grid_remove()
        ttk.Label(self.filters_frame, text="Buscar:").grid(row=0, column=0, sticky="w", padx=(6,4), pady=4)
        self.search_var = tk.StringVar(); self.search_entry = ttk.Entry(self.filters_frame, textvariable=self.search_var, width=26)
        self.search_entry.grid(row=0, column=1, columnspan=3, sticky="ew", padx=(0,6), pady=4)
        ttk.Label(self.filters_frame, text="Empresa (Operadores):").grid(row=1, column=0, sticky="w", padx=(6,4), pady=4)
        self.emp_filter_var = tk.StringVar(value="Todas")
        self.emp_filter_cb = ttk.Combobox(self.filters_frame, textvariable=self.emp_filter_var, values=["Todas"], state="readonly", width=24)
        self.emp_filter_cb.grid(row=1, column=1, sticky="w", padx=(0,6), pady=4)

        # Plantilla en blanco
        self.blank_rows_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(controls_frame, text="Agregar filas en blanco (plantilla)", variable=self.blank_rows_var, command=self.on_toggle_blank)\
            .grid(row=5, column=0, columnspan=4, sticky="w", pady=(8,0))

        ttk.Label(controls_frame, text="Cantidad:").grid(row=6, column=0, sticky="w")
        self.blank_rows_count_var = tk.IntVar(value=20)
        self.blank_rows_spin = tk.Spinbox(controls_frame, from_=0, to=500, textvariable=self.blank_rows_count_var,
                                          width=6, state="disabled", justify="center")
        self.blank_rows_spin.grid(row=6, column=1, sticky="w")
        ttk.Label(controls_frame, text="filas").grid(row=6, column=2, sticky="w")

        self.generate_button = ttk.Button(controls_frame, text="Generar Reporte", command=self.run_report_generation)
        self.generate_button.grid(row=7, column=0, columnspan=4, pady=18, sticky="ew")

        ttk.Label(status_frame, text="Registro de Actividad", style='Header.TLabel').pack(anchor="w")
        self.log_text = tk.Text(status_frame, height=18, state="disabled", bg="#FFFFFF", relief="solid", borderwidth=1, font=("Courier New", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(10,0))

        # Defaults
        self.report_type_combo.set("Cargas")
        self.period_combo.set("Diario")
        self.on_report_select(None)
        self.on_period_select(None)
        self.log_message("Aplicación lista. Seleccione sus opciones y genere un reporte.")

    def on_toggle_blank(self):
        en = "normal" if self.blank_rows_var.get() else "disabled"
        self.blank_rows_spin.config(state=en)

    def on_report_select(self, event):
        report_type = self.report_type_var.get()
        if report_type == "Operadores":
            try:
                con = get_connection(); cur = con.cursor()
                cur.execute("SELECT DISTINCT nombre_empresa FROM empresas ORDER BY nombre_empresa;")
                empresas = [r[0] for r in cur.fetchall()]
                cur.close(); con.close()
            except Exception:
                empresas = []
            if empresas:
                self.emp_filter_cb.config(values=["Todas"] + empresas); self.emp_filter_var.set("Todas")
            else:
                self.emp_filter_var.set("Todas")
            self.filters_frame.grid()
        elif report_type == "Empresas":
            self.filters_frame.grid_remove()
        else:
            self.filters_frame.grid_remove()

        if report_type in ["Empresas","Operadores"]:
            self.period_combo.config(state="disabled"); self.date_frame.grid_remove()
        else:
            self.period_combo.config(state="readonly"); self.date_frame.grid(); self.on_period_select(None)

    def on_period_select(self, event):
        p = self.period_var.get()
        if p == "Diario":
            self.label_fecha1.config(text="Fecha:")
            self.label_fecha1.grid(row=0, column=0, padx=5, pady=5)
            self.cal_start.grid(row=0, column=1, padx=5, pady=5)
            self.label_fecha2.grid_remove(); self.cal_end.grid_remove()
        elif p == "Rango Personalizado":
            self.label_fecha1.config(text="Fecha Inicio:")
            self.label_fecha1.grid(row=0, column=0, padx=5, pady=5)
            self.cal_start.grid(row=0, column=1, padx=5, pady=5)
            self.label_fecha2.config(text="Fecha Fin:")
            self.label_fecha2.grid(row=1, column=0, padx=5, pady=5)
            self.cal_end.grid(row=1, column=1, padx=5, pady=5)
        else:
            self.label_fecha1.config(text="Fecha Ref:")
            self.label_fecha1.grid(row=0, column=0, padx=5, pady=5)
            self.cal_start.grid(row=0, column=1, padx=5, pady=5)
            self.label_fecha2.grid_remove(); self.cal_end.grid_remove()

    def log_message(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def run_report_generation(self):
        self.generate_button.config(state="disabled")
        self.log_message("Iniciando generación de reporte...")
        threading.Thread(target=self.generate_report_thread).start()

    def generate_report_thread(self):
        report_type = self.report_type_var.get()
        try:
            params = {}
            if report_type in ["Cargas","Descargas"]:
                period = self.period_var.get()
                fref = self.cal_start.get_date()
                if period == "Diario":
                    params['fecha_inicio'] = params['fecha_fin'] = fref
                elif period == "Semanal":
                    start = fref - timedelta(days=fref.weekday())
                    params['fecha_inicio'] = start; params['fecha_fin'] = start + timedelta(days=6)
                elif period == "Mensual":
                    start = fref.replace(day=1)
                    next_start = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                    params['fecha_inicio'] = start; params['fecha_fin'] = next_start - timedelta(days=1)
                elif period == "Rango Personalizado":
                    params['fecha_inicio'] = fref; params['fecha_fin'] = self.cal_end.get_date()
                    if params['fecha_inicio'] > params['fecha_fin']:
                        self.log_message("ERROR: La fecha de inicio no puede ser posterior a la de fin.")
                        self.generate_button.config(state="normal"); return

            report_functions = {
                "Cargas": (obtener_datos_cargas, "Reporte_Cargas_{}_{}.pdf", True),
                "Descargas": (obtener_datos_descargas, "Reporte_Descargas_{}_{}.pdf", True),
                "Empresas": (lambda **kw: obtener_datos_empresas(kw.get("search_text")), "Catalogo_Empresas.pdf", False),
                "Operadores": (lambda **kw: obtener_datos_operadores(kw.get("search_text"), kw.get("empresa_filtro")), "Catalogo_Operadores.pdf", True),
            }
            func, filename_template, is_horizontal = report_functions[report_type]

            if report_type == "Empresas":
                params['search_text'] = self.search_var.get().strip()
            elif report_type == "Operadores":
                params['search_text'] = self.search_var.get().strip()
                params['empresa_filtro'] = self.emp_filter_var.get()

            self.log_message(f"Obteniendo datos para reporte de {report_type}...")
            result = func(**params) if params else func()
            if not result:
                self.log_message("ERROR: No se pudo obtener estructura del reporte.")
                self.generate_button.config(state="normal"); return

            titulo, datos, anchos, pie_pagina = result

            want_blanks = self.blank_rows_var.get() and report_type in ["Cargas","Descargas"]
            blank_count = max(0, min(500, int(self.blank_rows_count_var.get()))) if want_blanks else 0

            if want_blanks:
                titulo = quitar_rango_fechas_titulo(titulo)
                datos = insertar_filas_en_blanco(datos, blank_count)
                col_count = len(datos[0])
                datos.append(["TOTALES:"] + [""] * (col_count - 1))
                self.log_message(f"Plantilla con {blank_count} filas en blanco numeradas.")
            else:
                if len(datos) <= 1:
                    self.log_message(f"ADVERTENCIA: No se encontraron datos para {report_type}.")
                    self.generate_button.config(state="normal"); return

            header_subtitle = "MINA SANTA FE" if report_type in ["Cargas","Descargas"] else None

            if want_blanks and report_type in ["Cargas","Descargas"]:
                nombre_archivo = f"Plantilla_{'Cargas' if report_type == 'Cargas' else 'Descargas'}.pdf"
            else:
                nombre_archivo = (filename_template.format(params['fecha_inicio'].strftime('%Y%m%d'),
                                                           params['fecha_fin'].strftime('%Y%m%d'))
                                  if report_type in ["Cargas","Descargas"] else filename_template)

            self.log_message(f"Creando PDF: {nombre_archivo}...")
            ok = generar_reporte_pdf(nombre_archivo, titulo, datos, anchos, pie_pagina,
                                     is_horizontal, header_subtitle=header_subtitle)
            if ok: self.log_message(f"ÉXITO: Reporte '{nombre_archivo}' generado.")
            else:  self.log_message("ERROR: Falló la creación del PDF.")
        except Exception as e:
            self.log_message(f"ERROR INESPERADO: {e}")
            traceback.print_exc()
        finally:
            self.generate_button.config(state="normal")

# -----------------------------
if __name__ == '__main__':
    root = tk.Tk()
    app = ReportApp(root)
    root.mainloop()
