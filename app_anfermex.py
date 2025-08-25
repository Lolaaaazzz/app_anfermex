# app_anfermex.py — ANFERMEX unificado (Operación + Reportes)
# - Login sin "pantallazo" blanco y centrado seguro
# - CRUD Cargas / Descargas / Empresas / Operadores
# - Autorrelleno en Descargas al indicar ID Carga
# - Modo Escáner (F9→G1, F10→G2) para tickets
# - Auto-suma M³ Desc. G1 + G2 -> M³ Total Desc. mientras tecleas
# - Pestaña "Reportes" integrada (ex-reportes.py)
#   * Descargas: operador SOLO nombre (sin teléfono)
#   * Tickets con fuente más pequeña (6 pt) para una sola línea
#   * Plantillas: plantilla_carga.pdf y plantilla_descarga.pdf

import tkinter as tk
from tkinter import ttk, messagebox
from tkcalendar import DateEntry
import mysql.connector
from mysql.connector import Error
from datetime import datetime, timedelta, date
import re, hashlib
import threading
import os
import traceback

# ====== Reportlab (PDF) ======
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfgen import canvas

# ========= Config BD =========
DB_CONFIG = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "ALdrinruiz01",
    "database": "sedena",
    "autocommit": False,
}
def get_conn(): return mysql.connector.connect(**DB_CONFIG)
def get_db_name(): return DB_CONFIG["database"]

# ========= Estilos =========
APP_BG = "#F0F0F0"; ACCENT = "#004A5A"; DANGER = "#B00020"
def apply_theme(root):
    s = ttk.Style(root); s.theme_use("clam")
    root.configure(bg=APP_BG)
    for k in ("TFrame","TLabel"): s.configure(k, background=APP_BG, font=("Helvetica",10))
    s.configure("Header.TLabel", background=APP_BG, foreground=ACCENT, font=("Helvetica",14,"bold"))
    s.configure("Subheader.TLabel", background=APP_BG, foreground="#333", font=("Helvetica",10))
    s.configure("TButton", padding=6, font=("Helvetica",10,"bold"))
    s.map("TButton", foreground=[("disabled","#888")])
    s.configure("Accent.TButton", foreground="white", background=ACCENT); s.map("Accent.TButton", background=[("active","#066379")])
    s.configure("Danger.TButton", foreground="white", background=DANGER); s.map("Danger.TButton", background=[("active","#d22b2b")])
    s.configure("Treeview", font=("Helvetica",10), rowheight=26); s.configure("Treeview.Heading", font=("Helvetica",10,"bold"), background="#E6E6E6")

# ========= Utiles =========
def run_async(func, *args, on_done=None, on_error=None):
    def worker():
        try:
            res = func(*args)
            if on_done: ventana.after(0, lambda: on_done(res))
        except Exception as e:
            if on_error: ventana.after(0, lambda: on_error(e))
    threading.Thread(target=worker, daemon=True).start()

def _parse_date(d):
    if isinstance(d, date): return d
    s = str(d)
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%Y/%m/%d"):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    return date.today()

def _fmt_time(t):
    if hasattr(t,"strftime"):
        try: return t.strftime("%H:%M")
        except: pass
    m = re.match(r"^\s*(\d{1,2}):(\d{2})", str(t))
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else "00:00"

def _set_entry(e, value):
    e.delete(0, tk.END)
    e.insert(0, value or "")

# ========= Login =========
def _check_password(plain, stored):
    if stored is None: return False
    s = str(stored)
    if s.startswith(("$2a$","$2b$","$2y$")):
        try:
            import bcrypt
            return bcrypt.checkpw(plain.encode("utf-8"), s.encode("utf-8"))
        except Exception:
            return False
    if re.fullmatch(r"[0-9a-fA-F]{64}", s):
        return hashlib.sha256(plain.encode("utf-8")).hexdigest().lower() == s.lower()
    return s == plain

def detectar_esquema_usuarios():
    db = get_db_name()
    with get_conn() as c, c.cursor() as cur:
        cur.execute("""SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
                       WHERE TABLE_SCHEMA=%s AND TABLE_NAME='usuarios'""",(db,))
        cols = [r[0].lower() for r in cur.fetchall()]
    if not cols: raise RuntimeError("No existe tabla 'usuarios'")
    def pick(cands):
        for x in cands:
            if x in cols: return x
        return None
    return {
        "id":   pick(["id_usuario","id","usuario_id"]),
        "user": pick(["usuario","nombre_usuario","username","correo","email"]),
        "pass": pick(["contrasena","password","clave","pass"]),
        "role": pick(["rol","role","perfil","tipo"]),
        "all": cols
    }

def verificar_credenciales(usuario, contrasena):
    esq = detectar_esquema_usuarios()
    if not esq["user"] or not esq["pass"]:
        raise RuntimeError(f"Tabla 'usuarios' sin columnas de usuario/contraseña. Cols: {', '.join(esq['all'])}")
    sel = []
    if esq["id"]: sel.append(esq["id"])
    sel += [esq["user"], esq["pass"]]
    if esq["role"]: sel.append(esq["role"])
    with get_conn() as c, c.cursor() as cur:
        cur.execute(f"SELECT {', '.join(sel)} FROM usuarios WHERE {esq['user']}=%s LIMIT 1", (usuario,))
        row = cur.fetchone()
        if not row: return None
    idx = 0
    info = {"id":None,"usuario":None,"hash":None,"rol":None}
    if esq["id"]: info["id"]=row[idx]; idx+=1
    info["usuario"]=row[idx]; idx+=1
    info["hash"]=row[idx]; idx+=1
    if esq["role"] and idx<len(row): info["rol"]=row[idx]
    return info if _check_password(contrasena, info["hash"]) else None

class LoginWindow(tk.Toplevel):
    def __init__(self, master, on_success):
        super().__init__(master); self.title("Acceso - ANFERMEX"); self.configure(bg=APP_BG); self.resizable(False,False)
        self.on_success = on_success; self.grab_set(); self.protocol("WM_DELETE_WINDOW", self._cancel)
        f = ttk.Frame(self, padding=14); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Acceso a ANFERMEX", style="Header.TLabel").grid(row=0,column=0,columnspan=2,sticky="w",pady=(0,8))
        ttk.Label(f,text="Usuario:").grid(row=1,column=0,sticky="e",padx=6,pady=4); self.u=tk.StringVar(); ttk.Entry(f,textvariable=self.u,width=28).grid(row=1,column=1,sticky="w",padx=6,pady=4)
        ttk.Label(f,text="Contraseña:").grid(row=2,column=0,sticky="e",padx=6,pady=4); self.p=tk.StringVar(); e=ttk.Entry(f,textvariable=self.p,show="•",width=28); e.grid(row=2,column=1,sticky="w",padx=6,pady=4)
        b=ttk.Frame(f); b.grid(row=3,column=0,columnspan=2,sticky="e",pady=(10,0))
        ttk.Button(b,text="Cancelar",command=self._cancel).pack(side="right",padx=(6,0))
        ttk.Button(b,text="Entrar",style="Accent.TButton",command=self._login).pack(side="right")
        self.bind("<Return>", lambda _: self._login())
        self.after(100, lambda: e.focus_set())
        # Centrar ventana
        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        sw, sh = self.master.winfo_screenwidth(), self.master.winfo_screenheight()
        x = max(0, (sw - w) // 2); y = max(0, (sh - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")
    def _cancel(self): self.grab_release(); self.master.destroy()
    def _login(self):
        u=self.u.get().strip(); p=self.p.get().strip()
        if not u or not p: messagebox.showwarning("Acceso","Completa usuario y contraseña.",parent=self); return
        try: info=verificar_credenciales(u,p)
        except Exception as e: messagebox.showerror("Acceso",f"Error verificando credenciales:\n{e}",parent=self); return
        if not info: messagebox.showerror("Acceso","Usuario o contraseña incorrectos.",parent=self); return
        self.grab_release(); self.destroy(); self.on_success(info)

# ========= CRUD Listado =========
class CrudListado(ttk.Frame):
    def __init__(self,parent,cols,heads,fetch_page_fn,on_edit_fn,on_delete_fn,page_size=25,col_widths=None):
        super().__init__(parent); self.fetch_page_fn=fetch_page_fn; self.on_edit_fn=on_edit_fn; self.on_delete_fn=on_delete_fn
        self.page=0; self.page_size=page_size
        top=ttk.Frame(self); top.pack(fill="x",pady=(0,6))
        ttk.Label(top,text="Listado",style="Header.TLabel").pack(side="left",padx=4)
        self.q=tk.StringVar(); ttk.Entry(top,textvariable=self.q,width=28).pack(side="left",padx=6)
        ttk.Button(top,text="Buscar",style="Accent.TButton",command=self.reload).pack(side="left")
        ttk.Button(top,text="Limpiar",command=lambda:(self.q.set(""),self.reload())).pack(side="left",padx=(6,0))
        ttk.Button(top,text="Refrescar",command=self.reload).pack(side="left",padx=6)
        ttk.Button(top,text="Seleccionar todo",command=self.select_all).pack(side="left",padx=(12,0))
        ttk.Button(top,text="Limpiar selección",command=self.clear_selection).pack(side="left",padx=6)
        self.tree=ttk.Treeview(self,columns=cols,show="headings",selectmode="extended")
        for i,(c,h) in enumerate(zip(cols,heads)):
            self.tree.heading(c,text=h); self.tree.column(c,anchor="center",width=(col_widths[i] if col_widths else 120),stretch=True)
        self.tree.pack(fill="both",expand=True,pady=6); self.tree.bind("<Double-1>", lambda _ : self._edit())
        bottom=ttk.Frame(self); bottom.pack(fill="x",pady=6)
        ttk.Button(bottom,text="Editar",style="Accent.TButton",command=self._edit).pack(side="left")
        ttk.Button(bottom,text="Borrar (uno)",style="Danger.TButton",command=self._delete_one).pack(side="left",padx=6)
        ttk.Button(bottom,text="Borrar seleccionados",style="Danger.TButton",command=self._delete_selected).pack(side="left")
        nav=ttk.Frame(self); nav.pack(fill="x")
        ttk.Button(nav,text="⟨ Anterior",command=self.prev_page).pack(side="left")
        ttk.Button(nav,text="Siguiente ⟩",command=self.next_page).pack(side="left",padx=6)
        self.info=ttk.Label(nav,text="Página 1"); self.info.pack(side="right")
        self.reload()
    def select_all(self): self.tree.selection_set(self.tree.get_children())
    def clear_selection(self): self.tree.selection_remove(self.tree.selection())
    def _selected(self): return [self.tree.item(i,"values") for i in self.tree.selection()]
    def _edit(self): rows=self._selected();  self.on_edit_fn(rows[0][0]) if rows else None
    def _delete_one(self):
        rows=self._selected()
        if not rows: return
        rid=rows[0][0]
        if messagebox.askyesno("Confirmar","¿Borrar el registro seleccionado?",parent=self): self.on_delete_fn(rid,on_ok=self.reload)
    def _delete_selected(self):
        rows=self._selected()
        if not rows: return
        ids=[r[0] for r in rows]
        if not messagebox.askyesno("Confirmar",f"¿Borrar {len(ids)} registros seleccionados?",parent=self): return
        done={"n":0}
        def _one_done(): done["n"]+=1;  self.reload() if done["n"]>=len(ids) else None
        for rid in ids: self.on_delete_fn(rid,on_ok=_one_done)
    def reload(self):
        q=self.q.get().strip(); page=self.page; size=self.page_size
        run_async(lambda: self.fetch_page_fn(query=q,limit=size,offset=page*size),
                  on_done=lambda rows: (self._fill(rows)),
                  on_error=lambda e: messagebox.showerror("Error",str(e),parent=self))
    def _fill(self,rows):
        for i in self.tree.get_children(): self.tree.delete(i)
        for r in rows: self.tree.insert("", "end", values=r)
        self.info.config(text=f"Página {self.page+1} · {len(rows)} filas")
    def next_page(self): self.page+=1; self.reload()
    def prev_page(self):
        if self.page>0: self.page-=1; self.reload()

# ========= Catálogos helpers =========
def load_empresas_nombres():
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT nombre_empresa FROM empresas ORDER BY nombre_empresa"); return [r[0] for r in cur.fetchall()]
def get_id_empresa_by_nombre(n):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT id_empresa FROM empresas WHERE nombre_empresa=%s",(n,)); r=cur.fetchone(); return r[0] if r else None

def load_operadores_opciones():
    """
    Regresa:
      opciones: lista de strings 'No. - Nombre | Tel'
      map_display_to_id: dict display -> numero_operador (int)
      map_id_to_row: dict id -> dict con campos (nombre, tel, placas...)
    """
    with get_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute("""SELECT numero_operador, nombre_operador, numero_telefono,
                              placas_tractocamion, placas_gondola1, placas_gondola2
                       FROM operadores ORDER BY nombre_operador""")
        rows=cur.fetchall()
    opciones=[]; d_disp_id={}; d_id_row={}
    for r in rows:
        disp=f"{r['numero_operador']} - {r['nombre_operador']} | {r.get('numero_telefono','') or ''}"
        opciones.append(disp); d_disp_id[disp]=int(r["numero_operador"]); d_id_row[int(r["numero_operador"])]=r
    return opciones, d_disp_id, d_id_row

# ========= CARGAS SQL =========
def listar_cargas_pagina(query="",limit=25,offset=0):
    sql = """
    SELECT c.id_carga,
           c.folio,
           DATE_FORMAT(c.fecha_carga,'%Y-%m-%d') AS fecha,
           TIME_FORMAT(c.hora_carga,'%H:%i') AS hora,
           e.nombre_empresa,
           COALESCE(o.nombre_operador, c.nombre_operador) AS operador,
           c.destino,
           c.total_m3_cargados
    FROM cargasdescargas c
    JOIN empresas e ON c.id_empresa=e.id_empresa
    LEFT JOIN operadores o ON o.numero_operador = c.id_operador
    WHERE (%s='' OR c.folio LIKE CONCAT('%',%s,'%') OR COALESCE(o.nombre_operador,c.nombre_operador) LIKE CONCAT('%',%s,'%') OR e.nombre_empresa LIKE CONCAT('%',%s,'%'))
    ORDER BY c.fecha_carga DESC, c.hora_carga DESC, c.id_carga DESC
    LIMIT %s OFFSET %s;
    """
    params=(query,query,query,query,limit,offset)
    with get_conn() as c, c.cursor() as cur:
        cur.execute(sql, params); return cur.fetchall()

def obtener_carga_por_id(id_carga):
    with get_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute("""
            SELECT c.*, e.nombre_empresa, COALESCE(o.nombre_operador,c.nombre_operador) AS operador_resuelto,
                   o.numero_telefono
            FROM cargasdescargas c
            JOIN empresas e ON c.id_empresa=e.id_empresa
            LEFT JOIN operadores o ON o.numero_operador=c.id_operador
            WHERE c.id_carga=%s
        """,(id_carga,))
        return cur.fetchone()

def insertar_carga(data):
    sql = """
    INSERT INTO cargasdescargas
    (folio, fecha_carga, hora_carga, id_empresa, id_operador, nombre_operador,
     placas_tractocamion, placas_gondola1, placas_gondola2, destino, total_m3_cargados)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s);
    """
    with get_conn() as c, c.cursor() as cur:
        cur.execute(sql, data); c.commit()

def actualizar_carga(id_carga, data):
    sql = """
    UPDATE cargasdescargas
    SET folio=%s, fecha_carga=%s, hora_carga=%s, id_empresa=%s,
        id_operador=%s, nombre_operador=%s,
        placas_tractocamion=%s, placas_gondola1=%s, placas_gondola2=%s,
        destino=%s, total_m3_cargados=%s
    WHERE id_carga=%s;
    """
    with get_conn() as c, c.cursor() as cur:
        cur.execute(sql, (*data, id_carga)); c.commit()

def eliminar_carga(id_carga, on_ok=None):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM descargas WHERE id_carga=%s",(id_carga,)); cnt=cur.fetchone()[0]
        if cnt>0: messagebox.showwarning("No permitido","La carga tiene descargas asociadas.",parent=ventana); return
    run_async(lambda: (_do_del_carga(id_carga)), on_done=lambda: (on_ok and on_ok()))
def _do_del_carga(id_carga):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM cargasdescargas WHERE id_carga=%s",(id_carga,)); c.commit()

# ========= DESCARGAS SQL =========
def listar_descargas_pagina(query="",limit=25,offset=0):
    sql = """
    SELECT d.id_descarga, c.folio, DATE_FORMAT(d.fecha_descarga,'%Y-%m-%d') AS fecha,
           e.nombre_empresa, d.nombre_operador_descarga, d.destino, d.m3_descargados
    FROM descargas d
    JOIN cargasdescargas c ON d.id_carga=c.id_carga
    JOIN empresas e ON d.id_empresa=e.id_empresa
    WHERE (%s='' OR c.folio LIKE CONCAT('%',%s,'%') OR d.nombre_operador_descarga LIKE CONCAT('%',%s,'%') OR e.nombre_empresa LIKE CONCAT('%',%s,'%'))
    ORDER BY d.fecha_descarga DESC, d.id_descarga DESC
    LIMIT %s OFFSET %s
    """
    params=(query,query,query,query,limit,offset)
    with get_conn() as c, c.cursor() as cur: cur.execute(sql, params); return cur.fetchall()

def obtener_descarga_por_id(id_descarga):
    with get_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute("""
          SELECT d.*, c.folio, e.nombre_empresa
          FROM descargas d
          JOIN cargasdescargas c ON d.id_carga=c.id_carga
          JOIN empresas e ON d.id_empresa=e.id_empresa
          WHERE d.id_descarga=%s
        """,(id_descarga,))
        return cur.fetchone()

def insertar_descarga(data):
    sql = """
    INSERT INTO descargas
    (id_carga,id_empresa,fecha_descarga,nombre_operador_descarga,placas_gondola1_descarga,placas_gondola2_descarga,
     m3_cargados,m3_descargados_g1,m3_descargados_g2,m3_descargados,
     codigo_barras_ticket_descarga,codigo_barras_ticket_descarga_1,destino)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    with get_conn() as c, c.cursor() as cur: cur.execute(sql, data); c.commit()

def actualizar_descarga(id_descarga, data):
    sql = """
    UPDATE descargas SET
      id_carga=%s, id_empresa=%s, fecha_descarga=%s, nombre_operador_descarga=%s,
      placas_gondola1_descarga=%s, placas_gondola2_descarga=%s,
      m3_cargados=%s, m3_descargados_g1=%s, m3_descargados_g2=%s, m3_descargados=%s,
      codigo_barras_ticket_descarga=%s, codigo_barras_ticket_descarga_1=%s, destino=%s
    WHERE id_descarga=%s
    """
    with get_conn() as c, c.cursor() as cur: cur.execute(sql, (*data, id_descarga)); c.commit()

def eliminar_descarga(id_descarga, on_ok=None):
    run_async(lambda: _do_del_desc(id_descarga), on_done=lambda:(on_ok and on_ok()))
def _do_del_desc(id_descarga):
    with get_conn() as c, c.cursor() as cur: cur.execute("DELETE FROM descargas WHERE id_descarga=%s",(id_descarga,)); c.commit()

# ========= EMPRESAS =========
def listar_empresas_pagina(query="",limit=25,offset=0):
    sql = """SELECT id_empresa,nombre_empresa,banco,numero_cuenta_bancaria,plazo_credito_dias
             FROM empresas
             WHERE (%s='' OR nombre_empresa LIKE CONCAT('%',%s,'%') OR banco LIKE CONCAT('%',%s,'%'))
             ORDER BY nombre_empresa LIMIT %s OFFSET %s"""
    params=(query,query,query,limit,offset)
    with get_conn() as c, c.cursor() as cur: cur.execute(sql, params); return cur.fetchall()

def obtener_empresa_por_id(id_empresa):
    with get_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute("SELECT * FROM empresas WHERE id_empresa=%s",(id_empresa,)); return cur.fetchone()

def insertar_empresa(data):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("INSERT INTO empresas (nombre_empresa,banco,numero_cuenta_bancaria,plazo_credito_dias) VALUES (%s,%s,%s,%s)", data); c.commit()

def actualizar_empresa(id_empresa, data):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("UPDATE empresas SET nombre_empresa=%s,banco=%s,numero_cuenta_bancaria=%s,plazo_credito_dias=%s WHERE id_empresa=%s", (*data,id_empresa)); c.commit()

def eliminar_empresa(id_empresa, on_ok=None):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM operadores WHERE id_empresa=%s",(id_empresa,)); op=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM cargasdescargas WHERE id_empresa=%s",(id_empresa,)); ca=cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM descargas WHERE id_empresa=%s",(id_empresa,)); de=cur.fetchone()[0]
        if op or ca or de: messagebox.showwarning("No permitido","Empresa en uso por otros registros.",parent=ventana); return
    run_async(lambda:_do_del_emp(id_empresa), on_done=lambda:(on_ok and on_ok()))
def _do_del_emp(id_empresa):
    with get_conn() as c, c.cursor() as cur: cur.execute("DELETE FROM empresas WHERE id_empresa=%s",(id_empresa,)); c.commit()

# ========= OPERADORES =========
def listar_operadores_pagina(query="",limit=25,offset=0):
    sql = """
    SELECT o.numero_operador, o.nombre_operador, o.numero_telefono, e.nombre_empresa,
           o.placas_tractocamion, o.placas_gondola1, o.placas_gondola2, o.capacidad_carga_m3
    FROM operadores o
    JOIN empresas e ON o.id_empresa=e.id_empresa
    WHERE (%s='' OR o.nombre_operador LIKE CONCAT('%',%s,'%') OR e.nombre_empresa LIKE CONCAT('%',%s,'%') OR o.numero_telefono LIKE CONCAT('%',%s,'%'))
    ORDER BY o.nombre_operador LIMIT %s OFFSET %s
    """
    params=(query,query,query,query,limit,offset)
    with get_conn() as c, c.cursor() as cur: cur.execute(sql, params); return cur.fetchall()

def obtener_operador_por_id(no_op):
    with get_conn() as c, c.cursor(dictionary=True) as cur:
        cur.execute("""SELECT o.*, e.nombre_empresa FROM operadores o
                       JOIN empresas e ON o.id_empresa=e.id_empresa
                       WHERE o.numero_operador=%s""",(no_op,)); return cur.fetchone()

def insertar_operador(data):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("""INSERT INTO operadores
                       (numero_operador,nombre_operador,numero_telefono,id_empresa,
                        placas_tractocamion,placas_gondola1,placas_gondola2,capacidad_carga_m3)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""", data); c.commit()

def actualizar_operador(no_op, data):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("""UPDATE operadores SET nombre_operador=%s,numero_telefono=%s,id_empresa=%s,
                       placas_tractocamion=%s,placas_gondola1=%s,placas_gondola2=%s,capacidad_carga_m3=%s
                       WHERE numero_operador=%s""", (*data, no_op)); c.commit()

def eliminar_operador(no_op, on_ok=None):
    with get_conn() as c, c.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM cargasdescargas WHERE id_operador=%s",(no_op,)); ca=cur.fetchone()[0]
        if ca>0: messagebox.showwarning("No permitido","Operador referenciado por cargas.",parent=ventana); return
    run_async(lambda:_do_del_op(no_op), on_done=lambda:(on_ok and on_ok()))
def _do_del_op(no_op):
    with get_conn() as c, c.cursor() as cur: cur.execute("DELETE FROM operadores WHERE numero_operador=%s",(no_op,)); c.commit()

# ========= Reportes: estilos y helpers PDF =========
LOGO_PATH = "ANFERMEX MINERIA.jpg"
_styles = getSampleStyleSheet()
WRAP_CELL_STYLE = ParagraphStyle("WrapCell", parent=_styles["BodyText"], fontName="Helvetica", fontSize=7, leading=9, alignment=0)
WRAP_HEADER_STYLE = ParagraphStyle("WrapHeader", parent=_styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=11, alignment=1)
# ↓↓↓ ajuste pedido: tickets a 6 pt para que vayan en una sola línea
TICKET_CELL_STYLE = ParagraphStyle("TicketCell", parent=_styles["BodyText"], fontName="Helvetica", fontSize=6, leading=7, alignment=1)

def envolver_encabezados(datos, columnas, reemplazos=None):
    if not datos: return datos
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
    if not datos: return datos
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
    if not anchos: return anchos
    page_width_in = 11.0 if es_horizontal else 8.5
    disponible = page_width_in*inch - (left + right)
    total = sum(anchos)
    if total <= 0: return anchos
    scale = disponible / total
    return [w*scale for w in anchos]

def insertar_filas_en_blanco(datos, n):
    n = max(0, min(500, int(n or 0)))
    if not datos: return datos
    cols = len(datos[0])
    out = [datos[0]]
    for i in range(1, n + 1):
        fila = [""] * cols
        fila[0] = str(i)
        out.append(fila)
    return out

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
        if self.header_subtitle:
            self.setFont("Helvetica-Bold", 11)
            self.setFillColor(colors.black)
            self.drawCentredString(page_width / 2.0, page_height - 1.75 * inch, self.header_subtitle)
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.grey)
        self.drawRightString(page_width - 0.75 * inch, 0.35 * inch, f"Página {self.page_num} de {total_pages}")
        self.drawString(0.75 * inch, 0.35 * inch, self.report_type_footer)
        self.restoreState()

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

        # ↓↓↓ ajuste pedido: fuente 6 pt en columnas de TICKETS (11 y 12, 0-based)
        style.append(('FONTSIZE', (11,1), (12,-1), 6))

        # Fila de totales
        for i, row in enumerate(datos_tabla):
            if not row: continue
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
                if hasattr(generar_reporte_pdf, "_total_span_end_col"):
                    span_end = generar_reporte_pdf._total_span_end_col
                else:
                    span_end = None
                if isinstance(span_end, int) and span_end >= 0:
                    style.append(('SPAN', (0, i), (span_end, i)))

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

# -------- Querys para Reportes --------
def rep_datos_cargas(fecha_inicio, fecha_fin, search_text=None):
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
    with get_conn() as con, con.cursor() as cur:
        cur.execute(sql, (fecha_inicio, fecha_fin))
        filas = cur.fetchall()
    datos = [encabezados]; no = 1
    for f in filas:
        (folio, fecha, hora, operador, tel, placa_tr, g1, g2, destino, m3) = f
        datos.append([
            str(no), str(folio or "-"),
            fecha.strftime("%d/%m/%Y") if fecha else "-",
            str(hora or "-"), str(operador or "-"), str(tel or "-"),
            str(placa_tr or "-"), str(g1 or "-"), str(g2 or "-"),
            str(destino or "-"), f"{float(m3 or 0):.2f}",
        ])
        total_m3 += float(m3 or 0); no += 1
    if filas: datos.append(["TOTALES:"] + [""]*9 + [f"{total_m3:,.2f}"])
    datos = envolver_encabezados(datos, list(range(len(encabezados))),
                                 reemplazos={6:"PLACAS<br/>TRACTO.",7:"GÓNDOLA<br/>1",8:"GÓNDOLA<br/>2",10:"M³<br/>CARGADOS"})
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

def rep_datos_descargas(fecha_inicio, fecha_fin, search_text=None):
    titulo = f"REPORTE DE DESCARGAS ({fecha_inicio.strftime('%d/%m/%Y')} - {fecha_fin.strftime('%d/%m/%Y')})"
    encabezados = [
        "No", "FOL.", "FECHA", "DESTINO",
        "OPERADOR",  # SOLO nombre
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
    with get_conn() as con, con.cursor() as cur:
        cur.execute(sql, (fecha_inicio, fecha_fin))
        filas = cur.fetchall()
    datos = [encabezados]; no = 1
    for fila in filas:
        (folio, fecha, destino, operador, g1, g2, m_carg, m_g1, m_g2, m_tot, t1, t2) = fila
        # ==== LIMPIEZA: SOLO NOMBRE (sin teléfono, sin "N - ") ====
        op = str(operador or "")
        op = re.split(r"\s*\|\s*", op)[0]           # corta a la izquierda del " | "
        op = re.sub(r"^\s*\d+\s*-\s*", "", op).strip()  # quita prefijo "N - "
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
            Paragraph(str(t1 or "-"), TICKET_CELL_STYLE),
            Paragraph(str(t2 or "-"), TICKET_CELL_STYLE),
        ])
        total_cargado += float(m_carg or 0); total_g1 += float(m_g1 or 0); total_g2 += float(m_g2 or 0); total_descargado_final += float(m_tot or 0)
        no += 1
    if filas:
        datos.append(["TOTALES:"] + [""]*6 + [
            f"{total_cargado:,.2f}", f"{total_g1:,.2f}", f"{total_g2:,.2f}", f"{total_descargado_final:,.2f}",
        ] + ["",""])
    datos = envolver_encabezados(
        datos, list(range(len(encabezados))),
        reemplazos={5:"PLACAS<br/>G1", 6:"PLACAS<br/>G2", 7:"M³ CARG.<br/>MINA.",
                    8:"M³ DESC.<br/>G1", 9:"M³ DESC.<br/>G2", 10:"M³ TOTAL<br/>DESC."}
    )
    datos = aplicar_wrap_en_columnas(datos, columnas_wrap={3,4})
    generar_reporte_pdf._alineaciones = [
        ('ALIGN', (0,0), (2,-1), 'CENTER'),
        ('ALIGN', (3,1), (4,-1), 'LEFT'),
        ('ALIGN', (5,1), (12,-1), 'CENTER'),
    ]
    generar_reporte_pdf._total_span_end_col = 6
    return titulo, datos, anchos, "REPORTE DETALLADO DE DESCARGAS"

def rep_datos_empresas(search_text=None):
    titulo = "CATÁLOGO DE EMPRESAS"
    encabezados = ["No.","ID","NOMBRE DE LA EMPRESA","PLAZO CRÉDITO (DÍAS)","BANCO","NÚMERO DE CUENTA"]
    anchos = [0.45*inch, 0.7*inch, 2.4*inch, 1.2*inch, 1.2*inch, 2.0*inch]
    sql = """
        SELECT id_empresa, nombre_empresa, plazo_credito_dias, banco, numero_cuenta_bancaria
        FROM empresas
        ORDER BY nombre_empresa;
    """
    with get_conn() as con, con.cursor() as cur:
        cur.execute(sql)
        filas = cur.fetchall()
    datos = [encabezados]; no = 1
    for f in filas:
        datos.append([
            str(no), str(f[0] or "-"), str(f[1] or "-"), str(f[2] or "-"),
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

def rep_datos_operadores(search_text=None, empresa_filtro=None):
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
    with get_conn() as con, con.cursor() as cur:
        cur.execute(sql, tuple(params))
        filas = cur.fetchall()
    datos = [encabezados]; no = 1
    for f in filas:
        (num_op, nombre, tel, empresa, tracto, g1, g2, cap) = f
        datos.append([
            str(no), str(num_op or "-"), str(nombre or "-"), str(tel or "-"),
            str(empresa or "-"), str(tracto or "-"), str(g1 or "-"), str(g2 or "-"),
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

# ========= UI helpers =========
def form_4col(parent):
    f=ttk.Frame(parent); [f.columnconfigure(i, weight=(1 if i in (1,3) else 0)) for i in range(4)]; return f
def row_2x(f,r,l1,w1,l2,w2):
    ttk.Label(f,text=l1).grid(row=r,column=0,sticky="e",padx=6,pady=4); w1.grid(row=r,column=1,sticky="ew",padx=6,pady=4)
    ttk.Label(f,text=l2).grid(row=r,column=2,sticky="e",padx=6,pady=4); w2.grid(row=r,column=3,sticky="ew",padx=6,pady=4)

# ========= App =========
class AppAnfermex(ttk.Frame):
    def __init__(self,root,usuario_info):
        super().__init__(root); self.pack(fill="both",expand=True)
        self.usuario_info=usuario_info
        self.empresas_cache=[]; self.oper_opciones=[]; self.oper_disp_to_id={}; self.oper_id_to_row={}
        self.build_ui()

    def refresh_empresas_cache(self):
        try: self.empresas_cache=load_empresas_nombres()
        except Error as e: messagebox.showerror("BD", f"Empresas: {e}", parent=self)

    def refresh_operadores_cache(self):
        try:
            self.oper_opciones, self.oper_disp_to_id, self.oper_id_to_row = load_operadores_opciones()
            if hasattr(self,"operador_c"): self.operador_c.config(values=self.oper_opciones)
            if hasattr(self,"operador_d"): self.operador_d.config(values=self.oper_opciones)
        except Error as e:
            messagebox.showerror("BD", f"Operadores: {e}", parent=self)

    def build_ui(self):
        head=ttk.Frame(self); head.pack(fill="x",padx=10,pady=(10,0))
        ttk.Label(head,text="ANFERMEX - Gestor de Cargas / Descargas / Catálogos",style="Header.TLabel").pack(side="left")
        usr=self.usuario_info.get("usuario") or ""; rol=self.usuario_info.get("rol") or ""
        ttk.Label(head,text=f"Usuario: {usr}" + (f"  ·  Rol: {rol}" if rol else ""),style="Subheader.TLabel").pack(side="right")

        self.nb=ttk.Notebook(self); self.nb.pack(fill="both",expand=True,padx=10,pady=10)
        self.tab_cargas=ttk.Frame(self.nb,padding=10); self.nb.add(self.tab_cargas,text="Cargas")
        self.tab_descargas=ttk.Frame(self.nb,padding=10); self.nb.add(self.tab_descargas,text="Descargas")
        self.tab_empresas=ttk.Frame(self.nb,padding=10); self.nb.add(self.tab_empresas,text="Empresas")
        self.tab_operadores=ttk.Frame(self.nb,padding=10); self.nb.add(self.tab_operadores,text="Operadores")
        self.tab_reportes=ttk.Frame(self.nb,padding=10); self.nb.add(self.tab_reportes,text="Reportes")

        self.build_cargas(self.tab_cargas)
        self.build_descargas(self.tab_descargas)
        self.build_empresas(self.tab_empresas)
        self.build_operadores(self.tab_operadores)
        self.build_reportes(self.tab_reportes)

    # --- CARGAS ---
    def build_cargas(self,parent):
        self.refresh_empresas_cache(); self.refresh_operadores_cache()
        sub=ttk.Notebook(parent); sub.pack(fill="both",expand=True)
        tab_reg=ttk.Frame(sub,padding=10); sub.add(tab_reg,text="Registrar")
        tab_list=ttk.Frame(sub,padding=10); sub.add(tab_list,text="Listado")

        form=form_4col(tab_reg); form.pack(fill="x",pady=4)
        self.ed_carga_id=None

        self.folio_c=ttk.Entry(form); self.empresa_c=ttk.Combobox(form,values=self.empresas_cache,state="readonly")
        row_2x(form,0,"Folio:",self.folio_c,"Empresa:",self.empresa_c)

        self.fecha_c=DateEntry(form,date_pattern="y-mm-dd",width=12); self.hora_c=ttk.Entry(form)
        row_2x(form,1,"Fecha:",self.fecha_c,"Hora (HH:MM):",self.hora_c)

        oper_box=ttk.Frame(form)
        self.operador_c=ttk.Combobox(oper_box, values=self.oper_opciones, state="readonly", width=46)
        self.operador_c.pack(side="left",fill="x",expand=True)
        ttk.Button(oper_box, text="↻", width=3, command=self.refresh_operadores_cache).pack(side="left", padx=(6,0))
        self.operador_c.bind("<<ComboboxSelected>>", self._on_operador_selected)
        self.operador_c.bind("<FocusOut>", self._on_operador_selected)

        self.destino_c=ttk.Entry(form)
        row_2x(form,2,"Operador:",oper_box,"Destino:",self.destino_c)

        self.pt_c=ttk.Entry(form); self.g1_c=ttk.Entry(form)
        row_2x(form,3,"Placas Tracto:",self.pt_c,"Góndola 1:",self.g1_c)

        self.g2_c=ttk.Entry(form); self.m3_c=ttk.Entry(form)
        row_2x(form,4,"Góndola 2:",self.g2_c,"M³ Cargados:",self.m3_c)

        btns=ttk.Frame(tab_reg); btns.pack(fill="x",pady=(10,0))
        self.btn_guardar_carga=ttk.Button(btns,text="Guardar Carga",style="Accent.TButton",command=self.on_save_carga); self.btn_guardar_carga.pack(side="left")
        ttk.Button(btns,text="Nueva",command=self.reset_form_carga).pack(side="left",padx=6)

        cols=("id","folio","fecha","hora","empresa","operador","destino","m3")
        heads=("ID","Folio","Fecha","Hora","Empresa","Operador","Destino","M³")
        widths=(60,90,100,70,180,180,150,80)
        self.list_cargas=CrudListado(tab_list,cols,heads,listar_cargas_pagina,self.on_edit_carga,eliminar_carga,page_size=25,col_widths=widths)
        self.list_cargas.pack(fill="both",expand=True)

    def _on_operador_selected(self, _evt=None):
        disp=self.operador_c.get().strip(); op_id=self.oper_disp_to_id.get(disp)
        if not op_id: return
        op=self.oper_id_to_row.get(op_id,{})
        _set_entry(self.pt_c, op.get("placas_tractocamion","") or "")
        _set_entry(self.g1_c, op.get("placas_gondola1","") or "")
        _set_entry(self.g2_c, op.get("placas_gondola2","") or "")

    def reset_form_carga(self):
        self.ed_carga_id=None; self.btn_guardar_carga.config(text="Guardar Carga")
        for w in (self.folio_c,self.hora_c,self.destino_c,self.pt_c,self.g1_c,self.g2_c,self.m3_c): w.delete(0,tk.END)
        self.empresa_c.set(self.empresas_cache[0] if self.empresas_cache else "")
        self.operador_c.set("")
        try: self.fecha_c.set_date(date.today())
        except: pass

    def on_edit_carga(self,id_carga):
        row=obtener_carga_por_id(id_carga)
        if not row: messagebox.showerror("Cargas","No se encontró la carga.",parent=self); return
        self.nb.select(self.tab_cargas); self.ed_carga_id=id_carga; self.btn_guardar_carga.config(text="Guardar Cambios")
        _set_entry(self.folio_c, row.get("folio",""))
        self.fecha_c.set_date(_parse_date(row.get("fecha_carga"))); _set_entry(self.hora_c, _fmt_time(row.get("hora_carga")))
        self.empresa_c.set(row.get("nombre_empresa","")); _set_entry(self.destino_c, row.get("destino",""))
        _set_entry(self.pt_c, row.get("placas_tractocamion",""))
        _set_entry(self.g1_c, row.get("placas_gondola1",""))
        _set_entry(self.g2_c, row.get("placas_gondola2",""))
        _set_entry(self.m3_c, f"{float(row.get('total_m3_cargados') or 0):.2f}")
        op_id=row.get("id_operador")
        if op_id and int(op_id) in self.oper_id_to_row:
            op=self.oper_id_to_row[int(op_id)]
            disp=f"{op_id} - {op.get('nombre_operador','')} | {op.get('numero_telefono','') or ''}"
            if disp not in self.oper_opciones: self.refresh_operadores_cache()
            self.operador_c.set(disp)
        else:
            self.operador_c.set("")

    def on_save_carga(self):
        folio=self.folio_c.get().strip()
        if not folio: messagebox.showwarning("Cargas","Folio es obligatorio.",parent=self); return
        id_emp=get_id_empresa_by_nombre(self.empresa_c.get().strip())
        if not id_emp: messagebox.showwarning("Cargas","Selecciona una empresa válida.",parent=self); return
        fecha=self.fecha_c.get_date(); hora=self.hora_c.get().strip() or "00:00"
        destino=self.destino_c.get().strip()
        pt,g1,g2=self.pt_c.get().strip(), self.g1_c.get().strip(), self.g2_c.get().strip()
        try: m3=float(self.m3_c.get().strip() or "0")
        except: messagebox.showwarning("Cargas","M³ cargados inválido.",parent=self); return
        disp=self.operador_c.get().strip(); id_op=self.oper_disp_to_id.get(disp)
        if not id_op:
            messagebox.showwarning("Cargas","Selecciona un operador del listado.",parent=self); return
        op_row=self.oper_id_to_row.get(id_op,{})
        nombre_op=op_row.get("nombre_operador","")
        data=(folio, fecha, hora, id_emp, id_op, nombre_op, pt, g1, g2, destino, m3)
        try:
            if self.ed_carga_id:
                actualizar_carga(self.ed_carga_id, data); messagebox.showinfo("Cargas","Carga actualizada.",parent=self)
            else:
                insertar_carga(data); messagebox.showinfo("Cargas","Carga registrada.",parent=self)
            self.reset_form_carga(); self.list_cargas.reload()
        except Error as e:
            messagebox.showerror("BD", f"Error al guardar carga: {e}", parent=self)

    # --- DESCARGAS ---
    def build_descargas(self,parent):
        self.refresh_empresas_cache(); self.refresh_operadores_cache()
        sub=ttk.Notebook(parent); sub.pack(fill="both",expand=True)
        tab_reg=ttk.Frame(sub,padding=10); sub.add(tab_reg,text="Registrar")
        tab_list=ttk.Frame(sub,padding=10); sub.add(tab_list,text="Listado")

        form=form_4col(tab_reg); form.pack(fill="x",pady=4)
        self.ed_descarga_id=None

        self.idc_d=ttk.Entry(form); self.emp_d=ttk.Combobox(form,values=self.empresas_cache,state="readonly")
        row_2x(form,0,"ID Carga:",self.idc_d,"Empresa:",self.emp_d)

        self.fecha_d=DateEntry(form,date_pattern="y-mm-dd",width=12)

        oper_box_d=ttk.Frame(form)
        self.operador_d=ttk.Combobox(oper_box_d, values=self.oper_opciones, state="normal", width=46)
        self.operador_d.pack(side="left",fill="x",expand=True)
        ttk.Button(oper_box_d, text="↻", width=3, command=self.refresh_operadores_cache).pack(side="left", padx=(6,0))
        self.operador_d.bind("<<ComboboxSelected>>", self._on_operador_desc_selected)
        self.operador_d.bind("<FocusOut>", self._on_operador_desc_selected)

        row_2x(form,1,"Fecha:",self.fecha_d,"Operador:",oper_box_d)

        self.dest_d=ttk.Entry(form); self.g1_d=ttk.Entry(form)
        row_2x(form,2,"Destino:",self.dest_d,"Placas G1:",self.g1_d)

        self.g2_d=ttk.Entry(form); self.mc_d=ttk.Entry(form)
        row_2x(form,3,"Placas G2:",self.g2_d,"M³ Carg. Mina:",self.mc_d)

        self.mg1_d=ttk.Entry(form); self.mg2_d=ttk.Entry(form)
        row_2x(form,4,"M³ Desc. G1:",self.mg1_d,"M³ Desc. G2:",self.mg2_d)

        self.mt_d=ttk.Entry(form); self.t1_d=ttk.Entry(form)
        row_2x(form,5,"M³ Total Desc.:",self.mt_d,"Ticket G1:",self.t1_d)

        self.t2_d=ttk.Entry(form); row_2x(form,6,"Ticket G2:",self.t2_d,"",ttk.Frame(form))

        # Auto-suma al teclear/salir
        for w in (self.mg1_d, self.mg2_d):
            w.bind("<KeyRelease>", self._recalc_total_desc)
            w.bind("<FocusOut>",  self._recalc_total_desc)

        # --- MODO ESCÁNER ---
        scan_bar = ttk.Frame(tab_reg); scan_bar.pack(fill="x", pady=(6,0))
        ttk.Label(scan_bar, text="Modo escáner (tickets):").pack(side="left")
        ttk.Button(scan_bar, text="Escanear → G1 (F9)",  command=lambda: self._open_scanner(target="g1")).pack(side="left", padx=6)
        ttk.Button(scan_bar, text="Escanear → G2 (F10)", command=lambda: self._open_scanner(target="g2")).pack(side="left")
        self.nb.bind_all("<F9>",  lambda e: self._open_scanner(target="g1"))
        self.nb.bind_all("<F10>", lambda e: self._open_scanner(target="g2"))

        # Autorrelleno al indicar ID Carga
        self.idc_d.bind("<Return>", self._preload_descarga_from_carga)
        self.idc_d.bind("<FocusOut>", self._preload_descarga_from_carga)

        btns=ttk.Frame(tab_reg); btns.pack(fill="x",pady=(10,0))
        self.btn_guardar_desc=ttk.Button(btns,text="Guardar Descarga",style="Accent.TButton",command=self.on_save_descarga); self.btn_guardar_desc.pack(side="left")
        ttk.Button(btns,text="Nueva",command=self.reset_form_descarga).pack(side="left",padx=6)

        cols=("id","folio","fecha","empresa","operador","destino","m3")
        heads=("ID","Folio","Fecha","Empresa","Operador","Destino","M³ Total Desc.")
        widths=(60,90,100,180,150,150,120)
        self.list_desc=CrudListado(tab_list,cols,heads,listar_descargas_pagina,self.on_edit_descarga,eliminar_descarga,page_size=25,col_widths=widths)
        self.list_desc.pack(fill="both",expand=True)

    # --- Auto-suma: M³ Desc. G1 + G2 -> M³ Total Desc. ---
    def _recalc_total_desc(self, *_):
        def fnum(x):
            try: return float((x or "").strip().replace(",", ""))
            except: return 0.0
        total = fnum(self.mg1_d.get()) + fnum(self.mg2_d.get())
        _set_entry(self.mt_d, f"{total:.2f}")

    # --- Modo escáner ---
    def _open_scanner(self, target="g1"):
        win = tk.Toplevel(self)
        win.title(f"Escanear → {'Ticket G1' if target=='g1' else 'Ticket G2'}")
        apply_theme(win)
        ttk.Label(win, text=f"Apunta el lector y presiona Enter (Destino: {'G1' if target=='g1' else 'G2'})", style="Header.TLabel").pack(padx=12, pady=(12,6), anchor="w")
        var = tk.StringVar()
        e = ttk.Entry(win, textvariable=var, width=48, font=("Consolas", 14))
        e.pack(padx=12, pady=(0,12), fill="x")
        e.focus_set()
        def accept(_=None):
            code = re.sub(r"\D+", "", var.get().strip())
            if target == "g1": _set_entry(self.t1_d, code)
            else: _set_entry(self.t2_d, code)
            win.destroy()
        ttk.Button(win, text="Aceptar", style="Accent.TButton", command=accept).pack(pady=(0,12))
        win.bind("<Return>", accept)

    # --- Autorrelleno en Descargas desde ID de Carga ---
    def _preload_descarga_from_carga(self, _evt=None):
        raw = self.idc_d.get().strip()
        if not raw: return
        try: id_carga = int(raw)
        except:
            return
        row = obtener_carga_por_id(id_carga)
        if not row:
            return
        nom_emp = row.get("nombre_empresa","")
        if nom_emp in self.empresas_cache:
            self.emp_d.set(nom_emp)
        elif self.empresas_cache:
            self.emp_d.set(self.empresas_cache[0])

        id_op = row.get("id_operador")
        disp = None
        if id_op and int(id_op) in self.oper_id_to_row:
            op=self.oper_id_to_row[int(id_op)]
            disp=f"{id_op} - {op.get('nombre_operador','')} | {op.get('numero_telefono','') or ''}"
        self.operador_d.set(disp or row.get("operador_resuelto",""))

        _set_entry(self.g1_d, row.get("placas_gondola1","") or "")
        _set_entry(self.g2_d, row.get("placas_gondola2","") or "")
        _set_entry(self.dest_d, row.get("destino","") or "")
        _set_entry(self.mc_d, f"{float(row.get('total_m3_cargados') or 0):.2f}")

    def _on_operador_desc_selected(self, _evt=None):
        disp=self.operador_d.get().strip(); op_id=self.oper_disp_to_id.get(disp)
        if not op_id: return
        op=self.oper_id_to_row.get(op_id,{})
        _set_entry(self.g1_d, op.get("placas_gondola1","") or "")
        _set_entry(self.g2_d, op.get("placas_gondola2","") or "")

    def reset_form_descarga(self):
        self.ed_descarga_id=None; self.btn_guardar_desc.config(text="Guardar Descarga")
        for w in (self.idc_d,self.dest_d,self.g1_d,self.g2_d,self.mc_d,self.mg1_d,self.mg2_d,self.mt_d,self.t1_d,self.t2_d): w.delete(0,tk.END)
        self.operador_d.set("")
        self.emp_d.set(self.empresas_cache[0] if self.empresas_cache else "")
        try: self.fecha_d.set_date(date.today())
        except: pass

    def on_edit_descarga(self,id_descarga):
        r=obtener_descarga_por_id(id_descarga)
        if not r: messagebox.showerror("Descargas","No se encontró la descarga.",parent=self); return
        self.nb.select(self.tab_descargas); self.ed_descarga_id=id_descarga; self.btn_guardar_desc.config(text="Guardar Cambios")
        _set_entry(self.idc_d, str(r["id_carga"]))
        self.emp_d.set(r.get("nombre_empresa","")); self.fecha_d.set_date(_parse_date(r.get("fecha_descarga")))
        self.operador_d.set(r.get("nombre_operador_descarga",""))
        _set_entry(self.dest_d, r.get("destino",""))
        _set_entry(self.g1_d, r.get("placas_gondola1_descarga",""))
        _set_entry(self.g2_d, r.get("placas_gondola2_descarga",""))
        def f(x):
            try: return f"{float(x or 0):.2f}"
            except: return "0.00"
        _set_entry(self.mc_d, f(r.get("m3_cargados")))
        _set_entry(self.mg1_d, f(r.get("m3_descargados_g1")))
        _set_entry(self.mg2_d, f(r.get("m3_descargados_g2")))
        _set_entry(self.mt_d, f(r.get("m3_descargados")))
        _set_entry(self.t1_d, r.get("codigo_barras_ticket_descarga",""))
        _set_entry(self.t2_d, r.get("codigo_barras_ticket_descarga_1",""))

    def on_save_descarga(self):
        try: id_carga=int(self.idc_d.get().strip())
        except: messagebox.showwarning("Descargas","ID Carga inválido.",parent=self); return
        id_emp=get_id_empresa_by_nombre(self.emp_d.get().strip())
        if not id_emp: messagebox.showwarning("Descargas","Selecciona una empresa válida.",parent=self); return
        fecha=self.fecha_d.get_date()
        op_text=self.operador_d.get().strip()
        if not op_text: messagebox.showwarning("Descargas","Indica el operador.",parent=self); return
        dest=self.dest_d.get().strip()
        g1=self.g1_d.get().strip(); g2=self.g2_d.get().strip()
        def fnum(x):
            try: return float((x or "").strip() or "0")
            except: return 0.0
        mc,mg1,mg2,mt = fnum(self.mc_d.get()), fnum(self.mg1_d.get()), fnum(self.mg2_d.get()), fnum(self.mt_d.get())
        t1,t2=self.t1_d.get().strip(), self.t2_d.get().strip()
        data=(id_carga,id_emp,fecha,op_text,g1,g2,mc,mg1,mg2,mt,t1,t2,dest)
        try:
            if self.ed_descarga_id:
                actualizar_descarga(self.ed_descarga_id, data); messagebox.showinfo("Descargas","Descarga actualizada.",parent=self)
            else:
                insertar_descarga(data); messagebox.showinfo("Descargas","Descarga registrada.",parent=self)
            self.reset_form_descarga(); self.list_desc.reload()
        except Error as e:
            messagebox.showerror("BD", f"Error al guardar descarga: {e}", parent=self)

    # --- EMPRESAS ---
    def build_empresas(self,parent):
        sub=ttk.Notebook(parent); sub.pack(fill="both",expand=True)
        tab_reg=ttk.Frame(sub,padding=10); sub.add(tab_reg,text="Registrar")
        tab_list=ttk.Frame(sub,padding=10); sub.add(tab_list,text="Listado")
        form=form_4col(tab_reg); form.pack(fill="x",pady=4)
        self.ed_empresa_id=None
        self.nom_e=ttk.Entry(form); self.banco_e=ttk.Entry(form)
        row_2x(form,0,"Nombre:",self.nom_e,"Banco:",self.banco_e)
        self.cuenta_e=ttk.Entry(form); self.plazo_e=ttk.Entry(form)
        row_2x(form,1,"Cuenta:",self.cuenta_e,"Plazo crédito (días):",self.plazo_e)
        btns=ttk.Frame(tab_reg); btns.pack(fill="x",pady=(10,0))
        self.btn_guardar_emp=ttk.Button(btns,text="Guardar Empresa",style="Accent.TButton",command=self.on_save_empresa); self.btn_guardar_emp.pack(side="left")
        ttk.Button(btns,text="Nueva",command=self.reset_form_empresa).pack(side="left",padx=6)
        cols=("id","nombre","banco","cuenta","plazo"); heads=("ID","Nombre","Banco","Cuenta","Plazo (días)")
        widths=(60,200,160,180,110)
        self.list_emp=CrudListado(tab_list,cols,heads,listar_empresas_pagina,self.on_edit_empresa,eliminar_empresa,page_size=25,col_widths=widths)
        self.list_emp.pack(fill="both",expand=True)
    def reset_form_empresa(self):
        self.ed_empresa_id=None; self.btn_guardar_emp.config(text="Guardar Empresa")
        for w in (self.nom_e,self.banco_e,self.cuenta_e,self.plazo_e): w.delete(0,tk.END)
    def on_edit_empresa(self,id_empresa):
        r=obtener_empresa_por_id(id_empresa)
        if not r: messagebox.showerror("Empresas","No se encontró la empresa.",parent=self); return
        self.nb.select(self.tab_empresas); self.ed_empresa_id=id_empresa; self.btn_guardar_emp.config(text="Guardar Cambios")
        _set_entry(self.nom_e, r.get("nombre_empresa",""))
        _set_entry(self.banco_e, r.get("banco",""))
        _set_entry(self.cuenta_e, r.get("numero_cuenta_bancaria",""))
        _set_entry(self.plazo_e, str(r.get("plazo_credito_dias") or ""))
    def on_save_empresa(self):
        nombre=self.nom_e.get().strip()
        if not nombre: messagebox.showwarning("Empresas","Nombre obligatorio.",parent=self); return
        banco=self.banco_e.get().strip(); cuenta=self.cuenta_e.get().strip()
        try: plazo=int(self.plazo_e.get().strip() or "0")
        except: messagebox.showwarning("Empresas","Plazo inválido.",parent=self); return
        data=(nombre,banco,cuenta,plazo)
        try:
            if self.ed_empresa_id: actualizar_empresa(self.ed_empresa_id,data); messagebox.showinfo("Empresas","Empresa actualizada.",parent=self)
            else: insertar_empresa(data); messagebox.showinfo("Empresas","Empresa registrada.",parent=self)
            self.reset_form_empresa(); self.list_emp.reload()
            self.refresh_empresas_cache()
            self.empresa_c.config(values=self.empresas_cache); self.emp_d.config(values=self.empresas_cache); self.emp_o.config(values=self.empresas_cache)
        except Error as e: messagebox.showerror("BD", f"Error al guardar empresa: {e}", parent=self)

    # --- OPERADORES ---
    def build_operadores(self,parent):
        self.refresh_empresas_cache()
        sub=ttk.Notebook(parent); sub.pack(fill="both",expand=True)
        tab_reg=ttk.Frame(sub,padding=10); sub.add(tab_reg,text="Registrar")
        tab_list=ttk.Frame(sub,padding=10); sub.add(tab_list,text="Listado")
        form=form_4col(tab_reg); form.pack(fill="x",pady=4)
        self.ed_operador_id=None
        self.no_o=ttk.Entry(form); self.emp_o=ttk.Combobox(form,values=self.empresas_cache,state="readonly")
        row_2x(form,0,"No. Operador:",self.no_o,"Empresa:",self.emp_o)
        self.nom_o=ttk.Entry(form); self.tel_o=ttk.Entry(form)
        row_2x(form,1,"Nombre:",self.nom_o,"Teléfono:",self.tel_o)
        self.pt_o=ttk.Entry(form); self.g1_o=ttk.Entry(form)
        row_2x(form,2,"Placas Tracto:",self.pt_o,"Góndola 1:",self.g1_o)
        self.g2_o=ttk.Entry(form); self.cap_o=ttk.Entry(form)
        row_2x(form,3,"Góndola 2:",self.g2_o,"Capacidad (M³):",self.cap_o)
        btns=ttk.Frame(tab_reg); btns.pack(fill="x",pady=(10,0))
        self.btn_guardar_op=ttk.Button(btns,text="Guardar Operador",style="Accent.TButton",command=self.on_save_operador); self.btn_guardar_op.pack(side="left")
        ttk.Button(btns,text="Nuevo",command=self.reset_form_operador).pack(side="left",padx=6)
        cols=("id","nombre","telefono","empresa","tracto","g1","g2","cap")
        heads=("No.","Nombre","Teléfono","Empresa","Placas Tracto","Góndola 1","Góndola 2","Capacidad (M³)")
        widths=(70,180,120,180,130,110,110,130)
        self.list_op=CrudListado(tab_list,cols,heads,listar_operadores_pagina,self.on_edit_operador,eliminar_operador,page_size=25,col_widths=widths)
        self.list_op.pack(fill="both",expand=True)
    def reset_form_operador(self):
        self.ed_operador_id=None; self.btn_guardar_op.config(text="Guardar Operador")
        for w in (self.no_o,self.nom_o,self.tel_o,self.pt_o,self.g1_o,self.g2_o,self.cap_o): w.delete(0,tk.END)
        self.emp_o.set(self.empresas_cache[0] if self.empresas_cache else "")
    def on_edit_operador(self,no_op):
        r=obtener_operador_por_id(no_op)
        if not r: messagebox.showerror("Operadores","No se encontró el operador.",parent=self); return
        self.nb.select(self.tab_operadores); self.ed_operador_id=no_op; self.btn_guardar_op.config(text="Guardar Cambios")
        _set_entry(self.no_o, str(r.get("numero_operador","")))
        _set_entry(self.nom_o, r.get("nombre_operador",""))
        _set_entry(self.tel_o, r.get("numero_telefono",""))
        self.emp_o.set(r.get("nombre_empresa",""))
        _set_entry(self.pt_o, r.get("placas_tractocamion",""))
        _set_entry(self.g1_o, r.get("placas_gondola1",""))
        _set_entry(self.g2_o, r.get("placas_gondola2",""))
        _set_entry(self.cap_o, f"{float(r.get('capacidad_carga_m3') or 0):.2f}")
    def on_save_operador(self):
        try: num=int(self.no_o.get().strip())
        except: messagebox.showwarning("Operadores","No. Operador inválido.",parent=self); return
        nombre=self.nom_o.get().strip()
        if not nombre: messagebox.showwarning("Operadores","Nombre obligatorio.",parent=self); return
        tel=self.tel_o.get().strip(); id_emp=get_id_empresa_by_nombre(self.emp_o.get().strip())
        if not id_emp: messagebox.showwarning("Operadores","Selecciona una empresa válida.",parent=self); return
        pt,g1,g2=self.pt_o.get().strip(), self.g1_o.get().strip(), self.g2_o.get().strip()
        try: cap=float(self.cap_o.get().strip() or "0")
        except: messagebox.showwarning("Operadores","Capacidad inválida.",parent=self); return
        try:
            if self.ed_operador_id:
                actualizar_operador(self.ed_operador_id, (nombre,tel,id_emp,pt,g1,g2,cap)); messagebox.showinfo("Operadores","Operador actualizado.",parent=self)
            else:
                insertar_operador((num,nombre,tel,id_emp,pt,g1,g2,cap)); messagebox.showinfo("Operadores","Operador registrado.",parent=self)
            self.reset_form_operador(); self.list_op.reload(); self.refresh_operadores_cache()
        except Error as e: messagebox.showerror("BD", f"Error al guardar operador: {e}", parent=self)

    # --- REPORTES ---
    def build_reportes(self, parent):
        wrap = ttk.Frame(parent); wrap.pack(fill="both", expand=True)
        top = ttk.Frame(wrap); top.pack(fill="x", pady=(0,8))

        ttk.Label(top, text="Panel de Reportes", style="Header.TLabel").pack(side="left")

        body = ttk.Frame(wrap); body.pack(fill="x", pady=(6,0))

        ttk.Label(body, text="Tipo de Reporte:").grid(row=0, column=0, sticky="e", padx=6, pady=4)
        self.rep_tipo = tk.StringVar(value="Descargas")
        self.rep_tipo_cb = ttk.Combobox(body, textvariable=self.rep_tipo,
                                        values=["Cargas","Descargas","Empresas","Operadores"], state="readonly", width=18)
        self.rep_tipo_cb.grid(row=0, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(body, text="Periodo:").grid(row=0, column=2, sticky="e", padx=6, pady=4)
        self.rep_periodo = tk.StringVar(value="Diario")
        self.rep_per_cb = ttk.Combobox(body, textvariable=self.rep_periodo,
                                       values=["Diario","Semanal","Mensual","Rango Personalizado"], state="readonly", width=20)
        self.rep_per_cb.grid(row=0, column=3, sticky="w", padx=6, pady=4)
        self.rep_per_cb.bind("<<ComboboxSelected>>", self._rep_on_period)

        self.rep_f1_lbl = ttk.Label(body, text="Fecha:")
        self.rep_f1_lbl.grid(row=1, column=0, sticky="e", padx=6, pady=4)
        self.rep_f1 = DateEntry(body, date_pattern="y-mm-dd", width=12); self.rep_f1.grid(row=1, column=1, sticky="w", padx=6, pady=4)
        self.rep_f2_lbl = ttk.Label(body, text="")
        self.rep_f2 = DateEntry(body, date_pattern="y-mm-dd", width=12)

        self.rep_blank = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text="Generar plantilla (filas en blanco)", variable=self.rep_blank, command=self._rep_on_blank)\
            .grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=(8,0))
        ttk.Label(body, text="Cantidad:").grid(row=2, column=2, sticky="e", padx=6, pady=(8,0))
        self.rep_blank_n = tk.Spinbox(body, from_=0, to=500, width=6, state="disabled", justify="center")
        self.rep_blank_n.grid(row=2, column=3, sticky="w", padx=6, pady=(8,0))
        self.rep_blank_n.delete(0, tk.END); self.rep_blank_n.insert(0, "20")

        ttk.Button(wrap, text="Generar PDF", style="Accent.TButton", command=self._gen_reporte).pack(anchor="w")

        self._rep_on_period(None)

    def _rep_on_blank(self):
        self.rep_blank_n.config(state=("normal" if self.rep_blank.get() else "disabled"))

    def _rep_on_period(self, _):
        p = self.rep_periodo.get()
        if p == "Diario":
            self.rep_f1_lbl.config(text="Fecha:")
            self.rep_f2_lbl.grid_forget(); self.rep_f2.grid_forget()
            self.rep_f1.grid(row=1,column=1, sticky="w", padx=6, pady=4)
        elif p == "Rango Personalizado":
            self.rep_f1_lbl.config(text="Fecha Inicio:")
            self.rep_f2_lbl.config(text="Fecha Fin:"); self.rep_f2_lbl.grid(row=1, column=2, sticky="e", padx=6, pady=4)
            self.rep_f1.grid(row=1,column=1, sticky="w", padx=6, pady=4)
            self.rep_f2.grid(row=1,column=3, sticky="w", padx=6, pady=4)
        else:
            self.rep_f1_lbl.config(text="Fecha Ref:")
            self.rep_f2_lbl.grid_forget(); self.rep_f2.grid_forget()
            self.rep_f1.grid(row=1,column=1, sticky="w", padx=6, pady=4)

    def _gen_reporte(self):
        tipo = self.rep_tipo.get()
        p = self.rep_periodo.get()
        fref = self.rep_f1.get_date()
        if tipo in ("Cargas", "Descargas"):
            if p == "Diario":
                fi = ff = fref
            elif p == "Semanal":
                start = fref - timedelta(days=fref.weekday())
                fi, ff = start, start + timedelta(days=6)
            elif p == "Mensual":
                start = fref.replace(day=1)
                next_start = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
                fi, ff = start, next_start - timedelta(days=1)
            else:
                fi, ff = self.rep_f1.get_date(), self.rep_f2.get_date()
                if fi > ff:
                    messagebox.showwarning("Reportes", "La fecha de inicio no puede ser posterior a la de fin.", parent=self)
                    return
        blank = self.rep_blank.get()
        n_blank = max(0, min(500, int(self.rep_blank_n.get() if self.rep_blank_n.get() else 0)))

        if tipo == "Cargas":
            titulo, datos, anchos, pie = rep_datos_cargas(fi, ff)
        elif tipo == "Descargas":
            titulo, datos, anchos, pie = rep_datos_descargas(fi, ff)
        elif tipo == "Empresas":
            titulo, datos, anchos, pie = rep_datos_empresas()
        else:
            titulo, datos, anchos, pie = rep_datos_operadores()

        if blank and tipo in ("Cargas","Descargas"):
            titulo = "PLANTILLA DE " + ("CARGAS" if tipo=="Cargas" else "DESCARGAS")
            datos = insertar_filas_en_blanco(datos, n_blank)
            col_count = len(datos[0])
            datos.append(["TOTALES:"] + [""] * (col_count - 1))
            nombre_pdf = "plantilla_carga.pdf" if tipo=="Cargas" else "plantilla_descarga.pdf"
        else:
            if tipo in ("Cargas","Descargas"):
                nombre_pdf = f"Reporte_{tipo}_{fi.strftime('%Y%m%d')}_{ff.strftime('%Y%m%d')}.pdf"
            else:
                nombre_pdf = f"Catalogo_{tipo}.pdf"

        header_subtitle = "MINA SANTA FE" if tipo in ("Cargas","Descargas") else None
        ok = generar_reporte_pdf(nombre_pdf, titulo, datos, anchos, pie, True, header_subtitle=header_subtitle)
        if ok:
            messagebox.showinfo("Reportes", f"PDF generado:\n{os.path.abspath(nombre_pdf)}", parent=self)
        else:
            messagebox.showerror("Reportes", "Error al generar el PDF.", parent=self)

# ========= Main =========
def _start_app(info):
    ventana.deiconify()
    AppAnfermex(ventana, info)

if __name__ == "__main__":
    ventana=tk.Tk()
    ventana.withdraw()  # Oculta la raíz hasta que pase el login
    ventana.title("ANFERMEX - Operación"); ventana.geometry("1200x720")
    apply_theme(ventana)
    LoginWindow(ventana, on_success=_start_app)
    ventana.mainloop()
