import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit.components.v1 as components
import os, io, re, json, base64
from pathlib import Path

# ===== GOOGLE DRIVE + SHEETS =====
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    DRIVE_AVAILABLE = True
except:
    DRIVE_AVAILABLE = False

try:
    import gspread
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    SHEETS_AVAILABLE = True
except:
    SHEETS_AVAILABLE = False

BASE_DIR = os.path.dirname(__file__)
DRIVE_FOLDER = "Hotrigo Backup"
SHEET_NAME = "HOTRIGO_DATABASE"
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Price Night","Hotel Total","Check-in","Nights","Check-out","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]

def get_drive_service():
    try:
        if "gdrive" not in st.secrets:
            return None, None
        creds_dict = dict(st.secrets["gdrive"])
        folder_id = creds_dict.pop("FOLDER_ID", None)
        pk = creds_dict.get("private_key", "")
        if "\\n" in pk:
            creds_dict["private_key"] = pk.replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/drive'])
        service = build('drive', 'v3', credentials=creds)
        return service, folder_id
    except Exception as e:
        return None, None
def get_folder_id(service, name):
    try:
        q=f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
        res=service.files().list(q=q, fields="files(id)").execute()
        files=res.get('files',[])
        if files: return files[0]['id']
        folder=service.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder'},fields='id').execute()
        return folder.get('id')
    except: return None

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
            # 1- جيب المجلد الرئيسي Hotrigo Backup
            if folder_id_secret:
                folder_id = folder_id_secret
            else:
                folder_id=get_folder_id(service, DRIVE_FOLDER)

            if folder_id:
                fname=os.path.basename(local_path)
                up=fname.upper()
                # 2- حدد المجلد الفرعي حسب اسم الملف
                if up.startswith("BOOK-"):
                    folder_id = get_or_create_subfolder(service, folder_id, "Invoices")
                elif up.startswith("VOUCHER_"):
                    folder_id = get_or_create_subfolder(service, folder_id, "Vouchers")
                elif up.startswith("STATEMENT_"):
                    folder_id = get_or_create_subfolder(service, folder_id, "Statements")

                q=f"name='{fname}' and '{folder_id}' in parents and trashed=false"
                ex=service.files().list(q=q, fields="files(id)").execute()
                for f in ex.get('files',[]):
                    try: service.files().delete(fileId=f['id']).execute()
                    except: pass
                media=MediaFileUpload(local_path, resumable=True)
                service.files().create(body={'name':fname,'parents':[folder_id]}, media_body=media).execute()
                print(f"✅ API Upload: {fname} -> {folder_id}")
                return True
    except Exception as e:
        print(f"Upload Error: {e}")
    return False

def get_sheet_client():
    try:
        if "gdrive" not in st.secrets:
            return None
        creds_dict = dict(st.secrets["gdrive"])
        creds_dict.pop("FOLDER_ID", None)
        pk = creds_dict.get("private_key", "")
        if "\\n" in pk:
            creds_dict["private_key"] = pk.replace("\\n", "\n")
        creds = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=['https://www.googleapis.com/auth/spreadsheets','https://www.googleapis.com/auth/drive'])
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        print(f"Sheet Error: {e}")
        return None

def load_data():
    try:
        sheet = get_gspread_sheet()
        if not sheet:
            return []
        records = sheet.get_all_records()
        return records
    except Exception as e:
        print(f"Load error: {e}")
        return []

def get_gspread_sheet():
    try:
        client = get_sheet_client()
        if not client:
            return None
        spreadsheet = client.open(SHEET_NAME)
        try:
            sheet = spreadsheet.worksheet("reservations")
        except:
            sheet = spreadsheet.sheet1
        # اذا الشيت فاضي تماما حط الهيدر بس
        try:
            vals = sheet.get_all_values()
            if len(vals) == 0:
                sheet.append_row(SHEET_HEADER)
        except:
            pass
        return sheet
    except Exception as e:
        print(f"Sheet open failed: {e}")
        return None
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Price Night","Hotel Total","Check-in","Nights","Check-out","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]

def booking_to_sheet_row(b):
    try:
        from datetime import datetime
        
        # ما عاد في sqlite - ناخد الداتا مباشر من الـ dict
        try: 
            d = dict(b)
        except: 
            d = {k: b[k] for k in b.keys()}

        def gv(k, default=""):
            v = d.get(k, default)
            return "" if v is None else v

        def to_f(v):
            try: 
                return float(str(v).replace(",", "").strip() or 0)
            except: 
                return 0.0

        nights = 0
        try:
            en = datetime.strptime(str(gv("entry_date"))[:10], "%Y-%m-%d")
            ex = datetime.strptime(str(gv("exit_date"))[:10], "%Y-%m-%d")
            nights = max(0, (ex - en).days)
        except:
            pass

        # رجع الصف بنفس ترتيب الهيدر تماما
        row = []
        for h in SHEET_HEADER:
            if h == "Nights" or h == "Night":
                row.append(nights)
            else:
                # نحاول نجيب القيمة - نجرب الاسم متل ما هو و small case
                val = d.get(h, d.get(h.lower(), d.get(h.replace(" ", "_").lower(), "")))
                row.append(val)
        
        return row

    except Exception as e:
        print(f"booking_to_sheet_row error: {e}")
        return None

        def gv(k, default=""):
            v = d.get(k, default)
            return "" if v is None else v
        def to_f(v):
            try: return float(str(v).replace(",", "").strip() or 0)
            except: return 0.0

        nights = 0
        try:
            en = datetime.strptime(str(gv("entry_date"))[:10], "%Y-%m-%d")
            ex = datetime.strptime(str(gv("exit_date"))[:10], "%Y-%m-%d")
            nights = max(0, (ex - en).days)
        except: nights = 0

        try: room_count = 0 if str(gv("room_count")).strip()=="" else int(float(str(gv("room_count"))))
        except: room_count = 0

        pax_names = str(gv("passengers")).strip()
        pax_count = len([x for x in pax_names.replace("\n",",").split(",") if x.strip()!=""]) if pax_names else 0

        sell = to_f(gv("sell"))
        pn = to_f(gv("price_per_night"))
        fl = to_f(gv("flight_cost"))
        tr = to_f(gv("transport_cost"))
        hotel_total = pn * room_count * (nights if nights>0 else 1)
        cost = hotel_total + fl + tr
        if room_count==0: cost = fl + tr
        profit = sell - cost

        row = [
            gv("id"),
            gv("company"),
            gv("passengers"),
            pax_count,
            gv("hotel"),
            room_count,
            gv("room_type"),
            pn, # Price Night
            hotel_total, # Hotel Total
            gv("entry_date"), # Check-in
            nights, # Nights
            gv("exit_date"), # Check-out
            fl, # Flight $
            tr, # Transport $
            sell, # Sell Price
            cost, # Cost
            profit, # Profit
            gv("sale_date"),
            gv("voucher_no"),
            gv("notes"),
            gv("airline"),
            gv("emp"),
            gv("flight_dep_time"),
            gv("flight_ret_time"),
            gv("flight_no_dep"),
            gv("flight_no_ret"),
            gv("transport_company"),
        ]
        return [str(x) if x is not None else "" for x in row]
    except Exception as e:
        print(f"booking_to_sheet_row error {e} for {b}")
        return None

def sync_booking_to_sheet(booking_data):
    try:
        sheet = get_gspread_sheet()
        if not sheet: 
            return False
        
        # اذا بعتت dict بياخدو مباشر، اذا بعتت id قديم ما عاد يشتغل
        # لازم تبعت الـ dict تبع الحجز
        if isinstance(booking_data, dict):
            b = booking_data
            booking_id = str(b.get("id", b.get("ID", "")))
        else:
            # للتوافق القديم - بس ما رح يلاقي شي لانو لغينا اللوكال
            print(f"Please pass dict not ID: {booking_data}")
            return False

        row = booking_to_sheet_row(b)
        if not row: 
            return False

        try:
            # حاول تلاقي الـ ID بالشيت وتعمل update
            cell = sheet.find(booking_id)
            sheet.update(f"A{cell.row}:AA{cell.row}", [row])
            print(f"✅ Updated ID {booking_id}")
        except:
            # اذا مو موجود اعمل append جديد
            sheet.append_row(row, value_input_option='USER_ENTERED')
            print(f"✅ Appended ID {booking_id}")
        
        return True
        
    except Exception as e:
        print(f"Sync failed {booking_data}: {e}")
        return False
def sync_all_to_sheet():
    """Disabled - هاد الفنكشن كان يمسح الشيت كلو بـ clear() لهيك لغيناه"""
    print("sync_all_to_sheet is disabled - all data now lives on Google Sheet directly")
    return True

# --- PDF Imports - طريقة آمنة بدون os.system ---
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    # لا تستخدم os.system داخل Streamlit - بيعمل مشاكل
    print("reportlab not installed, add it to requirements.txt")

# --- تم الغاء قاعدة البيانات المحلية ---
# DB = os.path.join(os.path.dirname(__file__), "hotrigo.db")  <- ملغي، ما عاد نحتاجو
# كل الحفظ صار مباشر على Google Sheet

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo.png")
# اذا اللوغو مو موجود على GitHub رح يطلع تحذير بس ما رح يوقف البرنامج
def get_logo_b64():
    if os.path.exists(LOGO_PATH):
        try:
            with open(LOGO_PATH, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except:
            return None
    return None

def init():
    """
    Init الجديد - ما عاد في sqlite ولا DB
    كل شي صار على Google Sheet مباشر
    """
    try:
        sheet = get_gspread_sheet()
        if sheet:
            try:
                # اذا الشيت فاضي، حط الهيدر
                first_row = sheet.row_values(1)
                if not first_row or len(first_row) == 0:
                    sheet.update('A1', [SHEET_HEADER])
                    print("✅ Header created in Sheet")
            except Exception as e:
                print(f"Header check: {e}")
        print("✅ Init done - Google Sheet ready")
    except Exception as e:
        print(f"Init warning: {e}")
    
    return True
init()

if "pending" not in st.session_state:
    st.session_state["pending"] = None
if "do_clear" not in st.session_state:
    st.session_state["do_clear"] = False
if "table_version" not in st.session_state:
    st.session_state["table_version"] = 0
if "search_mode" not in st.session_state:
    st.session_state["search_mode"] = "بحث"

if st.session_state["do_clear"]:
    for k in ["emp","pas","comp","hotel","pn","fl","tr","sell","air","note","vno","sd","ed","xd","ftd","ftr","fti","fto"]:
        if k in st.session_state:
            try: del st.session_state[k]
            except: pass
    st.session_state["do_clear"] = False
    st.session_state["pending"] = None

def to_f(s):
    try: return float(str(s).replace(",","").strip()) if str(s).strip()!="" else 0.0
    except: return 0.0

def smart_match(input_val, full_list, upper_list):
    v = input_val.strip().upper()
    if not v or v=="0": return "", True
    if v in upper_list: return full_list[upper_list.index(v)], True
    return input_val, False

def sanitize_filename(name):
    name = str(name).split('\n')[0].strip()
    name = re.sub(r'[\\/*?:"<>|]', '', name).replace(' ', '_')
    return name[:60] if name else "Traveler"

def clear_filters():
    st.session_state.entry_date_filter=None
    st.session_state.exit_date_filter=None
    st.session_state.search=""
    st.session_state.search_mode="الكل"

def generate_invoice_pdf(data, save_path=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    HEADER_H = 135
    c.setFillColorRGB(0.06, 0.18, 0.36)
    c.rect(0, height-HEADER_H, width, HEADER_H, fill=1, stroke=0)
    c.setFillColorRGB(1, 0.55, 0)
    c.rect(0, height-HEADER_H-6, width, 6, fill=1, stroke=0)
    has_logo = os.path.exists(LOGO_PATH)
    booking_num = data.get('voucher','') or data.get('booking_no','') or f"BOOK-{data.get('id','')}"
    if has_logo:
        try:
            c.drawImage(LOGO_PATH, 20, height-HEADER_H+12, width=110, height=110, preserveAspectRatio=True, mask='auto')
            c.setFillColorRGB(1,1,1)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(145, height-55, "HOTRIGO - INVOICE")
            c.setFont("Helvetica", 11)
            c.drawString(145, height-75, f"Invoice No: {booking_num} | Date: {datetime.now().strftime('%Y-%m-%d')}")
        except:
            c.setFillColorRGB(1,1,1)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(30, height-60, "HOTRIGO - INVOICE")
    else:
        c.setFillColorRGB(1,1,1)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(30, height-60, "HOTRIGO - INVOICE")
        c.setFont("Helvetica", 11)
        c.drawString(30, height-80, f"Invoice No: {booking_num} | Date: {datetime.now().strftime('%Y-%m-%d')}")
    c.setFillColorRGB(0,0,0)
    y = height-HEADER_H-40
    c.setFont("Helvetica-Bold", 13)
    c.drawString(30, y, f"Agent: {data.get('company','')}")
    y-=24; c.drawString(30, y, f"Invoice No: {booking_num}"); y-=24
    c.drawString(30, y, f"Hotel: {data.get('hotel','')}"); y-=24
    c.drawString(30, y, f"Check-in: {data.get('entry_date','')} | Check-out: {data.get('exit_date','')}"); y-=24
    c.drawString(30, y, f"Room Type: {data.get('room_type','')} | Rooms: {data.get('room_count',1)}"); y-=32
    c.setFont("Helvetica-Bold", 12); c.drawString(30, y, "Passengers:"); y-=20
    c.setFont("Helvetica", 11)
    for name in str(data.get('passengers','')).strip().split('\n'):
        if name.strip():
            c.drawString(45, y, f"- {name.strip()}"); y-=18
            if y < 150:
                c.showPage(); y = height-50; c.setFont("Helvetica", 11)
    y-=30
    c.setFillColorRGB(0.95,0.95,0.95); c.rect(30, y-15, width-60, 60, fill=1, stroke=0)
    c.setFillColorRGB(0.06, 0.18, 0.36); c.setFont("Helvetica-Bold", 22)
    c.drawString(40, y+15, f"Selling Price: ${float(data.get('sell',0)):,.2f}")
    c.showPage(); c.save()
    pdf_bytes=buffer.getvalue(); buffer.close()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f: f.write(pdf_bytes)
        upload_drive(save_path)
    return pdf_bytes

def generate_voucher_pdf(data, save_path=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    HEADER_H = 135
    c.setFillColorRGB(0.06, 0.18, 0.36); c.rect(0, height-HEADER_H, width, HEADER_H, fill=1, stroke=0)
    c.setFillColorRGB(1, 0.55, 0); c.rect(0, height-HEADER_H-6, width, 6, fill=1, stroke=0)
    has_logo = os.path.exists(LOGO_PATH)
    if has_logo:
        try:
            c.drawImage(LOGO_PATH, 20, height-HEADER_H+12, width=110, height=110, preserveAspectRatio=True, mask='auto')
            c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold", 26)
            c.drawString(145, height-55, "HOTRIGO - BOOKING VOUCHER")
            c.setFont("Helvetica", 11)
            c.drawString(145, height-75, f"tourism2020-hotrigo | {datetime.now().strftime('%d-%m-%Y')}")
        except:
            c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold", 26)
            c.drawString(30, height-60, "HOTRIGO - BOOKING VOUCHER")
    else:
        c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold", 26)
        c.drawString(30, height-60, "HOTRIGO - BOOKING VOUCHER")
    c.setFillColorRGB(0,0,0); y = height-HEADER_H-30
    c.setFillColorRGB(0.96,0.96,0.96); c.rect(30, y-45, width-60, 45, fill=1, stroke=0)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y-10, f"Booking Date: {data.get('sale_date','')}")
    c.drawString(40, y-30, f"Booking No: {data.get('booking_no','')}"); y -= 75
    c.setFont("Helvetica-Bold", 13); c.drawString(30, y, "Guest Names:"); y -= 20
    c.setFont("Helvetica", 12)
    for idx, name in enumerate(str(data.get('passengers','')).strip().split('\n'), 1):
        if name.strip(): c.drawString(40, y, f"{idx}. {name.strip()}"); y -= 18
    y -= 15; c.line(30, y, width-30, y); y -= 25
    c.setFont("Helvetica-Bold", 12); c.drawString(30, y, "Hotel Details:"); y -= 22
    c.setFont("Helvetica", 11)
    rc = data.get('room_count',1)
    c.drawString(40, y, f"Hotel: {data.get('hotel','')} - Rooms: {rc}"); y -= 18
    c.drawString(40, y, f"Room Type: {data.get('room_type','')}"); y -= 18
    c.drawString(40, y, f"Check-in: {data.get('entry_date','')} | Check-out: {data.get('exit_date','')} | Nights: {data.get('nights','')}")
    y -= 30
    notes = data.get('notes','') or ''
    if notes.strip():
        c.setFont("Helvetica-Bold", 11); c.drawString(30, y, "Note:"); y-=18; c.setFont("Helvetica", 11)
        for line in notes.split('\n'):
            if line.strip(): c.drawString(40, y, line.strip()[:100]); y-=18
    c.showPage(); c.save()
    pdf_bytes=buffer.getvalue(); buffer.close()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f: f.write(pdf_bytes)
        upload_drive(save_path)
    return pdf_bytes

def generate_agent_statement_excel(agent_name, bookings_df, payments_df):
    import io
    buffer = io.BytesIO()
    try: import openpyxl
    except: 
        import os
        os.system("pip install openpyxl")
        import openpyxl
    from datetime import datetime
    import pandas as pd

    def _parse_date(d):
        if not d or pd.isna(d): return None
        for fmt in ("%Y-%m-%d","%d/%m/%Y","%d-%m-%Y","%Y/%m/%d"):
            try: return datetime.strptime(str(d).strip(), fmt)
            except: pass
        return None

    def _first_pax(pas):
        if not pas or pd.isna(pas): return ""
        s = str(pas).replace('\r','\n').strip()
        lines = [x.strip() for x in s.split('\n') if x.strip()]
        return lines[0].split(',')[0].strip() if lines else ""

    def _count_pax(pas):
        if not pas or pd.isna(pas): return 0
        s = str(pas).replace('\r','\n').strip()
        lines = [x.strip() for x in s.split('\n') if x.strip()]
        if len(lines) > 1: return len(lines)
        if ',' in s: return len([x for x in s.split(',') if x.strip()])
        return 1 if s else 0

    total_sales = bookings_df['sell'].sum() if not bookings_df.empty and 'sell' in bookings_df.columns else 0
    total_payments = payments_df['amount'].sum() if not payments_df.empty and 'amount' in payments_df.columns else 0
    balance = total_sales - total_payments

    data = []
    if not bookings_df.empty:
        for _, r in bookings_df.iterrows():
            ent = _parse_date(r.get('entry_date'))
            ex = _parse_date(r.get('exit_date'))
            nights = (ex - ent).days if ent and ex else ""
            data.append({
                'رقم الحجز': r.get('id',''),
                'اسم الوكيل': r.get('company', agent_name),
                'اسم اول مسافر': _first_pax(r.get('passengers','')),
                'عدد الاشخاص': _count_pax(r.get('passengers','')),
                'الفندق': r.get('hotel',''),
                'نوع الغرف': r.get('room_type',''),
                'عدد الغرف': r.get('room_count',''),
                'تاريخ الدخول': r.get('entry_date',''),
                'الليالي': nights,
                'تاريخ الخروج': r.get('exit_date',''),
                'سعر المبيع': r.get('sell',''),
                'الملاحظة': r.get('notes',''),
            })
        book_export = pd.DataFrame(data)
    else:
        book_export = pd.DataFrame()

    if not payments_df.empty:
        cols_exist = [c for c in ['pay_date','amount','note'] if c in payments_df.columns]
        pay_export = payments_df[cols_exist].copy()
        rename_map = {'pay_date':'تاريخ الدفعة','amount':'قيمة الدفعة','note':'ملاحظة الدفعة'}
        pay_export.rename(columns={k:v for k,v in rename_map.items() if k in pay_export.columns}, inplace=True)
    else:
        pay_export = pd.DataFrame()

    summary_df = pd.DataFrame([{'الوكيل': agent_name, 'اجمالي الحجوزات': total_sales, 'اجمالي الدفعات': total_payments, 'الرصيد المتبقي': balance}])

    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        if not book_export.empty:
            book_export.to_excel(writer, sheet_name='الحجوزات', index=False)
        else:
            pd.DataFrame([{'ملاحظة':'لا يوجد حجوزات'}]).to_excel(writer, sheet_name='الحجوزات', index=False)
        if not pay_export.empty:
            pay_export.to_excel(writer, sheet_name='الدفعات', index=False)
        else:
            pd.DataFrame([{'ملاحظة':'لا يوجد دفعات'}]).to_excel(writer, sheet_name='الدفعات', index=False)
        summary_df.to_excel(writer, sheet_name='الملخص', index=False)

    buffer.seek(0)
    return buffer.getvalue(), total_sales, total_payments, balance

def generate_agent_statement_pdf(agent_name, bookings_df, payments_df):
    buffer = io.BytesIO()
    pagesize_land = landscape(A4)
    c = canvas.Canvas(buffer, pagesize=pagesize_land)
    width, height = pagesize_land
    HEADER_H = 95

    total_sales = float(bookings_df['sell'].sum()) if 'sell' in bookings_df and not bookings_df.empty else 0
    total_payments = float(payments_df['amount'].sum()) if not payments_df.empty and 'amount' in payments_df else 0
    balance = total_sales - total_payments

    c.setFillColorRGB(0.06, 0.18, 0.36); c.rect(0, height-HEADER_H, width, HEADER_H, fill=1, stroke=0)
    c.setFillColorRGB(1, 0.55, 0); c.rect(0, height-HEADER_H-5, width, 5, fill=1, stroke=0)
    has_logo = os.path.exists(LOGO_PATH)
    if has_logo:
        try: c.drawImage(LOGO_PATH, 25, height-88, width=80, height=75, preserveAspectRatio=True, mask='auto')
        except: pass
    c.setFillColorRGB(1,1,1); c.setFont("Helvetica-Bold", 20)
    c.drawString(120 if has_logo else 30, height-38, f"AGENT STATEMENT - {agent_name}")
    c.setFont("Helvetica", 10)
    c.drawString(120 if has_logo else 30, height-58, f"Date: {datetime.now().strftime('%d/%m/%Y')} | {len(bookings_df)} bookings | tourism2020-hotrigo")
    c.setFillColorRGB(0,0,0); y = height-HEADER_H-25
    c.setFont("Helvetica-Bold", 11); c.drawString(30, y, f"Agent: {agent_name}"); y-=25

    # ===== فوق - مربع كبير =====
    c.setFillColorRGB(1, 0.95, 0.85); c.rect(30, y-50, width-60, 50, fill=1, stroke=0)
    c.setStrokeColorRGB(0.8,0,0); c.setLineWidth(1); c.rect(30, y-50, width-60, 50, fill=0, stroke=1)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y-15, f"Total Sales: ${total_sales:.2f} | Total Payments: ${total_payments:.2f} | Balance: ${balance:.2f}")
    c.setFillColorRGB(0.8,0,0) if balance>0 else c.setFillColorRGB(0,0.5,0)
    c.setFont("Helvetica-Bold", 16); c.drawString(40, y-38, f"REMAINING BALANCE: ${balance:.2f}")
    c.setFillColorRGB(0,0,0)
    y -= 75

    left = 30; right = width - 30; usable = right - left
    col_book = left + 5; col_pass = left + 75; col_rooms = left + 195; col_type = left + 235; col_checkin = left + 290; col_checkout = left + 375; col_sell = left + 465; col_note = left + 530
    c.setFillColorRGB(0.9,0.9,0.9); c.rect(left, y-16, usable, 18, fill=1, stroke=0)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 9)
    c.drawString(col_book, y-12, "Booking No"); c.drawString(col_pass, y-12, "Passenger"); c.drawString(col_rooms, y-12, "Rooms"); c.drawString(col_type, y-12, "Type"); c.drawString(col_checkin, y-12, "Check-in"); c.drawString(col_checkout, y-12, "Check-out"); c.drawString(col_sell, y-12, "Sell"); c.drawString(col_note, y-12, "Note")
    y-=32; c.setFont("Helvetica", 9)
    for _, row in bookings_df.iterrows():
        if y < 150:
            c.showPage(); y = height-40; c.setFont("Helvetica-Bold", 9)
            c.setFillColorRGB(0.9,0.9,0.9); c.rect(left, y-16, usable, 18, fill=1, stroke=0)
            c.setFillColorRGB(0,0,0); c.drawString(col_book, y-12, "Booking No"); c.drawString(col_pass, y-12, "Passenger"); c.drawString(col_rooms, y-12, "Rooms"); c.drawString(col_type, y-12, "Type"); c.drawString(col_checkin, y-12, "Check-in"); c.drawString(col_checkout, y-12, "Check-out"); c.drawString(col_sell, y-12, "Sell"); c.drawString(col_note, y-12, "Note")
            y-=32; c.setFont("Helvetica", 9)
        bno = str(row['booking_no']) if 'booking_no' in row and pd.notna(row['booking_no']) and str(row['booking_no']).strip()!="" else f"HTG-{int(row['id']):06d}" if 'id' in row and pd.notna(row['id']) else ""
        pas = str(row['passengers']).split('\n')[0][:20] if 'passengers' in row and pd.notna(row['passengers']) else ""
        rc = str(row['room_count']) if 'room_count' in row and pd.notna(row['room_count']) else "1"
        rtype = str(row['room_type'])[:10] if 'room_type' in row and pd.notna(row['room_type']) else ""
        entry = str(row['entry_date'])[:10] if 'entry_date' in row else ""
        exit_d = str(row['exit_date'])[:10] if 'exit_date' in row else ""
        sell = float(row['sell']) if 'sell' in row and pd.notna(row['sell']) else 0
        note = str(row['notes'])[:18] if 'notes' in row and pd.notna(row['notes']) else ""
        c.drawString(col_book, y, bno[:12]); c.drawString(col_pass, y, pas); c.drawString(col_rooms, y, rc); c.drawString(col_type, y, rtype); c.drawString(col_checkin, y, entry); c.drawString(col_checkout, y, exit_d); c.drawString(col_sell, y, f"{sell:.0f}"); c.drawString(col_note, y, note)
        y-=12; c.line(left, y, right, y); y-=22
    y-=12; c.line(left, y, right, y); y-=22; c.setFont("Helvetica-Bold", 11); c.drawString(left, y, "Payments:"); y-=20
    c.setFillColorRGB(0.9,0.9,0.9); c.rect(left, y-16, usable, 18, fill=1, stroke=0); c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 9)
    c.drawString(left+5, y-12, "Pay Date"); c.drawString(left+125, y-12, "Amount"); c.drawString(left+300, y-12, "Note")
    y-=32; c.setFont("Helvetica", 9)
    if not payments_df.empty:
        for _, p in payments_df.iterrows():
            if y < 140: c.showPage(); y = height-40; c.setFont("Helvetica", 9)
            pd_date = str(p['pay_date'])[:10]; amt = float(p['amount']) if p['amount'] else 0
            c.drawString(left+5, y, pd_date); c.drawString(left+125, y, f"${amt:.2f}"); c.drawString(left+300, y, str(p['note'])[:40] if pd.notna(p['note']) else "")
            y-=12; c.line(left, y, right, y); y-=16
    else: c.drawString(left+5, y, "No payments yet"); y-=16

    # ===== تحت - مربع كبير =====
    y-=20; c.line(left, y, right, y); y-=40
    if y < 90: c.showPage(); y = height-60
    c.setFillColorRGB(1, 0.95, 0.85); c.rect(30, y-50, width-60, 50, fill=1, stroke=0)
    c.setStrokeColorRGB(0.8,0,0); c.setLineWidth(1); c.rect(30, y-50, width-60, 50, fill=0, stroke=1)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y-15, f"Total Sales: ${total_sales:.2f} | Total Payments: ${total_payments:.2f} | Balance: ${balance:.2f}")
    c.setFillColorRGB(0.8,0,0) if balance>0 else c.setFillColorRGB(0,0.5,0)
    c.setFont("Helvetica-Bold", 16); c.drawString(40, y-38, f"REMAINING BALANCE: ${balance:.2f}")

    c.showPage(); c.save()
    pdf_bytes=buffer.getvalue(); buffer.close()
    return pdf_bytes, total_sales, total_payments, balance

st.set_page_config(page_title="hotrigo", page_icon="✈️", layout="wide")

# --- DB اللوكال ملغي - تحميل القوائم من الشيت مباشر ---
agents_for_js = []
hotels_for_js = []
airlines_for_js = []
transport_for_js = []
try:
    _sheet_js = get_gspread_sheet()
    if _sheet_js:
        _all = _sheet_js.get_all_values()
        if len(_all) > 1:
            for _r in _all[1:]:
                try:
                    if len(_r) > 3 and _r[3].strip(): agents_for_js.append(_r[3].strip())
                    if len(_r) > 6 and _r[6].strip(): hotels_for_js.append(_r[6].strip())
                    if len(_r) > 18 and _r[18].strip(): airlines_for_js.append(_r[18].strip())
                    if len(_r) > 22 and _r[22].strip(): transport_for_js.append(_r[22].strip())
                except:
                    continue
            agents_for_js = sorted(list(set(agents_for_js)))
            hotels_for_js = sorted(list(set(hotels_for_js)))
            airlines_for_js = sorted(list(set(airlines_for_js)))
            transport_for_js = sorted(list(set(transport_for_js)))
except:
    pass

agents_upper=[a.upper() for a in agents_for_js]
hotels_upper=[h.upper() for h in hotels_for_js]
airlines_upper=[a.upper() for a in airlines_for_js]
transport_upper=[a.upper() for a in transport_for_js]

js_template = """
<script>
const doc = window.parent.document;
const AGENTS = __AGENTS__;
const HOTELS = __HOTELS__;
const AIRLINES = __AIRLINES__;
const TRANSPORT = __TRANSPORT__;
function isSearchField(input){if(!input) return false; const ph=(input.getAttribute('placeholder')||'').toLowerCase(); const cont=input.closest('div[data-testid="stTextInput"], div[data-testid="stTextArea"]'); const txt=cont?(cont.innerText||'').toLowerCase():''; return ph.includes('search')||txt.includes('search');}
function killAutofill(){doc.querySelectorAll('div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stNumberInput"] input').forEach(inp=>{if(isSearchField(inp)) return; if(inp.type==='hidden') return; inp.setAttribute('autocomplete','off'); inp.removeAttribute('list');}); doc.querySelectorAll('datalist').forEach(d=>d.remove());}
killAutofill(); setTimeout(killAutofill,200); setInterval(killAutofill,1500);
function isCalendarOpen(){return doc.querySelector('div[data-baseweb="calendar"], div[data-baseweb="datepicker"]')!== null;}
function getActiveContainer(){const dlg=doc.querySelector('div[data-testid="stDialog"], div[role="dialog"]'); if(dlg&&dlg.offsetParent!==null&&dlg.querySelector('input, textarea')){return dlg;} return doc;}
function getFieldType(input){if(isSearchField(input)) return 'SEARCH'; const cont=input.closest('div[data-testid="stTextInput"], div[data-testid="stTextArea"], div[data-testid="stDateInput"], div[data-testid="stNumberInput"]'); if(!cont) return null; const testId=cont.getAttribute('data-testid')||''; if(testId.includes('stDateInput')) return 'DATE'; if(testId.includes('stNumberInput')) return 'NUMBER'; const txt=(cont.innerText||'').toLowerCase(); if(txt.includes('agent')) return 'AGENT'; if(txt.includes('hotel')) return 'HOTEL'; if(txt.includes('airline')) return 'AIRLINE'; if(txt.includes('transport')) return 'TRANSPORT'; if(txt.includes('passengers')) return 'PASSENGERS'; if(txt.includes('room type')) return 'ROOM'; return 'OTHER';}
function getFields(){const container=getActiveContainer(); const els=Array.from(container.querySelectorAll('input:not([type=hidden]), textarea')); return els.filter(e=>e.offsetParent!==null&&!e.disabled&&e.type!=='checkbox'&&e.type!=='radio'&&e.getClientRects().length>0);}
function setNativeValue(input,value){const lastValue=input.value; input.value=value; if(input._valueTracker)input._valueTracker.setValue(lastValue); try{const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input),'value').set; setter.call(input,value);}catch(e){} input.dispatchEvent(new Event('input',{bubbles:true})); input.dispatchEvent(new Event('change',{bubbles:true})); if(getFieldType(input)!=='PASSENGERS'){setTimeout(()=>{input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));},20);}}
function insertNewLinePassengers(textarea){const start=textarea.selectionStart; const end=textarea.selectionEnd; const text=textarea.value; const newText=text.substring(0,start)+"\\n"+text.substring(end); const newPos=start+1; const lastValue=textarea.value; textarea.value=newText; if(textarea._valueTracker)textarea._valueTracker.setValue(lastValue); try{const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(textarea),'value').set; setter.call(textarea,newText);}catch(e){} textarea.dispatchEvent(new Event('input',{bubbles:true})); textarea.dispatchEvent(new Event('change',{bubbles:true})); textarea.selectionStart=textarea.selectionEnd=newPos; textarea.focus();}
function findNearest(active,dir){const fields=getFields(); const ar=active.getBoundingClientRect(); const acx=ar.left+ar.width/2; const acy=ar.top+ar.height/2; let candidates=[]; for(let f of fields){if(f===active)continue; const r=f.getBoundingClientRect(); const cx=r.left+r.width/2; const cy=r.top+r.height/2; if(dir==='left'&&r.left<ar.left-5){candidates.push({f,dist:acx-cx,cy:Math.abs(acy-cy)});} if(dir==='right'&&r.left>ar.right+5){candidates.push({f,dist:cx-acx,cy:Math.abs(acy-cy)});} if(dir==='down'&&r.top>ar.top+5){candidates.push({f,dist:cy-acy,cx:Math.abs(acx-cx)});} if(dir==='up'&&r.bottom<ar.bottom-5){candidates.push({f,dist:acy-cy,cx:Math.abs(acx-cx)});}} if(!candidates.length) return null; if(dir==='left'||dir==='right'){candidates.sort((a,b)=>{if(Math.abs(a.cy-b.cy)>20) return a.cy-b.cy; return a.dist-b.dist;});} else {candidates.sort((a,b)=>{if(Math.abs(a.cx-b.cx)>80) return a.cx-b.cx; return a.dist-b.dist;});} return candidates[0].f;}
function moveToNext(input){const fields=getFields(); let idx=fields.indexOf(input); if(idx!==-1&&idx+1<fields.length){setTimeout(()=>{const n=fields[idx+1]; if(n){n.focus(); try{n.select();}catch(e){}}},60);}}
function moveToPrev(input){const fields=getFields(); let idx=fields.indexOf(input); if(idx>0){setTimeout(()=>{const p=fields[idx-1]; if(p){p.focus(); try{p.select();}catch(e){}}},60);}}
let activeList=null; let activeIndex=0; let currentInput=null;
function closeList(){if(activeList){activeList.remove(); activeList=null; activeIndex=0; currentInput=null;}}
function highlightActive(){if(!activeList) return; Array.from(activeList.children).forEach((ch,i)=>{ch.style.background=i===activeIndex?'#1976d2':'white'; ch.style.color=i===activeIndex?'white':'black';});}
function createList(input,items){closeList(); if(!items.length)return; currentInput=input; activeIndex=0; const rect=input.getBoundingClientRect(); const div=doc.createElement('div'); div.style.position='fixed'; div.style.left=rect.left+'px'; div.style.top=(rect.bottom+2)+'px'; div.style.width=rect.width+'px'; div.style.maxHeight='220px'; div.style.overflowY='auto'; div.style.background='white'; div.style.border='1px solid #ccc'; div.style.borderRadius='6px'; div.style.boxShadow='0 4px 12px rgba(0,0,0,0.3)'; div.style.zIndex='9999999999'; items.forEach((txt,i)=>{const item=doc.createElement('div'); item.textContent=txt; item.style.padding='12px'; item.style.cursor='pointer'; item.style.background=i===0?'#1976d2':'white'; item.style.color=i===0?'white':'black'; item.style.fontWeight='bold'; item.style.borderBottom='1px solid #eee'; item.addEventListener('mousedown',(e)=>{e.preventDefault(); e.stopPropagation(); setNativeValue(input,txt); closeList(); moveToNext(input);}); div.appendChild(item);}); doc.body.appendChild(div); activeList=div;}
doc.addEventListener('input',function(e){const input=e.target; if(!input||input.tagName!=='INPUT')return; if(isSearchField(input)) return; const type=getFieldType(input); if(type!=='AGENT'&&type!=='HOTEL'&&type!=='AIRLINE'&&type!=='TRANSPORT') return; const val=input.value.trim().toUpperCase(); if(val.length<1||val==="0"){closeList(); return;} let list=type==='AGENT'?AGENTS:type==='HOTEL'?HOTELS:type==='AIRLINE'?AIRLINES:TRANSPORT; if(!list||!list.length) return; let filtered=list.filter(x=>x.toUpperCase().startsWith(val)).slice(0,8); if(filtered.length)createList(input,filtered); else closeList();});
doc.addEventListener('keydown',function(e){const active=doc.activeElement; if(!active||(active.tagName!=='INPUT'&&active.tagName!=='TEXTAREA')) return; if(isSearchField(active)) return; if(isCalendarOpen()){if(['ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Enter','Escape'].includes(e.key)) return;} const type=getFieldType(active); const isAgentOrHotel=(type==='AGENT'||type==='HOTEL'); if(type==='PASSENGERS'){if(e.key==='Enter'){e.preventDefault(); e.stopPropagation(); insertNewLinePassengers(active); return;} if(e.key==='ArrowDown'||e.key==='ArrowRight'){e.preventDefault(); e.stopPropagation(); closeList(); const next=findNearest(active,e.key==='ArrowDown'?'down':'right'); if(next){next.focus(); try{next.select();}catch(e){}} else {moveToNext(active);} return;} if(e.key==='ArrowUp'||e.key==='ArrowLeft'){e.preventDefault(); e.stopPropagation(); closeList(); const prev=findNearest(active,e.key==='ArrowUp'?'up':'left'); if(prev){prev.focus();} else {moveToPrev(active);} return;} if(e.key==='Escape'){closeList(); return;} return;} if(isAgentOrHotel&&activeList&&currentInput===active){if(e.key==='Enter'){e.preventDefault(); e.stopPropagation(); const chosen=activeList.children[activeIndex]?.textContent||activeList.children[0]?.textContent; if(chosen){setNativeValue(active,chosen);} closeList(); setTimeout(()=>{moveToNext(active);},100); return;} if(e.key==='ArrowDown'){if(activeList){e.preventDefault(); if(activeIndex<activeList.children.length-1){activeIndex++; highlightActive();} return;}} if(e.key==='ArrowUp'){if(activeList){e.preventDefault(); if(activeIndex>0){activeIndex--; highlightActive();} return;}} if(e.key==='Escape'){closeList(); return;}} if(e.key==='Enter'){e.preventDefault(); closeList(); moveToNext(active); return;} if(e.key==='ArrowRight'){e.preventDefault(); closeList(); const t=findNearest(active,'right'); if(t){t.focus(); try{t.select();}catch(e){}} else {moveToNext(active);} return;} if(e.key==='ArrowLeft'){e.preventDefault(); closeList(); const t=findNearest(active,'left'); if(t){t.focus(); try{t.select();}catch(e){}} else {moveToPrev(active);} return;} if(e.key==='ArrowDown'){e.preventDefault(); closeList(); const t=findNearest(active,'down'); if(t){t.focus(); try{t.select();}catch(e){}} else {moveToNext(active);} return;} if(e.key==='ArrowUp'){e.preventDefault(); closeList(); const t=findNearest(active,'up'); if(t){t.focus(); try{t.select();}catch(e){}} else {moveToPrev(active);} return;}},true);
doc.addEventListener('click',(e)=>{if(activeList&&!activeList.contains(e.target)&&e.target!==currentInput)closeList();});
</script>
"""
js_code = js_template.replace("__AGENTS__", json.dumps(agents_for_js)).replace("__HOTELS__", json.dumps(hotels_for_js)).replace("__AIRLINES__", json.dumps(airlines_for_js)).replace("__TRANSPORT__", json.dumps(transport_for_js))
components.html(js_code, height=0)

@st.dialog("Edit Booking")
def edit_dialog(row):
    import streamlit.components.v1 as components
    sheet = get_gspread_sheet()
    if not sheet:
        st.error("Sheet not connected")
        return

    try:
        if isinstance(row, int):
            row_idx = row
        elif isinstance(row, (list, tuple)) and len(row)>0 and str(row[0]).isdigit():
            row_idx = int(row[0])
        else:
            row_idx = int(row)
        if row_idx < 2: row_idx = 2
    except:
        row_idx = 2

    try:
        all_vals = sheet.get_all_values()
        header = all_vals[0]
        if row_idx > len(all_vals):
            st.error("Booking not found in Sheet")
            return
        d_row = all_vals[row_idx-1]
        d = {}
        for i, h in enumerate(header):
            d[h] = d_row[i] if i < len(d_row) else ""
        d['id'] = row_idx
        if 'company' not in d and 'Company' in d: d['company'] = d['Company']
    except Exception as e:
        st.error(f"Booking not found: {e}")
        return

    def gv(k, default=""):
        v = d.get(k, default)
        return "" if v is None else str(v)

    st.info(f"Editing booking #{d.get('id')} - {gv('company')}")

    c1, c2 = st.columns(2)
    with c1: e_sale = st.text_input("Sale Date", value=gv("sale_date"), key="dlg_sale")
    with c2: e_entry = st.text_input("Entry Date", value=gv("entry_date"), key="dlg_en")

    c3, c4 = st.columns(2)
    with c3: e_exit = st.text_input("Exit Date", value=gv("exit_date"), key="dlg_ex")
    with c4: e_comp = st.text_input("Agent *", value=gv("company"), key="dlg_comp")

    e_pas = st.text_area("Passengers", value=gv("passengers"), height=130, key="dlg_pas")

    c5, c6 = st.columns(2)
    with c5: e_room = st.text_input("Room Type", value=gv("room_type"), key="dlg_room")
    with c6:
        cur_rc = gv("room_count")
        init_val = "" if cur_rc in ["0", "1", "None", ""] else cur_rc
        if cur_rc == "1": init_val = ""
        e_rc_text = st.text_input("Number of Rooms", value=init_val, placeholder="Empty = 0", key="dlg_rc")

    c7, c8 = st.columns(2)
    with c7:
        current_hotel = gv("hotel")
        if 'hotels_for_js' in globals() and hotels_for_js:
            idx = hotels_for_js.index(current_hotel) if current_hotel in hotels_for_js else 0
            e_hotel = st.selectbox("Hotel *", hotels_for_js, index=idx, key="dlg_hotel")
        else:
            e_hotel = st.text_input("Hotel *", value=current_hotel, key="dlg_hotel")
    with c8: e_emp = st.text_input("Employee", value=gv("emp"), key="dlg_emp")

    c_price, c_flight = st.columns(2)
    with c_price: e_pn = st.text_input("Price per Night $", value=gv("price_per_night"), key="dlg_pn")
    with c_flight: e_fl = st.text_input("Flight $", value=gv("flight_cost"), key="dlg_fl")

    c_trans, c_sell = st.columns(2)
    with c_trans: e_tr = st.text_input("Transport $", value=gv("transport_cost"), key="dlg_tr")
    with c_sell: e_sell = st.text_input("Selling Price $ *", value=gv("sell"), key="dlg_sell")

    e_notes = st.text_input("Note", value=gv("notes"), key="dlg_notes")

    c_air, c_vno = st.columns(2)
    with c_air: e_air = st.text_input("Airline (empty=no flight)", value=gv("airline"), key="dlg_air")
    with c_vno: e_vno = st.text_input("Voucher No", value=gv("voucher_no"), key="dlg_vno")

    c_dep, c_ret = st.columns(2)
    with c_dep: e_dep = st.text_input("Departure Time", value=gv("flight_dep_time"), placeholder="10:30", key="dlg_dep")
    with c_ret: e_ret = st.text_input("Return Time", value=gv("flight_ret_time"), placeholder="18:45", key="dlg_ret")

    c_fno_dep, c_fno_ret = st.columns(2)
    with c_fno_dep: e_fno_dep = st.text_input("Flight No Dep", value=gv("flight_no_dep"), placeholder="TK2026", key="dlg_fno_dep")
    with c_fno_ret: e_fno_ret = st.text_input("Flight No Ret", value=gv("flight_no_ret"), placeholder="TK2027", key="dlg_fno_ret")

    c_air_dep, c_air_ret = st.columns(2)
    with c_air_dep: e_dep_air = st.text_input("Departure Airport", value=gv("dep_airport"), placeholder="IST", key="dlg_dep_air")
    with c_air_ret: e_ret_air = st.text_input("Return Airport", value=gv("ret_airport"), placeholder="BEY", key="dlg_ret_air")

    e_trans_co = st.text_input("Transport Company (empty=no transfer)", value=gv("transport_company"), key="dlg_transco")

    components.html("""
    <script>
    const doc = window.parent.document;
    if(doc._editBookingNavHandler){
        doc.removeEventListener('keydown', doc._editBookingNavHandler, true);
    }
    function getFields(){
        const dlg = doc.querySelector('div[data-testid="stDialog"]');
        if(!dlg) return [];
        const list=[];
        dlg.querySelectorAll('[data-testid="stTextInput"], [data-testid="stTextArea"], [data-testid="stSelectbox"]').forEach(w=>{
            let el = w.dataset.testid==='stSelectbox' ? w.querySelector('div[role="combobox"]') : w.querySelector('input, textarea');
            if(el) list.push(el);
        });
        return list;
    }
    const GRID = [
        [0,1], [2,3], [4], [5,6], [7,8], [9,10], [11,12], [13], [14,15], [16,17], [18,19], [20,21], [22]
    ];
    function findPos(idx){
        for(let r=0;r<GRID.length;r++){
            let c=GRID[r].indexOf(idx);
            if(c!==-1) return {r,c};
        }
        return null;
    }
    const handler = function(e){
        if(!['ArrowRight','ArrowLeft','ArrowDown','ArrowUp','Enter'].includes(e.key)) return;
        const dlg = doc.querySelector('div[data-testid="stDialog"]');
        if(!dlg || !dlg.contains(doc.activeElement)) return;
        const fields=getFields();
        if(fields.length<23) return;
        let curIdx=-1;
        for(let i=0;i<fields.length;i++){
            if(fields[i]===doc.activeElement || fields[i].contains(doc.activeElement) || doc.activeElement.contains(fields[i])){curIdx=i; break;}
        }
        if(curIdx===-1) return;
        const active = doc.activeElement;
        const isArea = active.tagName==='TEXTAREA';
        if(isArea){
            const start = active.selectionStart;
            const end = active.selectionEnd;
            const val = active.value;
            const before = val.substring(0, start);
            const after = val.substring(end);
            if(e.key==='ArrowUp' && before.includes('\\n')) return;
            if(e.key==='ArrowDown' && after.includes('\\n')) return;
            if(e.key==='ArrowLeft' && start>0) return;
            if(e.key==='ArrowRight' && end < val.length) return;
            if(e.key==='Enter' && !e.ctrlKey) return;
        } else {
            if(e.key==='ArrowRight' && active.selectionStart < active.value.length) return;
            if(e.key==='ArrowLeft' && active.selectionStart > 0) return;
        }
        const pos=findPos(curIdx);
        if(!pos) return;
        let target=null;
        if(e.key==='ArrowRight'){
            let row=GRID[pos.r];
            if(pos.c+1<row.length) target=row[pos.c+1];
        } else if(e.key==='ArrowLeft'){
            let row=GRID[pos.r];
            if(pos.c-1>=0) target=row[pos.c-1];
        } else if(e.key==='ArrowDown' || (e.key==='Enter' && isArea)){
            for(let r=pos.r+1;r<GRID.length;r++){
                if(GRID[r][pos.c]!==undefined){target=GRID[r][pos.c]; break;}
                if(GRID[r].length===1){target=GRID[r][0]; break;}
            }
        } else if(e.key==='ArrowUp'){
            for(let r=pos.r-1;r>=0;r--){
                if(GRID[r][pos.c]!==undefined){target=GRID[r][pos.c]; break;}
                if(GRID[r].length===1){target=GRID[r][0]; break;}
            }
        } else if(e.key==='Enter'){
            let row=GRID[pos.r];
            if(pos.c+1<row.length) target=row[pos.c+1];
            else { for(let r=pos.r+1;r<GRID.length;r++){ if(GRID[r][0]!==undefined){target=GRID[r][0]; break;} } }
            if(target===null){
                const btn=doc.querySelector('div[data-testid="stDialog"] button[kind="primary"]');
                if(btn){ e.preventDefault(); btn.click(); return; }
            }
        }
        if(target!==null){
            e.preventDefault(); e.stopImmediatePropagation();
            const el=fields[target];
            if(el){ el.focus(); try{ el.select(); }catch(_){} }
        }
    };
    doc._editBookingNavHandler = handler;
    doc.addEventListener('keydown', handler, true);
    </script>
    """, height=0)

    if st.button("Save", type="primary", use_container_width=True):
        try:
            s = e_rc_text.strip()
            e_rc_final = 0 if s == "" else int(float(s))
        except: e_rc_final = 0
        
        # تحقق بسيط - لغينا smart_match المعقد اذا بدك ترجعو رجعو
        # comp_full, comp_ok = smart_match(e_comp, agents_for_js, agents_upper)
        # بس هلأ منحفظ مباشر
        comp_full = e_comp
        hotel_full = e_hotel
        air_full = e_air
        trans_full = e_trans_co

        # ابن الصف الجديد بنفس ترتيب الهيدر
        new_data = {
            'sale_date': e_sale,
            'company': comp_full,
            'passengers': e_pas,
            'room_type': e_room,
            'room_count': str(e_rc_final),
            'hotel': hotel_full,
            'entry_date': e_entry,
            'exit_date': e_exit,
            'price_per_night': e_pn,
            'flight_cost': e_fl,
            'transport_cost': e_tr,
            'sell': e_sell,
            'notes': e_notes,
            'voucher_no': e_vno,
            'airline': air_full,
            'emp': e_emp,
            'flight_dep_time': e_dep,
            'flight_ret_time': e_ret,
            'transport_company': trans_full,
            'flight_no_dep': e_fno_dep,
            'flight_no_ret': e_fno_ret,
            'dep_airport': e_dep_air,
            'ret_airport': e_ret_air,
        }
        
        # حدث القاموس d
        for k,v in new_data.items():
            d[k] = v
            # كمان حدث النسخ الكبيرة
            if k == 'company': d['Company'] = v
            if k == 'passengers': d['Passengers'] = v
            if k == 'hotel': d['Hotel'] = v

        new_row = []
        for h in header:
            # اذا الهيدر مطابق لمفتاح جديد
            val = d.get(h, "")
            # جرب المفتاح الصغير
            if val == "" and h.lower() in [x.lower() for x in new_data.keys()]:
                for nk,nv in new_data.items():
                    if nk.lower() == h.lower() or nk.replace('_',' ').lower() == h.lower():
                        val = nv
                        break
            new_row.append(str(val))

        try:
            with st.spinner("Updating Google Sheet..."):
                sheet.update(f"A{row_idx}:Z{row_idx}", [new_row], value_input_option="USER_ENTERED")
            st.success("✅ تم التحديث بالشيت!")
            st.session_state.table_version += 1
            import time; time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Error updating sheet: {e}")
@st.dialog("Invoice - معاينة الفاتورة", width="large")
def invoice_dialog(row):
    try:
        _sheet = get_gspread_sheet()
        ws = _sheet.spreadsheet.worksheet("Bookings")
        all_vals = ws.get_all_values()
        target_id = str(row[0]).strip()
        full = None
        for r in all_vals[1:]:
            if r and str(r[0]).strip() == target_id:
                full = r
                break
        if not full:
            return
        
        def g(i, d=""):
            return full[i] if len(full) > i else d

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
    except Exception as e:
        st.error(f"Error: {e}")

@st.dialog("Booking Voucher - معاينة الفاوتشر", width="large")
def voucher_dialog(row):
    try:
        _sheet = get_gspread_sheet()
        ws = _sheet.spreadsheet.worksheet("Bookings")
        all_vals = ws.get_all_values()
        target_id = str(row[0]).strip()
        full = None
        for r in all_vals[1:]:
            if r and str(r[0]).strip() == target_id:
                full = r
                break
        if not full:
            return

        def g(i, d=""):
            return full[i] if len(full) > i else d

        rc = g(25) if g(25) else 1
        booking_no = g(15).strip() if g(15).strip() != "" else f"HTG-{int(g(0) or 0):06d}"
        data={"sale_date":g(1),"booking_no":booking_no,"passengers":g(5),"hotel":g(6),"room_type":g(21) if g(21) else "","room_count":rc,"entry_date":g(2),"exit_date":g(3),"nights":g(7),"notes":g(16) if g(16) else "","sell":g(12)}
        filename=f"VOUCHER_{booking_no}_{sanitize_filename(data['passengers'])}.pdf"
        full_path=Path.home() / "Desktop" / "voucher" / filename
        pdf_bytes=generate_voucher_pdf(data, save_path=str(full_path))
        logo_b64 = get_logo_b64()
        logo_html = f"<img src='data:image/png;base64,{logo_b64}' style='width:110px;height:110px;object-fit:contain;background:white;border-radius:4px;padding:4px;margin-right:20px;'>" if logo_b64 else ""
        passengers_html = "".join([f"<div style='padding:5px 0; font-size:15px;'>- {p.strip()}</div>" for p in str(data['passengers']).split('\n') if p.strip()])
        notes_html = f"<div style='margin-top:14px; background:#fffbe6; border-left:4px solid #FF8C00; padding:12px 16px; border-radius:6px; font-size:14px;'><b>Note:</b><br>{data['notes'].replace(chr(10), '<br>') if data['notes'] else 'No notes'}</div>" if data['notes'] else ""
        html_preview = f"""
        <div style="background:white; border:1px solid #ddd; border-radius:12px; padding:20px; font-family:Arial; color:#222;">
            <div style="background:#0F2D5C; color:white; padding:12px 20px; border-radius:8px; margin:-20px -20px 20px -20px; display:flex; align-items:center; border-bottom:6px solid #FF8C00; height:135px;">
                {logo_html}<div><div style="font-size:26px; font-weight:bold;">HOTRIGO - BOOKING VOUCHER</div><div style="font-size:13px; margin-top:6px;">Booking No: {booking_no} | Date: {data['sale_date']}</div></div>
            </div>
            <div style="background:#f8f9fa; padding:14px 18px; border-radius:8px; margin-bottom:14px; line-height:26px; font-size:14px;"><b>Booking No:</b> {booking_no}<br><b>Hotel:</b> {data['hotel']} | <b>Room Type:</b> {data['room_type']} | <b>Rooms:</b> {data['room_count']}<br><b>Check-in:</b> {data['entry_date']} | <b>Check-out:</b> {data['exit_date']} | <b>Nights:</b> {data['nights']}</div>
            <div style="font-weight:bold; margin:12px 0 6px 0; font-size:15px;">Guest Names:</div>
            <div style="background:#fff; border:1px solid #eee; border-left:4px solid #0F2D5C; padding:12px 18px; border-radius:6px;">{passengers_html}</div>{notes_html}
        </div>
        """
        st.markdown(f"### 🧾 معاينة الفاوتشر - {booking_no} - {rc} Rooms")
        components.html(html_preview, height=700, scrolling=True)
        st.download_button("⬇️ تحميل / طباعة Voucher PDF", data=pdf_bytes, file_name=filename, mime="application/pdf", use_container_width=True, type="primary")
    except Exception as e:
        st.error(f"Error voucher: {e}")

@st.dialog("Agent Statement", width="large")
def agent_statement_dialog(agent_name):
    try:
        _sheet = get_gspread_sheet()
        spreadsheet = _sheet.spreadsheet
        
        # 1- Bookings من شيت Bookings
        try:
            b_ws = spreadsheet.worksheet("Bookings")
            b_vals = b_ws.get_all_records()
            bookings = pd.DataFrame(b_vals)
            # فلترة حسب الشركة
            if not bookings.empty and 'company' in bookings.columns:
                bookings = bookings[bookings['company'].astype(str).str.strip() == str(agent_name).strip()]
                if 'entry_date' in bookings.columns:
                    bookings = bookings.sort_values(by='entry_date')
            else:
                # fallback اذا get_all_records فشل بسبب هيدر
                bookings = pd.DataFrame()
        except Exception as e:
            bookings = pd.DataFrame()

        # 2- Payments من شيت Payments
        try:
            p_ws = spreadsheet.worksheet("Payments")
            p_vals = p_ws.get_all_records()
            payments = pd.DataFrame(p_vals)
            if not payments.empty:
                # العمود اسمو Agent Name في الكود الجديد
                col_name = 'Agent Name' if 'Agent Name' in payments.columns else 'agent' if 'agent' in payments.columns else payments.columns[1] if len(payments.columns)>1 else None
                if col_name:
                    payments = payments[payments[col_name].astype(str).str.strip() == str(agent_name).strip()]
                    date_col = 'Pay Date' if 'Pay Date' in payments.columns else 'pay_date'
                    if date_col in payments.columns:
                        payments = payments.sort_values(by=date_col, ascending=False)
        except Exception as e:
            payments = pd.DataFrame()

        if bookings.empty:
            st.warning(f"لا يوجد حجوزات للوكيل {agent_name}"); return
        
        pdf_bytes, total_sales, total_payments, balance = generate_agent_statement_pdf(agent_name, bookings, payments)
        excel_bytes, _, _, _ = generate_agent_statement_excel(agent_name, bookings, payments)
        filename_pdf = f"STATEMENT_{agent_name}_{datetime.now().strftime('%Y%m%d')}.pdf"
        full_path_pdf = Path.home() / "Desktop" / "statements" / filename_pdf
        os.makedirs(os.path.dirname(full_path_pdf), exist_ok=True)
        with open(full_path_pdf, "wb") as f: f.write(pdf_bytes)
        try:
            upload_drive(str(full_path_pdf))
        except:
            pass

        st.markdown(f"### كشف حساب: {agent_name} - المبيعات ${total_sales:,.2f} - المدفوع ${total_payments:,.2f} - الباقي ${balance:,.2f}")
        
        st.download_button("📄 تحميل PDF", data=pdf_bytes, file_name=filename_pdf, mime="application/pdf", use_container_width=True, type="primary", key=f"dl_stmt_{agent_name}")

        import base64
        b64 = base64.b64encode(pdf_bytes).decode()
        st.markdown(f'<iframe src="data:application/pdf;base64,{b64}#toolbar=0" width="100%" height="700px" style="border:none;"></iframe>', unsafe_allow_html=True)
    except Exception as e:
        st.error(f"Error statement: {e}")

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

        # للكروبات الكبيرة - تحميل اكسل
        if pax_num > 20:
            st.warning(f"Group of {pax_num} detected - Please upload Excel")
            up_file = st.file_uploader("Upload Passenger List Excel", type=["xlsx","xls","csv"], key="up_pas")
            if up_file is not None:
                try:
                    import pandas as pd
                    if up_file.name.endswith(".csv"):
                        df = pd.read_csv(up_file)
                    else:
                        df = pd.read_excel(up_file)
                    # ناخد اول عمود فيه الاسماء
                    col = df.columns[0]
                    passenger_list = df[col].astype(str).tolist()
                    st.success(f"Loaded {len(passenger_list)} names from Excel")
                    for n in passenger_list[:5]:
                        st.caption(f"- {n}")
                    if len(passenger_list) > 5:
                        st.caption(f"... and {len(passenger_list)-5} more")
                except Exception as e:
                    st.error(f"Error reading file: {e}")
            else:
                st.info("Excel should have one column with passenger names")
                passenger_list = []
        else:
            # للعدد القليل - خانات عادية
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
            elif not comp_ok: st.error(f"❌ Agent '{comp}' not found!")
            elif not hotel_ok: st.error(f"❌ Hotel '{hotel}' not found!")
            elif not airline_ok: st.error(f"❌ Airline '{airline}' not found!")
            elif not transport_ok: st.error(f"❌ Transport '{transport_co}' not found!")
            else:
                ht_tot=to_f(pn)*to_f(nights)*to_f(room_count)
                cost=ht_tot+to_f(fl)+to_f(tr)
                profit=to_f(sell)-cost
                st.session_state["pending"]={"sale_date":str(sd),"entry_date":str(ed),"exit_date":str(xd),"company":comp_full,"passengers":pas.strip(),"hotel":hotel_full,"room_type":room_type.strip(),"room_count":int(to_f(room_count)),"nights":int(to_f(nights)),"price_night":float(to_f(pn)),"hotel_total":float(ht_tot),"flight":float(to_f(fl)),"transport":float(to_f(tr)),"sell":float(to_f(sell)),"cost":float(cost),"profit":float(profit),"voucher":vno,"notes":notes,"airline":airline_full,"emp":emp.strip(),"dep":dep_time.strip(),"ret":ret_time.strip(),"transport_company":transport_full,"fno_dep":flight_no_dep.strip(),"fno_ret":flight_no_ret.strip()}

        if st.session_state.get("pending"):
            d=st.session_state["pending"]
            st.warning(f"✅ {d['company']} - {d['passengers'].split(chr(10))[0]} | {d['room_count']} Rooms | Sell ${d['sell']:.2f}")
            c1,c2=st.columns(2)
            with c1:
                if st.button("YES", type="primary", use_container_width=True):
                    conn=sqlite3.connect(DB, check_same_thread=False)
                    cur=conn.cursor()
                    cur.execute("INSERT INTO bookings (sale_date,entry_date,exit_date,company,passengers,hotel,nights,price_night,hotel_total,flight,transport,sell,cost,profit,voucher,notes,airline,emp,flight_dep_time,flight_ret_time,room_type,transport_company,flight_no_dep,flight_no_ret,room_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (d["sale_date"],d["entry_date"],d["exit_date"],d["company"],d["passengers"],d["hotel"],d["nights"],d["price_night"],d["hotel_total"],d["flight"],d["transport"],d["sell"],d["cost"],d["profit"],d["voucher"],d["notes"],d["airline"],d["emp"],d["dep"],d["ret"],d["room_type"],d["transport_company"],d["fno_dep"],d["fno_ret"],d["room_count"]))
                    new_id = cur.lastrowid
                    conn.commit(); conn.close()
                    with st.spinner(f"جاري الرفع للـ Google Sheet - ID {new_id}..."):
                        ok = sync_booking_to_sheet(new_id)
                        if ok: st.success(f"✅ تم الرفع للـ Sheet - ID {new_id}")
                        else: st.warning("تم الحفظ محلياً - فشل الرفع للشيت")
                    st.session_state.do_clear=True; st.session_state.pending=None; st.rerun()
            with c2:
                if st.button("NO", use_container_width=True): st.session_state.pending=None; st.rerun()
    with r:
        col_f1, col_f2, col_f3=st.columns([1.2, 1.2, 1.3])
        with col_f1: entry_date_val=st.date_input("entry_date_filter", value=None, key="entry_date_filter", label_visibility="collapsed")
        with col_f2: exit_date_val=st.date_input("exit_date_filter", value=None, key="exit_date_filter", label_visibility="collapsed")
        with col_f3:
            c_a,c_b=st.columns(2)
            with c_a: st.button("Show All", use_container_width=True, on_click=clear_filters)
            with c_b: st.caption("✅ Sheet Live")

        b_filter, b_btns = st.columns([1.0, 4.0])
        with b_filter: search_mode = st.selectbox("نوع البحث", ["الكل", "مسافر فقط", "وكيل فقط", "رقم حجز"], key="search_mode")
        with b_btns:
            b1, b2, b3, b4, b5, scol=st.columns([0.5, 0.6, 0.6, 1.0, 0.6, 1.5])
            with b1: edit_btn=st.button("Edit", use_container_width=True, key="edit_small")
            with b2: inv_btn=st.button("Invoice", use_container_width=True, key="inv_btn")
            with b3: voucher_btn=st.button("Voucher", use_container_width=True, key="voucher_btn")
            with b4: statement_btn=st.button("Agent Statement", use_container_width=True, key="statement_btn", type="primary")
            with b5: view_btn=st.button("👁️ عرض", use_container_width=True, key="view_btn")
            with scol: search_val=st.text_input("Search", placeholder="Search...", label_visibility="collapsed", key="search")

        # ===== قراءة من Google Sheet مباشر =====
        sheet = get_gspread_sheet()
        if not sheet:
            st.error("Sheet not connected")
            st.stop()
        all_vals = sheet.get_all_values()
        if len(all_vals) < 2:
            df_raw = pd.DataFrame()
            display_df = pd.DataFrame(columns=["ID","Sale Date","Agent","Passengers","Room Type","Rooms","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co"])
        else:
            header = all_vals[0]
            rows = all_vals[1:]
            clean_rows = []
            for r in rows:
                if len(r) < len(header): r = r + [""] * (len(header)-len(r))
                clean_rows.append(r[:len(header)])
            df_raw = pd.DataFrame(clean_rows, columns=header)
            df_raw["_sheet_row"] = [i+2 for i in range(len(df_raw))]
            
            df_filtered = df_raw.copy()
            s_raw = search_val.strip()
            if s_raw:
                s = s_raw.lower()
                mode = st.session_state.get("search_mode", "الكل")
                if mode == "مسافر فقط":
                    df_filtered = df_filtered[df_filtered.apply(lambda row: s in str(row.get("passengers","")).lower(), axis=1)]
                elif mode == "وكيل فقط":
                    df_filtered = df_filtered[df_filtered.apply(lambda row: s in str(row.get("company","")).lower(), axis=1)]
                else:
                    df_filtered = df_filtered[df_filtered.apply(lambda row: s in str(row.values).lower(), axis=1)]
            if entry_date_val:
                df_filtered = df_filtered[df_filtered.apply(lambda row: str(entry_date_val) in str(row.values), axis=1)]
            if exit_date_val:
                df_filtered = df_filtered[df_filtered.apply(lambda row: str(exit_date_val) in str(row.values), axis=1)]

            if df_filtered.empty:
                display_df = pd.DataFrame(columns=["ID","Sale Date","Agent","Passengers","Room Type","Rooms","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co"])
            else:
                cols_map = ["id","sale_date","company","passengers","room_type","room_count","hotel","entry_date","exit_date","sell","airline","flight_dep_time","flight_ret_time","notes","emp","transport_company"]
                existing = [c for c in cols_map if c in df_filtered.columns]
                if existing and len(existing) > 5:
                    display_df = df_filtered[existing].copy()
                    display_df.columns = ["ID","Sale Date","Agent","Passengers","Room Type","Rooms","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co"][:len(existing)]
                else:
                    display_df = df_filtered.drop(columns=["_sheet_row"], errors='ignore').copy()
                df_raw = df_filtered

        if 'display_df' not in locals() or display_df is None:
            display_df = pd.DataFrame(columns=["ID","Sale Date","Agent","Passengers","Room Type","Rooms","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co"])

        event = st.dataframe(display_df, use_container_width=True, height=650, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"main_table_{st.session_state.table_version}")
        st.markdown(f"**Total bookings: {len(df_raw)}**")
        selected_rows = event.selection.rows if event and hasattr(event, 'selection') else []
        selected_ids = []
        if selected_rows and not df_raw.empty:
            try:
                selected_ids = df_raw.iloc[selected_rows]["_sheet_row"].tolist()
                st.info(f"✅ محدد: Sheet Row {selected_ids[0]}")
            except:
                selected_ids = [selected_rows[0]+2]

        def get_selected_ids(): return selected_ids
        def get_selected_agent():
            if selected_rows and not df_raw.empty:
                try: return df_raw.iloc[selected_rows[0]].get("company","")
                except: return None
            return None

        # ===== الأزرار صارت تقرا من الشيت =====
        if edit_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("اكبس على سطر واحد وبعدين Edit")
            else:
                row_idx = int(ids[0])
                # ابعت رقم السطر للـ edit_dialog
                edit_dialog(row_idx)

        if inv_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("اكبس على سطر واحد وبعدين Invoice")
            else:
                row_idx = int(ids[0])
                invoice_dialog(row_idx)

        if voucher_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("اكبس على سطر واحد وبعدين Voucher")
            else:
                row_idx = int(ids[0])
                voucher_dialog(row_idx)
if statement_btn:
    ag = get_selected_agent()
    if not ag:
        st.error("حدد سطر واحد للوكيل")
    else:
        agent_statement_dialog(ag)

if view_btn:
    ids = get_selected_ids()
    if len(ids)!= 1:
        st.error("حدد حجز واحد من الجدول أولاً")
    else:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (int(ids[0]),)).fetchone()
        conn.close()
        if row:
            @st.dialog("Booking Details", width="small")
            def view_dialog():
                d = dict(row)
                st.markdown(f"<h3 style='text-align:center; font-weight:900; margin:0;'>{d.get('company','')}</h3>", unsafe_allow_html=True)
                st.divider()
                
                st.markdown("""
                <style>
                .pax-box {
                    max-height:150px; 
                    overflow-y:auto; 
                    border:1px solid #ddd; 
                    border-radius:6px; 
                    padding:6px 8px; 
                    background:#f9f9f9; 
                    font-size:16px; 
                    font-weight:900; 
                    white-space:pre-line;
                    margin-top:0;
                }
                </style>
                """, unsafe_allow_html=True)
                pax = f"<div class='pax-box'>{d.get('passengers','')}</div>"
                notes_val = (d.get('notes','') or d.get('note','') or '').strip()

                # --- فوق ---
                st.markdown("<p style='font-weight:900; font-size:15px; margin:0 0 2px 0;'>Passengers:</p>", unsafe_allow_html=True)
                st.markdown(pax, unsafe_allow_html=True)
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:0;'>Hotel: {d.get('hotel','')}</p>", unsafe_allow_html=True)
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Check-in: {d.get('entry_date','')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Departure: {d.get('flight_dep_time','')} {d.get('dep_airport','')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Flight No: {d.get('flight_no_dep','')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Note: {notes_val}</p>", unsafe_allow_html=True)
                
                st.markdown("<div style='height:50px;'></div>", unsafe_allow_html=True)
                st.divider()
                
                # --- تحت ---
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Hotel: {d.get('hotel','')}</p>", unsafe_allow_html=True)
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                st.markdown("<p style='font-weight:900; font-size:15px; margin:0 0 2px 0;'>Passengers:</p>", unsafe_allow_html=True)
                st.markdown(pax, unsafe_allow_html=True)
                st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Check-out: {d.get('exit_date','')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Return: {d.get('flight_ret_time','')} {d.get('ret_airport','')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Flight No: {d.get('flight_no_ret','')}</p>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-weight:900; font-size:15px; margin:2px 0;'>Note: {notes_val}</p>", unsafe_allow_html=True)

            view_dialog()
with t2:
    st.divider()

    def to_f_local(x):
        try: return float(str(x).replace('$','').replace(',','').strip() or 0)
        except: return 0

    def first_traveler_only(text):
        if not text: return ""
        t=str(text).strip()
        for sep in [",", "\n", "/", ";", "|", " - "]:
            if sep in t: t=t.split(sep)[0]; break
        return t.strip()[:25]

    def get_col(df, *keys):
        for k in keys:
            for c in df.columns:
                if k.lower() in c.lower(): return c
        return None

def generate_pdf_bytes(pay_agent):
    from fpdf import FPDF
    from io import BytesIO
    from datetime import datetime
    conn = sqlite3.connect(DB)
    df_pays_pdf = pd.read_sql("SELECT pay_date,amount,note FROM agent_payments WHERE agent=? ORDER BY pay_date", conn, params=(pay_agent,))
    total_paid_pdf = df_pays_pdf['amount'].sum() if not df_pays_pdf.empty else 0
    df_raw_for_pdf = pd.read_sql("SELECT * FROM bookings WHERE company=?", conn, params=(pay_agent,))
    conn.close()
    if df_raw_for_pdf.empty:
        return None
    sell_c = None
    for c in df_raw_for_pdf.columns:
        if 'sell' in c.lower() or 'price' in c.lower():
            sell_c = c
            break
    total_sell = df_raw_for_pdf[sell_c].apply(to_f_local).sum() if sell_c else 0
    col_traveler = get_col(df_raw_for_pdf, 'traveler', 'guest', 'passenger', 'pax_name', 'names')
    col_pax = get_col(df_raw_for_pdf, 'pax', 'persons', 'people', 'adult')
    col_hotel = get_col(df_raw_for_pdf, 'hotel')
    col_room_type = get_col(df_raw_for_pdf, 'room_type', 'room')
    col_room_count = get_col(df_raw_for_pdf, 'room_count', 'rooms')
    col_checkin = get_col(df_raw_for_pdf, 'checkin', 'check_in', 'arrival')
    col_nights = get_col(df_raw_for_pdf, 'nights', 'night')
    col_checkout = get_col(df_raw_for_pdf, 'checkout', 'check_out', 'departure')
    col_note = get_col(df_raw_for_pdf, 'note', 'remark')

    class PDF(FPDF):
        def header(self):
            self.set_font("Arial", "B", 26)
            self.set_text_color(13, 71, 161)
            self.cell(0, 14, "HOTRIGO", ln=True, align='C')
            self.ln(2)
            self.set_draw_color(13, 71, 161)
            self.set_line_width(0.8)
            self.line(10, self.get_y(), 287, self.get_y())
            self.ln(6)
        def footer(self):
            self.set_y(-15)
            self.set_font("Arial", "I", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | HOTRIGO - {pay_agent}", align='C')

    pdf = PDF(orientation='L', unit='mm', format='A4')
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()
    pdf.set_font("Arial", "B", 14)
    pdf.cell(0, 10, f"Agent Statement - {pay_agent}", ln=True, align='C')
    pdf.ln(4)
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(13, 71, 161)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 10, f"Total Sales: ${total_sell:.2f} | Paid: ${total_paid_pdf:.2f} | Balance: ${total_sell-total_paid_pdf:.2f}", border=1, align='C', fill=True)
    pdf.ln(12)
    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(13, 71, 161)
    pdf.cell(0, 8, f"Bookings - {pay_agent}", ln=True)
    pdf.ln(2)
    headers = ["ID", "Agent", "Traveler", "Pax", "Hotel", "Room Type", "Rooms", "Check-in", "Nights", "Check-out", "Sale Price", "Note"]
    widths = [12, 18, 24, 9, 28, 20, 10, 18, 10, 18, 18, 92]
    pdf.set_font("Arial", "B", 7)
    pdf.set_fill_color(13, 71, 161)
    pdf.set_text_color(255, 255, 255)
    for h, w in zip(headers, widths):
        pdf.cell(w, 8, h, border=1, align='C', fill=True)
    pdf.ln()
    pdf.set_font("Arial", "", 6.5)
    pdf.set_text_color(0, 0, 0)
    for _, row in df_raw_for_pdf.iterrows():
        if pdf.get_y() > 175:
            pdf.add_page()
        vals = [str(row.get('id',"")), str(pay_agent)[:12], first_traveler_only(row.get(col_traveler,"") if col_traveler else ""), str(row.get(col_pax,"") if col_pax else ""), str(row.get(col_hotel,"") if col_hotel else "")[:18], str(row.get(col_room_type,"") if col_room_type else "")[:12], str(row.get(col_room_count,"") if col_room_count else ""), str(row.get(col_checkin,"") if col_checkin else "")[:10], str(row.get(col_nights,"") if col_nights else ""), str(row.get(col_checkout,"") if col_checkout else "")[:10], f"${to_f_local(row.get(sell_c,0)):.0f}" if sell_c else "", str(row.get(col_note,"") if col_note else "")[:50]]
        for v, w in zip(vals, widths):
            pdf.cell(w, 7, v, border=1, align='C')
        pdf.ln()
    pdf.ln(8)
    if not df_pays_pdf.empty:
        if pdf.get_y() > 160:
            pdf.add_page()
        pdf.set_font("Arial", "B", 11)
        pdf.set_text_color(13, 71, 161)
        pdf.cell(0, 8, f"Payment History - {pay_agent}", ln=True)
        pdf.ln(1)
        pdf.set_font("Arial", "B", 8)
        pdf.set_fill_color(0, 150, 64)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(40, 9, "Date", border=1, align='C', fill=True)
        pdf.cell(30, 9, "Amount", border=1, align='C', fill=True)
        pdf.cell(207, 9, "Note", border=1, align='C', fill=True)
        pdf.ln()
        pdf.set_font("Arial", "", 8)
        pdf.set_text_color(0, 0, 0)
        for _, prow in df_pays_pdf.iterrows():
            if pdf.get_y() > 180:
                pdf.add_page()
            pdf.cell(40, 8, str(prow['pay_date']), border=1, align='C')
            pdf.cell(30, 8, f"${float(prow['amount']):.2f}", border=1, align='C')
            pdf.cell(207, 8, str(prow['note'])[:95], border=1, align='L')
            pdf.ln()
    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()

def generate_excel_bytes(pay_agent):
    from io import BytesIO
    from datetime import datetime
    import pandas as pd
    import sqlite3

    conn = sqlite3.connect(DB)
    df1 = pd.read_sql("SELECT * FROM bookings WHERE company=?", conn, params=(pay_agent,))
    df2 = pd.read_sql("SELECT * FROM agent_payments WHERE agent=?", conn, params=(pay_agent,))
    conn.close()

    def _parse_date(d):
        if not d or pd.isna(d):
            return None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                return datetime.strptime(str(d).strip(), fmt)
            except:
                pass
        return None

    def _first_pax(pas):
        if not pas or pd.isna(pas):
            return ""
        s = str(pas).replace('\r', '\n').strip()
        lines = [x.strip() for x in s.split('\n') if x.strip()]
        return lines[0].split(',')[0].strip() if lines else ""

    def _count_pax(pas):
        if not pas or pd.isna(pas):
            return 0
        s = str(pas).replace('\r', '\n').strip()
        lines = [x.strip() for x in s.split('\n') if x.strip()]
        if len(lines) > 1:
            return len(lines)
        if ',' in s:
            return len([x for x in s.split(',') if x.strip()])
        return 1 if s else 0

    data = []
    for _, r in df1.iterrows():
        ent = _parse_date(r.get('entry_date'))
        ex = _parse_date(r.get('exit_date'))
        nights = (ex - ent).days if ent and ex else ""
        data.append({
            'Booking ID': r.get('id', ''),
            'Agent Name': r.get('company', pay_agent),
            'First Passenger': _first_pax(r.get('passengers', '')),
            'Pax Count': _count_pax(r.get('passengers', '')),
            'Hotel': r.get('hotel', ''),
            'Room Type': r.get('room_type', ''),
            'Room Count': r.get('room_count', ''),
            'Check-in': r.get('entry_date', ''),
            'Nights': nights,
            'Check-out': r.get('exit_date', ''),
            'Sell Price': r.get('sell', ''),
            'Notes': r.get('notes', ''),
        })

    book_export = pd.DataFrame(data) if data else pd.DataFrame([{'Note': 'No bookings'}])

    if not df2.empty:
        cols = [c for c in ['pay_date', 'amount', 'note'] if c in df2.columns]
        pay_export = df2[cols].copy()
        pay_export.rename(columns={'pay_date': 'Payment Date', 'amount': 'Amount', 'note': 'Payment Note'}, inplace=True)
    else:
        pay_export = pd.DataFrame([{'Note': 'No payments'}])

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        book_export.to_excel(writer, sheet_name='Bookings', index=False)
        pay_export.to_excel(writer, sheet_name='Payments', index=False)
    output.seek(0)
    return output.getvalue()

# --- Payments from Google Sheet - DB Removed ---
agents_list = agents_for_js

left_side, right_side = st.columns([1, 1], gap="large")

with left_side:
    narrow, gap = st.columns([0.40, 0.60])
    with narrow:
        st.markdown("#### Add New Payment")
        pay_agent = st.selectbox("Agent Name", agents_list, key="pay_agent_main")
        pay_date = st.date_input("Payment Date", datetime.now(), key="pay_date_main")
        pay_amount = st.text_input("Payment Amount $", key="pay_amount_main", placeholder="$ Amount")
        pay_statement = st.text_input("Statement", key="pay_statement_main", placeholder="e.g. Hotel booking payment...")
        pay_note = st.text_input("Note", key="pay_note_main", placeholder="Bank - Cash...")

        if st.button("Add Payment", use_container_width=True, type="primary", key="btn_add_pay_main"):
            amt = to_f_local(pay_amount)
            if amt <= 0:
                st.error("Please enter valid amount")
            else:
                try:
                    _sheet = get_gspread_sheet()
                    spreadsheet = _sheet.spreadsheet
                    try:
                        pay_ws = spreadsheet.worksheet("Payments")
                    except:
                        pay_ws = spreadsheet.add_worksheet(title="Payments", rows=2000, cols=10)
                        pay_ws.append_row(
                            ["Pay Date", "Agent Name", "Amount", "Statement", "Note", "Created At"],
                            value_input_option="USER_ENTERED"
                        )

                    pay_ws.append_row(
                        [
                            str(pay_date),
                            pay_agent,
                            amt,
                            pay_statement,
                            pay_note,
                            str(datetime.now())
                        ],
                        value_input_option="USER_ENTERED"
                    )
                    
                    st.success(f"Payment ${amt} added for {pay_agent}")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")

        try:
            pdf_bytes = generate_pdf_bytes(pay_agent)
        except:
            pdf_bytes = None

        try:
            excel_bytes = generate_excel_bytes(pay_agent)
        except Exception as e:
            print(e)
            excel_bytes = None
        b1, b2 = st.columns(2, gap="small")
        with b1:
            if pdf_bytes:
                st.download_button("🖨️ Print PDF", data=pdf_bytes, file_name=f"HOTRIGO_{pay_agent}_statement.pdf", mime="application/pdf", use_container_width=True, key=f"dl_pdf_one_{pay_agent}")
            else:
                st.button("🖨️ Print PDF", disabled=True, use_container_width=True, key=f"dis_pdf_{pay_agent}")
        with b2:
            if excel_bytes:
                st.download_button("📊 Export Excel", data=excel_bytes, file_name=f"HOTRIGO_{pay_agent}_statement.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True, key=f"dl_excel_one_{pay_agent}")
    with right_side:
        # === فوق : Agents Summary ===
        st.markdown("#### 💰 Agents Summary")
        try:
            conn=sqlite3.connect(DB)
            df_all_bookings=pd.read_sql("SELECT * FROM bookings",conn)
            df_all_pays=pd.read_sql("SELECT agent, SUM(amount) as total_paid FROM agent_payments GROUP BY agent",conn)
            conn.close()
            sell_c_all=None
            for c in df_all_bookings.columns:
                if 'sell' in c.lower() or 'price' in c.lower(): sell_c_all=c; break
            summary=[]
            for ag in agents_list:
                df_ag = df_all_bookings[df_all_bookings['company']==ag] if not df_all_bookings.empty else pd.DataFrame()
                total_sales = df_ag[sell_c_all].apply(to_f_local).sum() if not df_ag.empty and sell_c_all else 0
                paid_row = df_all_pays[df_all_pays['agent']==ag] if not df_all_pays.empty else pd.DataFrame()
                total_paid = float(paid_row['total_paid'].values[0]) if not paid_row.empty else 0
                summary.append({"Agent":ag, "Sales":total_sales, "Paid":total_paid, "Balance":total_sales-total_paid})
            df_summary=pd.DataFrame(summary)
            if not df_summary.empty:
                st.dataframe(df_summary.style.format({"Sales":"${:.2f}","Paid":"${:.2f}","Balance":"${:.2f}"}), use_container_width=True, height=250)
                st.markdown(f"""<div style="background:#0d47a1;color:white;padding:10px;border-radius:8px;text-align:center">
                Sales: ${df_summary['Sales'].sum():.2f} | Paid: ${df_summary['Paid'].sum():.2f} | Due: ${df_summary['Balance'].sum():.2f}
                </div>""", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Summary Error: {e}")

        st.divider()

        # === تحت : Statement for AHMAD ===
        st.markdown(f"#### Statement for {pay_agent}")
        conn=sqlite3.connect(DB)
        df_pays=pd.read_sql("SELECT pay_date as Date, amount as Amount, note as Note FROM agent_payments WHERE agent=? ORDER BY pay_date DESC", conn, params=(pay_agent,))
        df_books=pd.read_sql("SELECT * FROM bookings WHERE company=?", conn, params=(pay_agent,))
        conn.close()
        if not df_books.empty:
            for c in df_books.columns:
                if 'sell' in c.lower() or 'price' in c.lower():
                    total_sell_r = df_books[c].apply(to_f_local).sum(); break
            else: total_sell_r=0
        else: total_sell_r=0
        total_paid_r = df_pays['Amount'].sum() if not df_pays.empty else 0
        c1,c2,c3 = st.columns(3)
        c1.metric("Total Sales", f"${total_sell_r:.2f}")
        c2.metric("Total Paid", f"${total_paid_r:.2f}")
        c3.metric("Balance", f"${total_sell_r - total_paid_r:.2f}")
        if not df_pays.empty:
            st.dataframe(df_pays, use_container_width=True, hide_index=True)
with t3:
    conn = sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT PRIMARY KEY)")
    conn.commit()
    conn.close()

    c1, c2, c3, c4 = st.columns(4, gap="medium")

    with c1:
        with st.container(border=True):
            st.markdown("#### 👥 Agents")
            with st.form(key="f_agents", clear_on_submit=True):
                na = st.text_input("", placeholder="Agent name...", label_visibility="collapsed")
                sa = st.form_submit_button("Add Agent", use_container_width=True)
                if sa and na.strip():
                    conn=sqlite3.connect(DB)
                    try: conn.execute("INSERT INTO agents (name) VALUES (?)", (na.strip().upper(),)); conn.commit()
                    except: pass
                    conn.close(); st.rerun()
            conn=sqlite3.connect(DB); dfa=pd.read_sql("SELECT name as Agents FROM agents ORDER BY name", conn); conn.close()
            st.dataframe(dfa, use_container_width=True, height=250, hide_index=True)

    with c2:
        with st.container(border=True):
            st.markdown("#### 🏨 Hotels")
            with st.form(key="f_hotels", clear_on_submit=True):
                nh = st.text_input("", placeholder="Hotel name...", label_visibility="collapsed")
                sh = st.form_submit_button("Add Hotel", use_container_width=True)
                if sh and nh.strip():
                    conn=sqlite3.connect(DB)
                    try: conn.execute("INSERT INTO hotels (name) VALUES (?)", (nh.strip(),)); conn.commit()
                    except: pass
                    conn.close(); st.rerun()
            conn=sqlite3.connect(DB); dfh=pd.read_sql("SELECT name as Hotels FROM hotels ORDER BY name", conn); conn.close()
            st.dataframe(dfh, use_container_width=True, height=250, hide_index=True)

    with c3:
        with st.container(border=True):
            st.markdown("#### ✈️ Airlines")
            with st.form(key="f_airlines", clear_on_submit=True):
                nal = st.text_input("", placeholder="Airlines name...", label_visibility="collapsed")
                sal = st.form_submit_button("Add Airline", use_container_width=True)
                if sal and nal.strip():
                    conn=sqlite3.connect(DB)
                    try: conn.execute("INSERT INTO airlines (name) VALUES (?)", (nal.strip(),)); conn.commit()
                    except: pass
                    conn.close(); st.rerun()
            conn=sqlite3.connect(DB); dfal=pd.read_sql("SELECT name as Airlines FROM airlines ORDER BY name", conn); conn.close()
            st.dataframe(dfal, use_container_width=True, height=250, hide_index=True)

    with c4:
        with st.container(border=True):
            st.markdown("#### 🚌 Transport")
            with st.form(key="f_transport", clear_on_submit=True):
                nt = st.text_input("", placeholder="Transportation name...", label_visibility="collapsed")
                stf = st.form_submit_button("Add Transport", use_container_width=True)
                if stf and nt.strip():
                    conn=sqlite3.connect(DB)
                    try: conn.execute("INSERT INTO transport_companies (name) VALUES (?)", (nt.strip(),)); conn.commit()
                    except: pass
                    conn.close(); st.rerun()
            conn=sqlite3.connect(DB); dft=pd.read_sql("SELECT name as Transport FROM transport_companies ORDER BY name", conn); conn.close()
            st.dataframe(dft, use_container_width=True, height=250, hide_index=True)
