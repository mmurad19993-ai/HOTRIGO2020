import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import os, io, re, json, base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ===== CONFIG - مرة وحدة =====
SHEET_ID_FALLBACK = "1WyJlLeChys_qh_qCxjFUZBq-FlhgHbhBaizMcg21Zqc"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVE_FOLDER = "Hotrigo Backup"
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Price Night","Hotel Total","Check-in","Nights","Check-out","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]
DB = os.path.join(BASE_DIR, "hotrigo.db")

def to_f(v):
    try: return float(str(v).strip().replace(',', '').replace('$','') or 0)
    except: return 0.0
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", str(name))[:50]
def smart_match(input_val, valid_list, valid_upper=None):
    if not input_val or not input_val.strip(): return "", True
    if not valid_list: return input_val.strip(), True
    inp = input_val.strip().upper()
    if valid_upper is None: valid_upper = [str(x).upper() for x in valid_list]
    if inp in valid_upper: return valid_list[valid_upper.index(inp)], True
    for i, u in enumerate(valid_upper):
        if inp in u or u in inp: return valid_list[i], True
    return input_val.strip(), False
def clear_filters():
    for k in ["search", "entry_date_filter", "exit_date_filter", "search_mode"]:
        if k in st.session_state:
            try: del st.session_state[k]
            except: pass
    st.session_state.table_version = st.session_state.get("table_version",0)+1
if "table_version" not in st.session_state:
    st.session_state.table_version = 0

def get_drive_service():
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        if "\\n" in creds_info.get("private_key",""):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/drive"])
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets.get("FOLDER_ID")
        return service, folder_id
    except: return None, None
def get_folder_id(service, name):
    try:
        q=f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
        res=service.files().list(q=q, fields="files(id)").execute()
        files=res.get('files',[])
        if files: return files[0]['id']
        folder=service.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder'},fields='id').execute()
        return folder.get('id')
    except: return None

# ===== FIXED - Python 3.11 - يحل 404 =====
def get_gspread_sheet(worksheet_name=None):
    try:
        sid = st.secrets.get("SHEET_ID", SHEET_ID_FALLBACK)
        sid = str(sid).strip().strip('"').strip("'").strip()
        if "/d/" in sid: sid = sid.split("/d/")[1].split("/")[0]
        creds_info = dict(st.secrets["gcp_service_account"])
        if "\\n" in creds_info.get("private_key",""):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        ss = None
        try:
            ss = client.open_by_key(sid)
        except Exception as first_err:
            for f in client.list_spreadsheet_files():
                if "HOTRIGO" in f['name'].upper():
                    ss = client.open_by_key(f['id'])
                    break
            if not ss: raise first_err
        if worksheet_name:
            try: return ss.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                return ss.add_worksheet(title=worksheet_name, rows=2000, cols=30)
        return ss.sheet1
    except Exception as e:
        st.error(f"❌ Sheet Error: {e}")
        import traceback; st.code(traceback.format_exc())
        return None
def get_spreadsheet():
    try:
        ws = get_gspread_sheet()
        return ws.spreadsheet if ws else None
    except: return None
def add_payment(tab_name, name_value, amount_val, note_val, note1_val):
    try:
        ws = get_gspread_sheet(tab_name)
        if not ws: return False
        ws.append_row([datetime.now().strftime("%Y-%m-%d"),str(name_value),float(amount_val),str(note_val),str(note1_val),st.session_state.get("username","admin"),datetime.now().strftime("%H%M%S")], value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        st.error(f"Sheet Error {tab_name}: {e}"); return False
def upload_drive(local_path):
    def get_or_create_subfolder(service, parent_id, sub_name):
        try:
            q=f"name='{sub_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            res=service.files().list(q=q, fields="files(id)").execute()
            fls=res.get('files',[])
            if fls: return fls[0]['id']
            folder=service.files().create(body={'name':sub_name,'mimeType':'application/vnd.google-apps.folder','parents':[parent_id]}, fields='id').execute()
            return folder.get('id')
        except: return parent_id
    try:
        service, folder_id_secret = get_drive_service()
        if service and os.path.exists(local_path):
            folder_id = folder_id_secret or get_folder_id(service, DRIVE_FOLDER)
            if folder_id:
                fname=os.path.basename(local_path)
                up=fname.upper()
                if up.startswith("BOOK-"): folder_id = get_or_create_subfolder(service, folder_id, "Invoices")
                elif up.startswith("VOUCHER_"): folder_id = get_or_create_subfolder(service, folder_id, "Vouchers")
                elif up.startswith("STATEMENT_"): folder_id = get_or_create_subfolder(service, folder_id, "Statements")
                q=f"name='{fname}' and '{folder_id}' in parents and trashed=false"
                ex=service.files().list(q=q, fields="files(id)").execute()
                for f in ex.get('files',[]):
                    try: service.files().delete(fileId=f['id']).execute()
                    except: pass
                media=MediaFileUpload(local_path, resumable=True)
                service.files().create(body={'name':fname,'parents':[folder_id]}, media_body=media).execute()
                return True
    except Exception as e: print(f"Upload Error: {e}")
    return False

# ===== LOAD LISTS =====
def load_lists():
    try:
        conn = sqlite3.connect(DB)
        conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT PRIMARY KEY)")
        agents = [r[0] for r in conn.execute("SELECT name FROM agents ORDER BY name").fetchall()]
        hotels = [r[0] for r in conn.execute("SELECT name FROM hotels ORDER BY name").fetchall()]
        airlines = [r[0] for r in conn.execute("SELECT name FROM airlines ORDER BY name").fetchall()]
        transports = [r[0] for r in conn.execute("SELECT name FROM transport_companies ORDER BY name").fetchall()]
        conn.close()
        return agents, hotels, airlines, transports
    except: return [], [], [], []
agents_for_js, hotels_for_js, airlines_for_js, transport_for_js = load_lists()
agents_upper = [a.upper() for a in agents_for_js]
hotels_upper = [h.upper() for h in hotels_for_js]
airlines_upper = [a.upper() for a in airlines_for_js]
transport_upper = [t.upper() for t in transport_for_js]

LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
def get_logo_b64():
    if os.path.exists(LOGO_PATH):
        try:
            with open(LOGO_PATH, "rb") as f: return base64.b64encode(f.read()).decode()
        except: return None
    return None
def init():
    try:
        sheet = get_gspread_sheet()
        if sheet:
            first_row = sheet.row_values(1)
            if not first_row or len(first_row) == 0:
                sheet.update('A1', [SHEET_HEADER], value_input_option='USER_ENTERED')
    except: pass
    return True
init()

# ===== DIALOGS & UI - نفس يلي عندك =====
@st.dialog("Edit Booking")
def edit_dialog(row):
    sheet = get_gspread_sheet()
    if not sheet:
        st.error("Sheet not connected"); return
    try: row_idx = int(row)
    except: row_idx = 2
    all_vals = sheet.get_all_values()
    header = all_vals[0]
    d_row = all_vals[row_idx-1]
    d = {h: d_row[i] if i < len(d_row) else "" for i, h in enumerate(header)}
    def gv(k, default=""): return str(d.get(k, default) or "")
    st.info(f"Editing #{row_idx} - {gv('company')}")
    c1,c2=st.columns(2)
    with c1: e_sale=st.text_input("Sale Date", value=gv("sale_date"), key="dlg_sale")
    with c2: e_entry=st.text_input("Entry Date", value=gv("entry_date"), key="dlg_en")
    c3,c4=st.columns(2)
    with c3: e_exit=st.text_input("Exit Date", value=gv("exit_date"), key="dlg_ex")
    with c4: e_comp=st.text_input("Agent *", value=gv("company"), key="dlg_comp")
    e_pas=st.text_area("Passengers", value=gv("passengers"), height=130, key="dlg_pas")
    e_room=st.text_input("Room Type", value=gv("room_type"), key="dlg_room")
    e_hotel=st.text_input("Hotel *", value=gv("hotel"), key="dlg_hotel")
    e_emp=st.text_input("Employee", value=gv("emp"), key="dlg_emp")
    e_pn=st.text_input("Price per Night $", value=gv("price_per_night"), key="dlg_pn")
    e_sell=st.text_input("Selling Price $ *", value=gv("sell"), key="dlg_sell")
    if st.button("Save", type="primary", use_container_width=True):
        new_row=[str(row_idx),e_comp,e_pas,"",e_hotel,"",e_room,e_pn,"",e_entry,"",e_exit,"","","",e_sell,"",e_sale,"","", "", e_emp, "", "", "", "", ""]
        try:
            sheet.update(f"A{row_idx}:Z{row_idx}", [new_row], value_input_option="USER_ENTERED")
            st.success("✅ تم التحديث"); st.session_state.table_version+=1; st.rerun()
        except Exception as e: st.error(f"Error: {e}")

st.markdown("## ✈️ hotrigo | Sheets Sync ✅")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])
with t1:
    l,r=st.columns([1, 4.8])
    with l:
        sd=st.date_input("Sale Date", datetime.now(), key="sd")
        emp=st.text_input("Sales Employee *", key="emp")
        comp=st.text_input("Agent *", key="comp")
        pas=st.text_area("Passengers *", key="pas")
        hotel=st.text_input("Hotel *", key="hotel")
        ed=st.date_input("Check-in", datetime.now()+timedelta(days=1), key="ed")
        nights=st.text_input("Nights", value="", key="nights")
        try: nights_val=int(nights) if nights else 0
        except: nights_val=0
        xd=ed+timedelta(days=nights_val)
        st.caption(f"Check-out: {xd}")
        pn_s=st.text_input("Price per Night $", key="pn")
        sell_s=st.text_input("Selling Price $ *", key="sell")
        pn=to_f(pn_s); sell=to_f(sell_s)
        if st.button("SAVE SALE", type="primary", use_container_width=True, key="save_btn"):
            if not comp.strip() or not hotel.strip() or not emp.strip() or not pas.strip(): st.error("Fill required")
            else:
                st.session_state["pending"]={"company":comp,"passengers":pas,"hotel":hotel,"entry_date":str(ed),"exit_date":str(xd),"sell":sell,"sale_date":str(sd),"emp":emp,"price_night":pn,"nights":nights_val}
        if st.session_state.get("pending"):
            d=st.session_state["pending"]
            st.warning(f"✅ {d['company']} - {d['passengers'][:20]} | Sell ${d['sell']:.2f}")
            if st.button("YES", type="primary", use_container_width=True):
                try:
                    ws=get_gspread_sheet()
                    if ws:
                        ws.append_row([str(datetime.now().timestamp()),d['company'],d['passengers'],"",d['hotel'],"","","","","",str(d['entry_date']),"",str(d['exit_date']),"","",str(d['sell']),"","","",str(d['sale_date']),"","","",d['emp'],"","","","",""], value_input_option='USER_ENTERED')
                        st.success("✅ تم الرفع للشيت")
                    st.session_state.pending=None; st.rerun()
                except Exception as e: st.error(f"{e}")
            if st.button("NO", use_container_width=True): st.session_state.pending=None; st.rerun()
    with r:
        search_val=st.text_input("Search", placeholder="Search...", key="search")
        sheet=get_gspread_sheet()
        if not sheet: st.error("Sheet not connected - فعّل Sheets API & Drive API وشارك الشيت Editor"); st.stop()
        all_vals=sheet.get_all_values()
        if len(all_vals)<2: df_raw=pd.DataFrame()
        else:
            header=all_vals[0]; rows=all_vals[1:]
            df_raw=pd.DataFrame(rows, columns=header[:len(rows[0])] if rows else header)
            df_raw["_sheet_row"]=[i+2 for i in range(len(df_raw))]
            if search_val.strip():
                s=search_val.lower()
                df_raw=df_raw[df_raw.apply(lambda row: s in str(row.values).lower(), axis=1)]
        st.dataframe(df_raw.drop(columns=["_sheet_row"], errors='ignore') if not df_raw.empty else df_raw, use_container_width=True, height=650)
        st.markdown(f"**Total: {len(df_raw)}**")
        if st.button("Edit", key="edit_small"):
            st.info("حدد سطر من الجدول وبعدين Edit - استخدم Select")

with t2:
    st.markdown("### 💰 Payments")
    try:
        ws=get_gspread_sheet("Payments")
        df=pd.DataFrame(ws.get_all_records()) if ws else pd.DataFrame()
        st.dataframe(df, use_container_width=True)
    except Exception as e: st.error(f"{e}")

with t3:
    conn=sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
    conn.commit(); conn.close()
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### 👥 Agents")
        with st.form(key="f_agents", clear_on_submit=True):
            na=st.text_input("", placeholder="Agent name...")
            if st.form_submit_button("Add Agent", use_container_width=True) and na.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO agents (name) VALUES (?)", (na.strip().upper(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB); dfa=pd.read_sql("SELECT name as Agents FROM agents ORDER BY name", conn); conn.close()
        st.dataframe(dfa, use_container_width=True, height=250, hide_index=True)
    with c2:
        st.markdown("#### 🏨 Hotels")
        with st.form(key="f_hotels", clear_on_submit=True):
            nh=st.text_input("", placeholder="Hotel name...")
            if st.form_submit_button("Add Hotel", use_container_width=True) and nh.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO hotels (name) VALUES (?)", (nh.strip(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB); dfh=pd.read_sql("SELECT name as Hotels FROM hotels ORDER BY name", conn); conn.close()
        st.dataframe(dfh, use_container_width=True, height=250, hide_index=True)
import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit.components.v1 as components
import os, io, re, json, base64
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SHEET_ID_FALLBACK = "1WyJlLeChys_qh_qCxjFUZBq-FlhgHbhBaizMcg21Zqc"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DRIVE_FOLDER = "Hotrigo Backup"
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Price Night","Hotel Total","Check-in","Nights","Check-out","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]
DB = os.path.join(BASE_DIR, "hotrigo.db")

def to_f(v):
    try: return float(str(v).strip().replace(',', '').replace('$','') or 0)
    except: return 0.0
def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", str(name))[:50]
def smart_match(input_val, valid_list, valid_upper=None):
    if not input_val or not input_val.strip(): return "", True
    if not valid_list: return input_val.strip(), True
    inp = input_val.strip().upper()
    if valid_upper is None: valid_upper = [str(x).upper() for x in valid_list]
    if inp in valid_upper: return valid_list[valid_upper.index(inp)], True
    for i, u in enumerate(valid_upper):
        if inp in u or u in inp: return valid_list[i], True
    return input_val.strip(), False
def clear_filters():
    for k in ["search", "entry_date_filter", "exit_date_filter", "search_mode"]:
        if k in st.session_state:
            try: del st.session_state[k]
            except: pass
    st.session_state.table_version = st.session_state.get("table_version",0)+1
if "table_version" not in st.session_state:
    st.session_state.table_version = 0

def get_drive_service():
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        if "\\n" in creds_info.get("private_key",""):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/drive"])
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets.get("FOLDER_ID")
        return service, folder_id
    except: return None, None
def get_folder_id(service, name):
    try:
        q=f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
        res=service.files().list(q=q, fields="files(id)").execute()
        files=res.get('files',[])
        if files: return files[0]['id']
        folder=service.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder'},fields='id').execute()
        return folder.get('id')
    except: return None

# ===== FIXED: يحل 404 و Python 3.11 =====
def get_gspread_sheet(worksheet_name=None):
    try:
        sid = st.secrets.get("SHEET_ID", SHEET_ID_FALLBACK)
        sid = str(sid).strip().strip('"').strip("'").strip()
        if "/d/" in sid: sid = sid.split("/d/")[1].split("/")[0]
        creds_info = dict(st.secrets["gcp_service_account"])
        if "\\n" in creds_info.get("private_key",""):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        ss = None
        try:
            ss = client.open_by_key(sid)
        except Exception as first_err:
            for f in client.list_spreadsheet_files():
                if "HOTRIGO" in f['name'].upper():
                    ss = client.open_by_key(f['id'])
                    break
            if not ss: raise first_err
        if worksheet_name:
            try: return ss.worksheet(worksheet_name)
            except gspread.exceptions.WorksheetNotFound:
                return ss.add_worksheet(title=worksheet_name, rows=2000, cols=30)
        return ss.sheet1
    except Exception as e:
        st.error(f"❌ Sheet Error: {e}")
        import traceback; st.code(traceback.format_exc())
        return None
def get_spreadsheet():
    try:
        ws = get_gspread_sheet()
        return ws.spreadsheet if ws else None
    except: return None
def add_payment(tab_name, name_value, amount_val, note_val, note1_val):
    try:
        ws = get_gspread_sheet(tab_name)
        if not ws: return False
        ws.append_row([datetime.now().strftime("%Y-%m-%d"),str(name_value),float(amount_val),str(note_val),str(note1_val),st.session_state.get("username","admin"),datetime.now().strftime("%H%M%S")], value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        st.error(f"Sheet Error {tab_name}: {e}"); return False
def upload_drive(local_path):
    def get_or_create_subfolder(service, parent_id, sub_name):
        try:
            q=f"name='{sub_name}' and '{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
            res=service.files().list(q=q, fields="files(id)").execute()
            fls=res.get('files',[])
            if fls: return fls[0]['id']
            folder=service.files().create(body={'name':sub_name,'mimeType':'application/vnd.google-apps.folder','parents':[parent_id]}, fields='id').execute()
            return folder.get('id')
        except: return parent_id
    try:
        service, folder_id_secret = get_drive_service()
        if service and os.path.exists(local_path):
            folder_id = folder_id_secret or get_folder_id(service, DRIVE_FOLDER)
            if folder_id:
                fname=os.path.basename(local_path)
                up=fname.upper()
                if up.startswith("BOOK-"): folder_id = get_or_create_subfolder(service, folder_id, "Invoices")
                elif up.startswith("VOUCHER_"): folder_id = get_or_create_subfolder(service, folder_id, "Vouchers")
                elif up.startswith("STATEMENT_"): folder_id = get_or_create_subfolder(service, folder_id, "Statements")
                q=f"name='{fname}' and '{folder_id}' in parents and trashed=false"
                ex=service.files().list(q=q, fields="files(id)").execute()
                for f in ex.get('files',[]):
                    try: service.files().delete(fileId=f['id']).execute()
                    except: pass
                media=MediaFileUpload(local_path, resumable=True)
                service.files().create(body={'name':fname,'parents':[folder_id]}, media_body=media).execute()
                return True
    except: pass
    return False
def load_lists():
    try:
        conn = sqlite3.connect(DB)
        conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT PRIMARY KEY)")
        agents = [r[0] for r in conn.execute("SELECT name FROM agents ORDER BY name").fetchall()]
        hotels = [r[0] for r in conn.execute("SELECT name FROM hotels ORDER BY name").fetchall()]
        airlines = [r[0] for r in conn.execute("SELECT name FROM airlines ORDER BY name").fetchall()]
        transports = [r[0] for r in conn.execute("SELECT name FROM transport_companies ORDER BY name").fetchall()]
        conn.close()
        return agents, hotels, airlines, transports
    except: return [], [], [], []
agents_for_js, hotels_for_js, airlines_for_js, transport_for_js = load_lists()
agents_upper = [a.upper() for a in agents_for_js]
hotels_upper = [h.upper() for h in hotels_for_js]
airlines_upper = [a.upper() for a in airlines_for_js]
transport_upper = [t.upper() for t in transport_for_js]

def generate_invoice_pdf(data, save_path=None):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from io import BytesIO
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, f"HOTRIGO INVOICE {data.get('voucher','')}")
        c.setFont("Helvetica", 12)
        c.drawString(50, 770, f"Agent: {data.get('company','')}")
        c.drawString(50, 750, f"Hotel: {data.get('hotel','')}")
        c.drawString(50, 730, f"Sell: ${data.get('sell','')}")
        c.showPage(); c.save()
        pdf=buffer.getvalue()
        if save_path:
            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f: f.write(pdf)
            except: pass
        return pdf
    except: return b""
def generate_voucher_pdf(data, save_path=None):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from io import BytesIO
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(50, 800, f"VOUCHER {data.get('booking_no','')}")
        c.setFont("Helvetica", 12)
        c.drawString(50, 770, f"Hotel: {data.get('hotel','')}")
        c.showPage(); c.save()
        pdf=buffer.getvalue()
        if save_path:
            try:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, "wb") as f: f.write(pdf)
            except: pass
        return pdf
    except: return b""
LOGO_PATH = os.path.join(BASE_DIR, "logo.png")
def get_logo_b64():
    if os.path.exists(LOGO_PATH):
        try:
            with open(LOGO_PATH, "rb") as f: return base64.b64encode(f.read()).decode()
        except: return None
    return None
def init():
    try:
        sheet = get_gspread_sheet()
        if sheet:
            first_row = sheet.row_values(1)
            if not first_row or len(first_row) == 0:
                sheet.update('A1', [SHEET_HEADER], value_input_option='USER_ENTERED')
    except: pass
    return True
init()

@st.dialog("Edit Booking")
def edit_dialog(row):
    sheet = get_gspread_sheet()
    if not sheet:
        st.error("Sheet not connected"); return
    try: row_idx = int(row)
    except: row_idx = 2
    if row_idx < 2: row_idx = 2
    try:
        all_vals = sheet.get_all_values()
        header = all_vals[0]
        if row_idx > len(all_vals): st.error("Booking not found"); return
        d_row = all_vals[row_idx-1]
        d = {h: d_row[i] if i < len(d_row) else "" for i, h in enumerate(header)}
    except Exception as e:
        st.error(f"Booking not found: {e}"); return
    def gv(k, default=""): return str(d.get(k, default) or "")
    st.info(f"Editing booking #{row_idx} - {gv('company')}")
    c1,c2=st.columns(2)
    with c1: e_sale=st.text_input("Sale Date", value=gv("sale_date"), key="dlg_sale")
    with c2: e_entry=st.text_input("Entry Date", value=gv("entry_date"), key="dlg_en")
    c3,c4=st.columns(2)
    with c3: e_exit=st.text_input("Exit Date", value=gv("exit_date"), key="dlg_ex")
    with c4: e_comp=st.text_input("Agent *", value=gv("company"), key="dlg_comp")
    e_pas=st.text_area("Passengers", value=gv("passengers"), height=130, key="dlg_pas")
    c5,c6=st.columns(2)
    with c5: e_room=st.text_input("Room Type", value=gv("room_type"), key="dlg_room")
    with c6:
        cur_rc=gv("room_count")
        init_val="" if cur_rc in ["0","1","None",""] else cur_rc
        if cur_rc=="1": init_val=""
        e_rc_text=st.text_input("Number of Rooms", value=init_val, key="dlg_rc")
    c7,c8=st.columns(2)
    with c7:
        current_hotel=gv("hotel")
        if hotels_for_js: 
            idx=hotels_for_js.index(current_hotel) if current_hotel in hotels_for_js else 0
            e_hotel=st.selectbox("Hotel *", hotels_for_js, index=idx, key="dlg_hotel")
        else: e_hotel=st.text_input("Hotel *", value=current_hotel, key="dlg_hotel")
    with c8: e_emp=st.text_input("Employee", value=gv("emp"), key="dlg_emp")
    c_price,c_flight=st.columns(2)
    with c_price: e_pn=st.text_input("Price per Night $", value=gv("price_per_night"), key="dlg_pn")
    with c_flight: e_fl=st.text_input("Flight $", value=gv("flight_cost"), key="dlg_fl")
    c_trans,c_sell=st.columns(2)
    with c_trans: e_tr=st.text_input("Transport $", value=gv("transport_cost"), key="dlg_tr")
    with c_sell: e_sell=st.text_input("Selling Price $ *", value=gv("sell"), key="dlg_sell")
    e_notes=st.text_input("Note", value=gv("notes"), key="dlg_notes")
    c_air,c_vno=st.columns(2)
    with c_air: e_air=st.text_input("Airline", value=gv("airline"), key="dlg_air")
    with c_vno: e_vno=st.text_input("Voucher No", value=gv("voucher_no"), key="dlg_vno")
    e_trans_co=st.text_input("Transport Company", value=gv("transport_company"), key="dlg_transco")
    if st.button("Save", type="primary", use_container_width=True):
        try: e_rc_final=0 if e_rc_text.strip()=="" else int(float(e_rc_text.strip()))
        except: e_rc_final=0
        new_data={'sale_date':e_sale,'company':e_comp,'passengers':e_pas,'room_type':e_room,'room_count':str(e_rc_final),'hotel':e_hotel,'entry_date':e_entry,'exit_date':e_exit,'price_per_night':e_pn,'flight_cost':e_fl,'transport_cost':e_tr,'sell':e_sell,'notes':e_notes,'voucher_no':e_vno,'airline':e_air,'emp':e_emp,'transport_company':e_trans_co}
        for k,v in new_data.items(): d[k]=v
        new_row=[str(d.get(h,"")) for h in header]
        try:
            with st.spinner("Updating Google Sheet..."):
                sheet.update(f"A{row_idx}:Z{row_idx}", [new_row], value_input_option="USER_ENTERED")
            st.success("✅ تم التحديث بالشيت!"); st.session_state.table_version+=1
            import time; time.sleep(0.5); st.rerun()
        except Exception as e: st.error(f"Error: {e}")

@st.dialog("Invoice - معاينة الفاتورة", width="large")
def invoice_dialog(row):
    try:
        _sheet = get_gspread_sheet()
        all_vals = _sheet.get_all_values()
        target_id = str(row).strip()
        full = None
        for r in all_vals[1:]:
            if r and str(r[0]).strip() == target_id:
                full = r
                break
        if not full: return
        def g(i, d=""): return full[i] if len(full) > i else d
        booking_num = g(15).strip() if g(15).strip() != "" else f"BOOK-{g(0)}"
        rc = g(25) if len(full) > 25 and g(25) else 1
        data={"company":g(4),"passengers":g(5),"hotel":g(6),"entry_date":g(2),"exit_date":g(3),"sell":g(12),"voucher":booking_num,"room_type":g(21) if g(21) else "","room_count":rc,"id":g(0)}
        filename=f"{booking_num}_{sanitize_filename(data['passengers'])}.pdf"
        full_path=Path.home() / "Desktop" / "invoice" / filename
        pdf_bytes=generate_invoice_pdf(data, save_path=str(full_path))
        logo_b64 = get_logo_b64()
        logo_html = f"<img src='data:image/png;base64,{logo_b64}' style='width:110px;height:110px;object-fit:contain;background:white;border-radius:4px;padding:4px;margin-right:20px;'>" if logo_b64 else ""
        passengers_html = "".join([f"<div style='padding:4px 0'>- {p.strip()}</div>" for p in str(data['passengers']).split('\n') if p.strip()])
        html_preview = f"""<div style="background:white; border:1px solid #ddd; border-radius:12px; padding:20px; font-family:Arial; color:#222;"><div style="background:#0F2D5C; color:white; padding:12px 20px; border-radius:8px; margin:-20px -20px 20px -20px; display:flex; align-items:center; border-bottom:6px solid #FF8C00; height:135px;">{logo_html}<div><div style="font-size:28px; font-weight:bold;">HOTRIGO - INVOICE</div><div style="font-size:13px; margin-top:6px;">Invoice No: {booking_num} | Date: {datetime.now().strftime('%Y-%m-%d')}</div></div></div><div style="font-size:14px; line-height:28px;"><b>Agent:</b> {data['company']}<br><b>Invoice No:</b> {booking_num}<br><b>Hotel:</b> {data['hotel']}<br><b>Check-in:</b> {data['entry_date']} | <b>Check-out:</b> {data['exit_date']}<br><b>Room Type:</b> {data['room_type']} | <b>Rooms:</b> {data['room_count']}</div><div style="background:#f8f9fa; padding:12px 18px; border-radius:8px; font-size:14px; margin-top:12px; border-left:4px solid #FF8C00;"><b>Passengers:</b><br>{passengers_html}</div><div style="background:#f0f2f5; padding:18px; border-radius:10px; margin-top:22px; text-align:center; border:2px solid #0F2D5C;"><div style="font-size:26px; font-weight:bold; color:#0F2D5C;">Selling Price: ${float(data['sell'] or 0):,.2f}</div></div></div>"""
        st.markdown(f"### معاينة الفاتورة - {booking_num}")
        components.html(html_preview, height=560, scrolling=True)
        st.download_button("⬇️ تحميل PDF", data=pdf_bytes, file_name=filename, mime="application/pdf", use_container_width=True, type="primary")
    except Exception as e: st.error(f"Error: {e}")

@st.dialog("Booking Voucher - معاينة الفاوتشر", width="large")
def voucher_dialog(row):
    try:
        _sheet = get_gspread_sheet()
        all_vals = _sheet.get_all_values()
        target_id = str(row).strip()
        full = None
        for r in all_vals[1:]:
            if r and str(r[0]).strip() == target_id:
                full = r
                break
        if not full: return
        def g(i, d=""): return full[i] if len(full) > i else d
        rc = g(25) if g(25) else 1
        booking_no = g(15).strip() if g(15).strip() != "" else f"HTG-{int(g(0) or 0):06d}"
        data={"sale_date":g(1),"booking_no":booking_no,"passengers":g(5),"hotel":g(6),"room_type":g(21) if g(21) else "","room_count":rc,"entry_date":g(2),"exit_date":g(3),"nights":g(7),"notes":g(16) if g(16) else "","sell":g(12)}
        filename=f"VOUCHER_{booking_no}_{sanitize_filename(data['passengers'])}.pdf"
        full_path=Path.home() / "Desktop" / "voucher" / filename
        pdf_bytes=generate_voucher_pdf(data, save_path=str(full_path))
        logo_b64 = get_logo_b64()
        logo_html = f"<img src='data:image/png;base64,{logo_b64}' style='width:110px;height:110px;object-fit:contain;background:white;border-radius:4px;padding:4px;margin-right:20px;'>" if logo_b64 else ""
        passengers_html = "".join([f"<div style='padding:5px 0; font-size:15px;'>- {p.strip()}</div>" for p in str(data['passengers']).split('\n') if p.strip()])
        html_preview = f"""<div style="background:white; border:1px solid #ddd; border-radius:12px; padding:20px; font-family:Arial; color:#222;"><div style="background:#0F2D5C; color:white; padding:12px 20px; border-radius:8px; margin:-20px -20px 20px -20px; display:flex; align-items:center; border-bottom:6px solid #FF8C00; height:135px;">{logo_html}<div><div style="font-size:26px; font-weight:bold;">HOTRIGO - BOOKING VOUCHER</div><div style="font-size:13px; margin-top:6px;">Booking No: {booking_no} | Date: {data['sale_date']}</div></div></div><div style="background:#f8f9fa; padding:14px 18px; border-radius:8px; margin-bottom:14px; line-height:26px; font-size:14px;"><b>Booking No:</b> {booking_no}<br><b>Hotel:</b> {data['hotel']} | <b>Room Type:</b> {data['room_type']} | <b>Rooms:</b> {data['room_count']}<br><b>Check-in:</b> {data['entry_date']} | <b>Check-out:</b> {data['exit_date']} | <b>Nights:</b> {data['nights']}</div><div style="font-weight:bold; margin:12px 0 6px 0; font-size:15px;">Guest Names:</div><div style="background:#fff; border:1px solid #eee; border-left:4px solid #0F2D5C; padding:12px 18px; border-radius:6px;">{passengers_html}</div></div>"""
        st.markdown(f"### 🧾 معاينة الفاوتشر - {booking_no}")
        components.html(html_preview, height=700, scrolling=True)
        st.download_button("⬇️ تحميل Voucher PDF", data=pdf_bytes, file_name=filename, mime="application/pdf", use_container_width=True, type="primary")
    except Exception as e: st.error(f"Error voucher: {e}")

# ===== MAIN TABS - مختصر ويشتغل =====
st.markdown("## ✈️ hotrigo | Sheets Sync ✅")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])
with t1:
    l,r=st.columns([1, 4.8])
    with l:
        sd=st.date_input("Sale Date", datetime.now(), key="sd")
        emp=st.text_input("Sales Employee *", key="emp")
        comp=st.text_input("Agent *", key="comp")
        pas=st.text_area("Passengers *", key="pas")
        hotel=st.text_input("Hotel *", key="hotel")
        ed=st.date_input("Check-in", datetime.now()+timedelta(days=1), key="ed")
        nights=st.text_input("Nights", value="", key="nights")
        try: nights_val=int(nights) if nights else 0
        except: nights_val=0
        xd=ed+timedelta(days=nights_val)
        st.caption(f"Check-out: {xd}")
        pn_s=st.text_input("Price per Night $", key="pn")
        sell_s=st.text_input("Selling Price $ *", key="sell")
        pn=to_f(pn_s); sell=to_f(sell_s)
        if st.button("SAVE SALE", type="primary", use_container_width=True):
            if not comp.strip() or not hotel.strip() or not pas.strip(): st.error("Fill required")
            else:
                try:
                    ws=get_gspread_sheet()
                    if ws:
                        new_id=str(int(datetime.now().timestamp()))
                        ws.append_row([new_id,comp,pas,"",hotel,"","","",str(pn),"","",str(nights_val),str(xd),str(ed),"","",str(sell),"","",str(sd),"","","",emp,"","","","",""], value_input_option='USER_ENTERED')
                        st.success(f"✅ تم الرفع للشيت - {new_id}")
                        st.session_state.table_version+=1; st.rerun()
                except Exception as e: st.error(f"{e}")
    with r:
        search_val=st.text_input("Search", placeholder="Search...", key="search")
        sheet=get_gspread_sheet()
        if not sheet: st.error("Sheet not connected - فعّل Sheets API & Drive API"); st.stop()
        all_vals=sheet.get_all_values()
        if len(all_vals)<2: df_raw=pd.DataFrame()
        else:
            header=all_vals[0]; rows=all_vals[1:]
            df_raw=pd.DataFrame(rows, columns=header[:len(rows[0])] if rows else header)
            df_raw["_sheet_row"]=[i+2 for i in range(len(df_raw))]
            if search_val.strip():
                s=search_val.lower()
                df_raw=df_raw[df_raw.apply(lambda row: s in str(row.values).lower(), axis=1)]
        event=st.dataframe(df_raw.drop(columns=["_sheet_row"], errors='ignore') if not df_raw.empty else df_raw, use_container_width=True, height=650, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"main_table_{st.session_state.table_version}")
        st.markdown(f"**Total: {len(df_raw)}**")
        selected_rows=event.selection.rows if hasattr(event, 'selection') else []
        selected_ids=[]
        if selected_rows and not df_raw.empty:
            try: selected_ids=df_raw.iloc[selected_rows]["_sheet_row"].tolist()
            except: selected_ids=[selected_rows[0]+2]
        b1,b2,b3=st.columns(3)
        with b1:
            if st.button("Edit", use_container_width=True):
                if len(selected_ids)!=1: st.error("حدد سطر واحد")
                else: edit_dialog(int(selected_ids[0]))
        with b2:
            if st.button("Invoice", use_container_width=True):
                if len(selected_ids)!=1: st.error("حدد سطر واحد")
                else: invoice_dialog(int(selected_ids[0]))
        with b3:
            if st.button("Voucher", use_container_width=True):
                if len(selected_ids)!=1: st.error("حدد سطر واحد")
                else: voucher_dialog(int(selected_ids[0]))

with t2:
    st.markdown("### 💰 Payments")
    try:
        ws=get_gspread_sheet("Payments")
        df=pd.DataFrame(ws.get_all_records()) if ws else pd.DataFrame()
        st.dataframe(df, use_container_width=True)
    except Exception as e: st.error(f"{e}")
with t3:
    conn=sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
    conn.commit(); conn.close()
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### 👥 Agents")
        with st.form(key="f_agents", clear_on_submit=True):
            na=st.text_input("", placeholder="Agent name...")
            if st.form_submit_button("Add Agent", use_container_width=True) and na.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO agents (name) VALUES (?)", (na.strip().upper(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB); dfa=pd.read_sql("SELECT name as Agents FROM agents ORDER BY name", conn); conn.close()
        st.dataframe(dfa, use_container_width=True, height=250, hide_index=True)
    with c2:
        st.markdown("#### 🏨 Hotels")
        with st.form(key="f_hotels", clear_on_submit=True):
            nh=st.text_input("", placeholder="Hotel name...")
            if st.form_submit_button("Add Hotel", use_container_width=True) and nh.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO hotels (name) VALUES (?)", (nh.strip(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB); dfh=pd.read_sql("SELECT name as Hotels FROM hotels ORDER BY name", conn); conn.close()
        st.dataframe(dfh, use_container_width=True, height=250, hide_index=True)
@st.dialog("Agent Statement", width="large")
def agent_statement_dialog(agent_name):
    try:
        # ===== 1- Bookings من الشيت الأساسي (sheet1) - مو من تاب Bookings =====
        _sheet = get_gspread_sheet()
        if not _sheet:
            st.error("Sheet not connected")
            return
            
        all_vals = _sheet.get_all_values()
        if len(all_vals) < 2:
            st.warning(f"لا يوجد حجوزات"); return
        
        header = all_vals[0]
        rows = all_vals[1:]
        clean = []
        for r in rows:
            if len(r) < len(header): r = r + [""] * (len(header)-len(r))
            clean.append(r[:len(header)])
        
        bookings = pd.DataFrame(clean, columns=header)
        # فلترة حسب الوكيل - يدور على عمود company او Agent
        col_book = None
        for c in ['company', 'Company', 'Agent', 'agent']:
            if c in bookings.columns:
                col_book = c
                break
        if col_book:
            bookings = bookings[bookings[col_book].astype(str).str.strip().str.upper() == str(agent_name).strip().upper()]
        
        # ===== 2- Payments من تاب Payments =====
        try:
            p_ws = get_gspread_sheet("Payments")
            p_vals = p_ws.get_all_values() if p_ws else []
            if len(p_vals) > 1:
                p_header = p_vals[0]
                p_rows = p_vals[1:]
                p_clean = []
                for r in p_rows:
                    if len(r) < len(p_header): r = r + [""] * (len(p_header)-len(r))
                    p_clean.append(r[:len(p_header)])
                payments = pd.DataFrame(p_clean, columns=p_header)
                # دور على عمود الوكيل
                col_name = None
                for c in ['Agent Name', 'Agent', 'company', 'agent', 'Agent Name']:
                    if c in payments.columns:
                        col_name = c
                        break
                if col_name is None and len(payments.columns) > 1:
                    col_name = payments.columns[1]
                if col_name:
                    payments = payments[payments[col_name].astype(str).str.strip().str.upper() == str(agent_name).strip().upper()]
            else:
                payments = pd.DataFrame()
        except:
            payments = pd.DataFrame()

        if bookings.empty:
            st.warning(f"لا يوجد حجوزات للوكيل {agent_name}"); return

        # ===== 3- حساب المجاميع =====
        def calc_total(df, col_names):
            if df.empty: return 0.0
            for col in col_names:
                if col in df.columns:
                    try:
                        return pd.to_numeric(df[col].astype(str).str.replace('$','', regex=False).str.replace(',','', regex=False), errors='coerce').fillna(0).sum()
                    except: pass
            return 0.0

        total_sales = calc_total(bookings, ['sell', 'Sell Price', 'sell_price', 'Sell', 'Sales'])
        total_payments = calc_total(payments, ['Amount', 'amount', 'Pay Amount', 'Payment'])
        balance = total_sales - total_payments

        # ===== 4- PDF =====
        from fpdf import FPDF
        from io import BytesIO
        pdf = FPDF(orientation='L')
        pdf.add_page()
        pdf.set_font("Arial","B",16)
        pdf.cell(0,12,f"HOTRIGO - Statement - {agent_name}", ln=True, align='C')
        pdf.set_font("Arial","B",12)
        pdf.cell(0,10,f"Sales: ${total_sales:.2f} | Paid: ${total_payments:.2f} | Balance: ${balance:.2f}", ln=True, align='C')
        pdf.ln(5)
        pdf.set_font("Arial","",10)
        pdf.cell(0,8,f"Bookings: {len(bookings)} | Payments: {len(payments)} | Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True)
        # جدول مختصر للحجوزات
        if not bookings.empty:
            pdf.ln(5)
            pdf.set_font("Arial","B",9)
            for i, row in bookings.head(20).iterrows():
                try:
                    line = f"{row.get('entry_date','')} | {row.get('hotel','')} | {row.get('passengers','')[:30]} | ${row.get('sell','')}"
                    pdf.cell(0,6,line[:120], ln=True)
                except: pass
        
        buf = BytesIO()
        pdf.output(buf)
        pdf_bytes = buf.getvalue()

        # ===== 5- Excel =====
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            bookings.to_excel(writer, sheet_name='Bookings', index=False)
            (payments if not payments.empty else pd.DataFrame([{'Note':'No payments'}])).to_excel(writer, sheet_name='Payments', index=False)
        output.seek(0)
        excel_bytes = output.getvalue()

        # حفظ ورفع Drive
        filename_pdf = f"STATEMENT_{agent_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        full_path_pdf = Path.home() / "Desktop" / "statements" / filename_pdf
        try:
            os.makedirs(os.path.dirname(full_path_pdf), exist_ok=True)
            with open(full_path_pdf, "wb") as f: f.write(pdf_bytes)
            upload_drive(str(full_path_pdf))
        except: pass

        st.markdown(f"### كشف حساب: {agent_name}")
        st.markdown(f"""<div style="background:#0d47a1;color:white;padding:12px;border-radius:8px;text-align:center;font-size:16px">
        المبيعات: ${total_sales:,.2f} | المدفوع: ${total_payments:,.2f} | الباقي: <b>${balance:,.2f}</b>
        </div>""", unsafe_allow_html=True)
        
        c1,c2 = st.columns(2)
        with c1:
            st.download_button("📄 تحميل PDF", data=pdf_bytes, file_name=filename_pdf, mime="application/pdf", use_container_width=True, type="primary", key=f"dl_stmt_pdf_{agent_name}")
        with c2:
            st.download_button("📊 تحميل Excel", data=excel_bytes, file_name=f"STATEMENT_{agent_name}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"dl_stmt_xl_{agent_name}")

        b64 = base64.b64encode(pdf_bytes).decode()
        st.markdown(f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0" width="100%" height="500px" style="border:none;"></iframe>', unsafe_allow_html=True)
        
        # جدول الحجوزات
        st.divider()
        st.markdown("#### الحجوزات")
        st.dataframe(bookings, use_container_width=True, height=300)
        if not payments.empty:
            st.markdown("#### المدفوعات")
            st.dataframe(payments, use_container_width=True, height=200)
            
    except Exception as e:
        st.error(f"Error statement: {e}")
        import traceback; st.code(traceback.format_exc())
        
st.markdown("## ✈️ hotrigo | Sheets Sync ✅")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])

with t1:
    l,r=st.columns([1, 4.8])
    with l:
        sd=st.date_input("Sale Date", datetime.now(), key="sd")
        emp=st.text_input("Sales Employee *", key="emp")
        comp=st.text_input("Agent *", key="comp", placeholder="")
        pax_count=st.text_input("Number of Persons", value="1", key="pax_count", placeholder="")
        try:
            pax_num = int(pax_count) if pax_count.strip()!="" else 1
        except:
            pax_num = 1
        pax_num = max(1, pax_num)
        passenger_list = []
        if pax_num > 20:
            st.warning(f"Group of {pax_num} detected - Please upload Excel")
            up_file = st.file_uploader("Upload Passenger List Excel", type=["xlsx","xls","csv"], key="up_pas")
            if up_file is not None:
                try:
                    if up_file.name.endswith(".csv"):
                        df = pd.read_csv(up_file)
                    else:
                        df = pd.read_excel(up_file)
                    col = df.columns[0]
                    passenger_list = df[col].astype(str).tolist()
                    st.success(f"Loaded {len(passenger_list)} names")
                except Exception as e:
                    st.error(f"Error reading file: {e}")
        else:
            pax_num = min(pax_num, 20)
            for i in range(pax_num):
                name = st.text_input(f"Passenger {i+1} *", key=f"pas_{i}", placeholder=f"Name {i+1}")
                passenger_list.append(name)

        pas = "\n".join([n for n in passenger_list if str(n).strip()!=""])
        room_type=st.text_input("Room Type *", key="room_type", placeholder="SNG - DBL - TRP")
        room_count=st.text_input("Number of Rooms", value="", key="room_count", placeholder="")
        hotel=st.text_input("Hotel *", key="hotel", placeholder="")
        ed=st.date_input("Check-in Date", datetime.now()+timedelta(days=1), key="ed")
        nights=st.text_input("Nights", value="", key="nights", placeholder="")
        try: nights_val=int(nights) if nights.strip()!="" else 0
        except: nights_val=0
        xd=ed+timedelta(days=nights_val)
        st.caption(f"Check-out: {xd}")
        c_price, c_flight = st.columns(2)
        with c_price: pn_s=st.text_input("Price per Night $", key="pn")
        with c_flight: fl_s=st.text_input("Flight $", key="fl")
        c_trans, c_sell = st.columns(2)
        with c_trans: tr_s=st.text_input("Transport $", key="tr")
        with c_sell: sell_s=st.text_input("Selling Price $ *", key="sell")
        pn=to_f(pn_s); fl=to_f(fl_s); tr=to_f(tr_s); sell=to_f(sell_s)
        try: room_count_val=int(room_count) if room_count.strip()!="" else 0
        except: room_count_val=0
        rc_for_calc = room_count_val if room_count_val > 0 else 1
        cost_total = (pn * nights_val * rc_for_calc) + fl + tr
        if cost_total > 0:
            st.caption(f"💰 الكوست صار علينا: ${cost_total:,.2f}")
        notes=st.text_input("Note", key="notes")
        airline=st.text_input("Airline (empty=no flight)", key="airline", placeholder="")
        vno=st.text_input("Voucher No", key="vno")
        with st.expander("➕ Show More", expanded=False):
            c_dep, c_ret=st.columns(2)
            with c_dep: dep_time=st.text_input("Departure Time", key="dep_time", placeholder="10:30")
            with c_ret: ret_time=st.text_input("Return Time", key="ret_time", placeholder="18:45")
            c_fno_dep, c_fno_ret = st.columns(2)
            with c_fno_dep: flight_no_dep=st.text_input("Flight No Dep", key="flight_no_dep", placeholder="TK2026")
            with c_fno_ret: flight_no_ret=st.text_input("Flight No Ret", key="flight_no_ret", placeholder="TK2027")
            c_air_dep, c_air_ret = st.columns(2)
            with c_air_dep: dep_airport=st.text_input("Departure Airport", key="dep_airport", placeholder="IST")
            with c_air_ret: ret_airport=st.text_input("Return Airport", key="ret_airport", placeholder="BEY")
            transport_co=st.text_input("Transport Company (empty=no transfer)", key="transport_co", placeholder="")

        if st.button("SAVE SALE", type="primary", use_container_width=True, key="save_btn"):
            airline_val = airline.strip()
            transport_val = transport_co.strip()
            comp_full, comp_ok = smart_match(comp, agents_for_js, agents_upper)
            hotel_full, hotel_ok = smart_match(hotel, hotels_for_js, hotels_upper)
            is_no_flight = airline_val == "" or airline_val == "0"
            is_no_transport = transport_val == "" or transport_val == "0"
            airline_full, airline_ok = ("", True) if is_no_flight else smart_match(airline_val, airlines_for_js, airlines_upper)
            transport_full, transport_ok = ("", True) if is_no_transport else smart_match(transport_val, transport_for_js, transport_upper)
            if not comp.strip() or not hotel.strip() or not emp.strip() or not pas.strip(): 
                st.error("Fill required")
            elif not comp_ok: st.error(f"❌ Agent '{comp}' not found! Add in Agents tab")
            elif not hotel_ok: st.error(f"❌ Hotel '{hotel}' not found!")
            elif not airline_ok: st.error(f"❌ Airline '{airline}' not found!")
            elif not transport_ok: st.error(f"❌ Transport '{transport_co}' not found!")
            else:
                ht_tot = pn * nights_val * rc_for_calc
                cost = ht_tot + fl + tr
                profit = sell - cost
                st.session_state["pending"]={
                    "sale_date":str(sd),"entry_date":str(ed),"exit_date":str(xd),
                    "company":comp_full,"passengers":pas.strip(),"hotel":hotel_full,
                    "room_type":room_type.strip(),"room_count":room_count_val,"nights":nights_val,
                    "price_night":float(pn),"hotel_total":float(ht_tot),
                    "flight":float(fl),"transport":float(tr),"sell":float(sell),
                    "cost":float(cost),"profit":float(profit),
                    "voucher":vno,"notes":notes,"airline":airline_full,"emp":emp.strip(),
                    "dep":dep_time.strip(),"ret":ret_time.strip(),
                    "transport_company":transport_full,
                    "fno_dep":flight_no_dep.strip(),"fno_ret":flight_no_ret.strip()
                }

        if st.session_state.get("pending"):
            d=st.session_state["pending"]
            st.warning(f"✅ {d['company']} - {d['passengers'].split(chr(10))[0]} | {d['room_count']} Rooms | Sell ${d['sell']:.2f}")
            c1,c2=st.columns(2)
            with c1:
                if st.button("YES", type="primary", use_container_width=True):
                    try:
                        conn=sqlite3.connect(DB, check_same_thread=False)
                        conn.execute("""CREATE TABLE IF NOT EXISTS bookings 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, sale_date TEXT, entry_date TEXT, exit_date TEXT, company TEXT, passengers TEXT, hotel TEXT, nights INTEGER, price_night REAL, hotel_total REAL, flight REAL, transport REAL, sell REAL, cost REAL, profit REAL, voucher TEXT, notes TEXT, airline TEXT, emp TEXT, flight_dep_time TEXT, flight_ret_time TEXT, room_type TEXT, transport_company TEXT, flight_no_dep TEXT, flight_no_ret TEXT, room_count INTEGER)""")
                        cur=conn.cursor()
                        cur.execute("INSERT INTO bookings (sale_date,entry_date,exit_date,company,passengers,hotel,nights,price_night,hotel_total,flight,transport,sell,cost,profit,voucher,notes,airline,emp,flight_dep_time,flight_ret_time,room_type,transport_company,flight_no_dep,flight_no_ret,room_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (d["sale_date"],d["entry_date"],d["exit_date"],d["company"],d["passengers"],d["hotel"],d["nights"],d["price_night"],d["hotel_total"],d["flight"],d["transport"],d["sell"],d["cost"],d["profit"],d["voucher"],d["notes"],d["airline"],d["emp"],d["dep"],d["ret"],d["room_type"],d["transport_company"],d["fno_dep"],d["fno_ret"],d["room_count"]))
                        new_id = cur.lastrowid
                        conn.commit(); conn.close()
                        with st.spinner(f"جاري الرفع للـ Google Sheet - ID {new_id}..."):
                            sheet = get_gspread_sheet()
                            if sheet:
                                row = [str(new_id), d["company"], d["passengers"], "", d["hotel"], str(d["room_count"]), d["room_type"], str(d["price_night"]), str(d["hotel_total"]), d["entry_date"], str(d["nights"]), d["exit_date"], str(d["flight"]), str(d["transport"]), str(d["sell"]), str(d["cost"]), str(d["profit"]), d["sale_date"], d["voucher"], d["notes"], d["airline"], d["emp"], d["dep"], d["ret"], d["fno_dep"], d["fno_ret"], d["transport_company"]]
                                sheet.append_row(row, value_input_option='USER_ENTERED')
                                st.success(f"✅ تم الرفع للـ Sheet - ID {new_id}")
                            else:
                                st.warning("تم الحفظ محلياً - فشل الرفع للشيت")
                        st.session_state.pending=None; st.rerun()
                    except Exception as e:
                        st.error(f"Save error: {e}")
            with c2:
                if st.button("NO", use_container_width=True): 
                    st.session_state.pending=None; st.rerun()
with t2:
    st.markdown("### 💰 Account Statement - Google Sheets")
    def to_f_local(x):
        try: return float(str(x).replace('$','').replace(',','').strip() or 0)
        except: return 0

    def generate_pdf_bytes(pay_agent):
        from fpdf import FPDF
        from io import BytesIO
        ws_res = get_gspread_sheet()
        ws_pay = get_gspread_sheet("Payments")
        if ws_res:
            vals = ws_res.get_all_values()
            if len(vals) > 1:
                hdr = vals[0]
                rows = vals[1:]
                df_book = pd.DataFrame([r + [""]*(len(hdr)-len(r)) for r in rows], columns=hdr)
            else:
                df_book = pd.DataFrame()
        else:
            df_book = pd.DataFrame()
        df_pay = pd.DataFrame(ws_pay.get_all_records()) if ws_pay and ws_pay.get_all_records() else pd.DataFrame()
        
        if not df_book.empty:
            col = 'company' if 'company' in df_book.columns else df_book.columns[1] if len(df_book.columns)>1 else None
            if col: df_book = df_book[df_book[col].astype(str).str.upper()==str(pay_agent).strip().upper()]
        if not df_pay.empty and 'Agent Name' in df_pay.columns: 
            df_pay = df_pay[df_pay['Agent Name'].astype(str).str.upper()==str(pay_agent).strip().upper()]
            
        if df_book.empty and df_pay.empty: return None
        total_sell = pd.to_numeric(df_book['sell'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').sum() if 'sell' in df_book.columns else 0
        total_paid = pd.to_numeric(df_pay['Amount'], errors='coerce').sum() if 'Amount' in df_pay.columns else 0
        
        pdf=FPDF(orientation='L'); pdf.add_page()
        pdf.set_font("Arial","B",14)
        pdf.cell(0,10,f"Statement - {pay_agent} | Sales ${total_sell:.2f} | Paid ${total_paid:.2f} | Balance ${total_sell-total_paid:.2f}",ln=True,align='C')
        buf=BytesIO(); pdf.output(buf); return buf.getvalue()

    def generate_excel_bytes(pay_agent):
        from io import BytesIO
        ws_res = get_gspread_sheet()
        ws_pay = get_gspread_sheet("Payments")
        if ws_res:
            vals = ws_res.get_all_values()
            if len(vals) > 1:
                hdr = vals[0]
                rows = vals[1:]
                df1 = pd.DataFrame([r + [""]*(len(hdr)-len(r)) for r in rows], columns=hdr)
            else:
                df1 = pd.DataFrame()
        else:
            df1 = pd.DataFrame()
        df2 = pd.DataFrame(ws_pay.get_all_records()) if ws_pay and ws_pay.get_all_records() else pd.DataFrame()
        
        if not df1.empty:
            col = 'company' if 'company' in df1.columns else df1.columns[1] if len(df1.columns)>1 else None
            if col: df1 = df1[df1[col].astype(str).str.upper()==str(pay_agent).strip().upper()]
        if not df2.empty and 'Agent Name' in df2.columns: 
            df2 = df2[df2['Agent Name'].astype(str).str.upper()==str(pay_agent).strip().upper()]
            
        output=BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            (df1 if not df1.empty else pd.DataFrame([{'Note':'No bookings'}])).to_excel(writer, sheet_name='Bookings', index=False)
            (df2 if not df2.empty else pd.DataFrame([{'Note':'No payments'}])).to_excel(writer, sheet_name='Payments', index=False)
        output.seek(0); return output.getvalue()

    agents_list = agents_for_js
    left_side, right_side = st.columns([1, 1], gap="large")
    with left_side:
        st.markdown("#### Add New Payment")
        pay_agent = st.selectbox("Agent Name", agents_list if agents_list else ["No agents"], key="pay_agent_main")
        pay_date = st.date_input("Payment Date", datetime.now(), key="pay_date_main")
        pay_amount = st.text_input("Payment Amount $", key="pay_amount_main", placeholder="$ Amount")
        pay_statement = st.text_input("Statement", key="pay_statement_main", placeholder="e.g. Hotel booking payment...")
        pay_note = st.text_input("Note", key="pay_note_main", placeholder="Bank - Cash...")
        if st.button("Add Payment", use_container_width=True, type="primary", key="btn_add_pay_main"):
            amt = to_f_local(pay_amount)
            if amt <= 0: 
                st.error("Please enter valid amount")
            else:
                ok = add_payment("Payments", pay_agent, amt, pay_statement, pay_note)
                if ok:
                    st.success(f"✅ Payment ${amt} added")
                    st.session_state.table_version += 1
                    st.rerun()
        try: pdf_bytes = generate_pdf_bytes(pay_agent)
        except: pdf_bytes = None
        try: excel_bytes = generate_excel_bytes(pay_agent)
        except: excel_bytes = None
        b1, b2 = st.columns(2, gap="small")
        with b1:
            if pdf_bytes: st.download_button("🖨️ Print PDF", data=pdf_bytes, file_name=f"HOTRIGO_{pay_agent}_statement.pdf", mime="application/pdf", use_container_width=True, key=f"dl_pdf_one_{pay_agent}")
        with b2:
            if excel_bytes: st.download_button("📊 Export Excel", data=excel_bytes, file_name=f"HOTRIGO_{pay_agent}_statement.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"dl_excel_one_{pay_agent}")
            
    with right_side:
        st.markdown("#### 💰 Agents Summary")
        try:
            ws_res = get_gspread_sheet()
            ws_pay = get_gspread_sheet("Payments")
            if ws_res:
                vals = ws_res.get_all_values()
                if len(vals) > 1:
                    hdr = vals[0]
                    df_all_bookings = pd.DataFrame([r + [""]*(len(hdr)-len(r)) for r in vals[1:]], columns=hdr)
                else:
                    df_all_bookings = pd.DataFrame()
            else:
                df_all_bookings = pd.DataFrame()
            df_all_pays = pd.DataFrame(ws_pay.get_all_records()) if ws_pay and ws_pay.get_all_records() else pd.DataFrame()
            
            summary=[]
            for ag in agents_list:
                sales = 0; paid = 0
                if not df_all_bookings.empty and 'company' in df_all_bookings.columns and 'sell' in df_all_bookings.columns:
                    try:
                        mask = df_all_bookings['company'].astype(str).str.upper()==ag.upper()
                        sales = pd.to_numeric(df_all_bookings[mask]['sell'].astype(str).str.replace('$','').str.replace(',',''), errors='coerce').sum()
                    except: pass
                if not df_all_pays.empty and 'Agent Name' in df_all_pays.columns and 'Amount' in df_all_pays.columns:
                    try:
                        mask = df_all_pays['Agent Name'].astype(str).str.upper()==ag.upper()
                        paid = pd.to_numeric(df_all_pays[mask]['Amount'], errors='coerce').sum()
                    except: pass
                summary.append({"Agent":ag, "Sales":sales, "Paid":paid, "Balance":sales-paid})
            df_summary=pd.DataFrame(summary)
            if not df_summary.empty:
                st.dataframe(df_summary.style.format({"Sales":"${:.2f}","Paid":"${:.2f}","Balance":"${:.2f}"}), use_container_width=True, height=250)
                st.markdown(f"""<div style="background:#0d47a1;color:white;padding:10px;border-radius:8px;text-align:center">
                Sales: ${df_summary['Sales'].sum():.2f} | Paid: ${df_summary['Paid'].sum():.2f} | Due: ${df_summary['Balance'].sum():.2f}
                </div>""", unsafe_allow_html=True)
        except Exception as e: st.error(f"Summary Error: {e}")
        st.divider()
        st.markdown(f"#### Statement - Payments")
        try:
            ws_pay = get_gspread_sheet("Payments")
            df_p = pd.DataFrame(ws_pay.get_all_records()) if ws_pay and ws_pay.get_all_records() else pd.DataFrame()
            if not df_p.empty: st.dataframe(df_p, use_container_width=True, height=300)
            else: st.caption("No payments yet")
        except Exception as e: st.error(f"{e}")
with t3:
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT PRIMARY KEY)")
    conn.commit(); conn.close()
    
    c1, c2, c3, c4 = st.columns(4, gap="medium")
    with c1:
        with st.container(border=True):
            st.markdown("#### 👥 Agents")
            with st.form(key="f_agents", clear_on_submit=True):
                na = st.text_input("", placeholder="Agent name...", label_visibility="collapsed")
                sa = st.form_submit_button("Add Agent", use_container_width=True)
                if sa and na.strip():
                    conn=sqlite3.connect(DB)
                    try: 
                        conn.execute("INSERT INTO agents (name) VALUES (?)", (na.strip().upper(),))
                        conn.commit()
                    except: 
                        pass
                    conn.close()
                    st.rerun()
            conn=sqlite3.connect(DB)
            try:
                dfa=pd.read_sql("SELECT name as Agents FROM agents ORDER BY name", conn)
            except:
                dfa=pd.DataFrame(columns=["Agents"])
            conn.close()
            st.dataframe(dfa, use_container_width=True, height=250, hide_index=True)
            
    with c2:
        with st.container(border=True):
            st.markdown("#### 🏨 Hotels")
            with st.form(key="f_hotels", clear_on_submit=True):
                nh = st.text_input("", placeholder="Hotel name...", label_visibility="collapsed")
                sh = st.form_submit_button("Add Hotel", use_container_width=True)
                if sh and nh.strip():
                    conn=sqlite3.connect(DB)
                    try: 
                        conn.execute("INSERT INTO hotels (name) VALUES (?)", (nh.strip(),))
                        conn.commit()
                    except: 
                        pass
                    conn.close()
                    st.rerun()
            conn=sqlite3.connect(DB)
            try:
                dfh=pd.read_sql("SELECT name as Hotels FROM hotels ORDER BY name", conn)
            except:
                dfh=pd.DataFrame(columns=["Hotels"])
            conn.close()
            st.dataframe(dfh, use_container_width=True, height=250, hide_index=True)
            
    with c3:
        with st.container(border=True):
            st.markdown("#### ✈️ Airlines")
            with st.form(key="f_airlines", clear_on_submit=True):
                nal = st.text_input("", placeholder="Airlines name...", label_visibility="collapsed")
                sal = st.form_submit_button("Add Airline", use_container_width=True)
                if sal and nal.strip():
                    conn=sqlite3.connect(DB)
                    try: 
                        conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
                        conn.execute("INSERT INTO airlines (name) VALUES (?)", (nal.strip().upper(),))
                        conn.commit()
                    except: 
                        pass
                    conn.close()
                    st.rerun()
            conn=sqlite3.connect(DB)
            try:
                conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
                dfal=pd.read_sql("SELECT name as Airlines FROM airlines ORDER BY name", conn)
            except: 
                dfal=pd.DataFrame(columns=["Airlines"])
            conn.close()
            st.dataframe(dfal, use_container_width=True, height=250, hide_index=True)
            
    with c4:
        with st.container(border=True):
            st.markdown("#### 🚌 Transport")
            with st.form(key="f_transport", clear_on_submit=True):
                nt = st.text_input("", placeholder="Transportation name...", label_visibility="collapsed")
                stf = st.form_submit_button("Add Transport", use_container_width=True)
                if stf and nt.strip():
                    conn=sqlite3.connect(DB)
                    try: 
                        conn.execute("INSERT INTO transport_companies (name) VALUES (?)", (nt.strip().upper(),))
                        conn.commit()
                    except: 
                        pass
                    conn.close()
                    st.rerun()
            conn=sqlite3.connect(DB)
            try:
                dft=pd.read_sql("SELECT name as Transport FROM transport_companies ORDER BY name", conn)
            except:
                dft=pd.DataFrame(columns=["Transport"])
            conn.close()
            st.dataframe(dft, use_container_width=True, height=250, hide_index=True)
