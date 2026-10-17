import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit.components.v1 as components
import os, io, re, json, base64
from pathlib import Path

# ===== GOOGLE DRIVE + SHEETS =====
import os, json, base64, re, io
import gspread
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SHEET_ID_FALLBACK = "1WyJlLeChys_qh_qCxjFUZBq-FlhgHbhBaizMcg21Zqc"
SHEETS_AVAILABLE = True
DRIVE_AVAILABLE = True

BASE_DIR = os.path.dirname(__file__)
DRIVE_FOLDER = "Hotrigo Backup"
SHEET_NAME = "HOTRIGO_DATABASE"
SHEET_ID = SHEET_ID_FALLBACK
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Price Night","Hotel Total","Check-in","Nights","Check-out","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]
DB = os.path.join(BASE_DIR, "hotrigo.db")

def get_drive_service():
    try:
        creds_info = dict(st.secrets["gcp_service_account"])
        if "\\n" in creds_info.get("private_key",""):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        creds = Credentials.from_service_account_info(creds_info, scopes=["https://www.googleapis.com/auth/drive"])
        service = build('drive', 'v3', credentials=creds)
        folder_id = st.secrets.get("FOLDER_ID")
        return service, folder_id
    except Exception as e:
        print(f"Drive error: {e}")
        return None, None

def get_folder_id(service, name):
    try:
        q=f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
        res=service.files().list(q=q, fields="files(id)").execute()
        files=res.get('files',[])
        if files: return files[0]['id']
        folder=service.files().create(body={'name':name,'mimeType':'application/vnd.google-apps.folder'},fields='id').execute()
        return folder.get('id')
    except:
        return None

def get_gspread_sheet(worksheet_name=None):
    try:
        sid = st.secrets.get("SHEET_ID", SHEET_ID_FALLBACK)
        sid = str(sid).strip().strip('"').strip("'")
        creds_info = dict(st.secrets["gcp_service_account"])
        if "\\n" in creds_info.get("private_key",""):
            creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
        scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        client = gspread.authorize(creds)
        ss = client.open_by_key(sid)
        if worksheet_name:
            try:
                return ss.worksheet(worksheet_name)
            except:
                return ss.add_worksheet(title=worksheet_name, rows=2000, cols=30)
        return ss.sheet1
    except Exception as e:
        st.error(f"❌ Sheet Error: {e}")
        import traceback
        st.code(traceback.format_exc())
        return None

def get_spreadsheet():
    try:
        ws = get_gspread_sheet()
        return ws.spreadsheet if ws else None
    except:
        return None

def add_payment(tab_name, name_value, amount_val, note_val, note1_val):
    try:
        ws = get_gspread_sheet(tab_name)
        if not ws:
            st.error("Sheet not connected")
            return False
        ws.append_row([
            datetime.now().strftime("%Y-%m-%d"),
            str(name_value),
            float(amount_val),
            str(note_val),
            str(note1_val),
            st.session_state.get("username","admin"),
            datetime.now().strftime("%H%M%S")
        ])
        st.success(f"تم الحفظ في {tab_name} ✓")
        return True
    except Exception as e:
        st.error(f"Sheet Error {tab_name}: {e}")
        return False

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
                return True
    except Exception as e:
        print(f"Upload Error: {e}")
    return False

def load_data():
    try:
        sheet = get_gspread_sheet()
        if not sheet:
            return []
        return sheet.get_all_records()
    except Exception as e:
        print(f"Load error: {e}")
        return []

def booking_to_sheet_row(b):
    try:
        try: d = dict(b)
        except: d = {k: b[k] for k in b.keys()}
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
        except: pass
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
        row = [gv("id"),gv("company"),gv("passengers"),pax_count,gv("hotel"),room_count,gv("room_type"),pn,hotel_total,gv("entry_date"),nights,gv("exit_date"),fl,tr,sell,cost,profit,gv("sale_date"),gv("voucher_no"),gv("notes"),gv("airline"),gv("emp"),gv("flight_dep_time"),gv("flight_ret_time"),gv("flight_no_dep"),gv("flight_no_ret"),gv("transport_company"),]
        return [str(x) if x is not None else "" for x in row]
    except Exception as e:
        print(f"booking_to_sheet_row error {e}")
        return None

def sync_booking_to_sheet(booking_data):
    try:
        sheet = get_gspread_sheet()
        if not sheet: return False
        if not isinstance(booking_data, dict): return False
        b = booking_data
        booking_id = str(b.get("id", b.get("ID", "")))
        row = booking_to_sheet_row(b)
        if not row: return False
        try:
            cell = sheet.find(booking_id)
            sheet.update(f"A{cell.row}:AA{cell.row}", [row])
        except:
            sheet.append_row(row, value_input_option='USER_ENTERED')
        return True
    except Exception as e:
        print(f"Sync failed {e}")
        return False

def sync_all_to_sheet():
    return True

# --- PDF Imports ---
try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo.png")
def get_logo_b64():
    if os.path.exists(LOGO_PATH):
        try:
            with open(LOGO_PATH, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except:
            return None
    return None

def init():
    try:
        sheet = get_gspread_sheet()
        if sheet:
            try:
                first_row = sheet.row_values(1)
                if not first_row or len(first_row) == 0:
                    sheet.update('A1', [SHEET_HEADER])
            except: pass
    except: pass
    return True
init()
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

# ===== GLOBAL HELPER - لازم يكون فوق الكل =====
def to_f(v):
    try:
        return float(str(v).strip().replace(',', '').replace('$','') or 0)
    except:
        return 0.0

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
                    import pandas as pd
                    if up_file.name.endswith(".csv"):
                        df = pd.read_csv(up_file)
                    else:
                        df = pd.read_excel(up_file)
                    col = df.columns[0]
                    passenger_list = df[col].astype(str).tolist()
                    st.success(f"Loaded {len(passenger_list)} names from Excel")
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
            elif not comp_ok: st.error(f"❌ Agent '{comp}' not found!")
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
            for r_ in rows:
                if len(r_) < len(header): r_ = r_ + [""] * (len(header)-len(r_))
                clean_rows.append(r_[:len(header)])
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

        if edit_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("اكبس على سطر واحد وبعدين Edit")
            else: edit_dialog(int(ids[0]))
        if inv_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("اكبس على سطر واحد وبعدين Invoice")
            else: invoice_dialog(int(ids[0]))
        if voucher_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("اكبس على سطر واحد وبعدين Voucher")
            else: voucher_dialog(int(ids[0]))
        if statement_btn:
            ag = get_selected_agent()
            if not ag: st.error("حدد سطر واحد للوكيل")
            else: agent_statement_dialog(ag)
        if view_btn:
            ids = get_selected_ids()
            if len(ids)!= 1: st.error("حدد حجز واحد من الجدول أولاً")
            else:
                if selected_rows and not df_raw.empty:
                    d = dict(df_raw.iloc[selected_rows[0]])
                    @st.dialog("Booking Details", width="small")
                    def view_dialog():
                        st.markdown(f"<h3 style='text-align:center; font-weight:900;'>{d.get('company','')}</h3>", unsafe_allow_html=True)
                        st.divider()
                        st.markdown(f"**Passengers:**\n{d.get('passengers','')}")
                        st.markdown(f"**Hotel:** {d.get('hotel','')}")
                        st.markdown(f"**Check-in:** {d.get('entry_date','')} | **Check-out:** {d.get('exit_date','')}")
                        st.markdown(f"**Sell:** ${d.get('sell','')} | **Note:** {d.get('notes','')}")
                    view_dialog()

with t2:
    st.markdown("### 💰 Account Statement - Google Sheets")
    def to_f_local(x):
        try: return float(str(x).replace('$','').replace(',','').strip() or 0)
        except: return 0

    def generate_pdf_bytes(pay_agent):
        from fpdf import FPDF
        from io import BytesIO
        ws_res = get_gspread_sheet("reservations")
        ws_pay = get_gspread_sheet("Payments")
        df_book = pd.DataFrame(ws_res.get_all_records()) if ws_res else pd.DataFrame()
        df_pay = pd.DataFrame(ws_pay.get_all_records()) if ws_pay else pd.DataFrame()
        if not df_book.empty and 'company' in df_book.columns: df_book = df_book[df_book['company']==pay_agent]
        if not df_pay.empty and 'Agent Name' in df_pay.columns: df_pay = df_pay[df_pay['Agent Name']==pay_agent]
        if df_book.empty and df_pay.empty: return None
        total_sell = pd.to_numeric(df_book['sell'], errors='coerce').sum() if 'sell' in df_book.columns else 0
        total_paid = pd.to_numeric(df_pay['Amount'], errors='coerce').sum() if 'Amount' in df_pay.columns else 0
        pdf=FPDF(orientation='L'); pdf.add_page()
        pdf.set_font("Arial","B",14); pdf.cell(0,10,f"Statement - {pay_agent} | Sales ${total_sell:.2f} | Paid ${total_paid:.2f} | Balance ${total_sell-total_paid:.2f}",ln=True,align='C')
        buf=BytesIO(); pdf.output(buf); return buf.getvalue()

    def generate_excel_bytes(pay_agent):
        from io import BytesIO
        ws_res = get_gspread_sheet("reservations")
        ws_pay = get_gspread_sheet("Payments")
        df1 = pd.DataFrame(ws_res.get_all_records()) if ws_res else pd.DataFrame()
        df2 = pd.DataFrame(ws_pay.get_all_records()) if ws_pay else pd.DataFrame()
        if not df1.empty and 'company' in df1.columns: df1 = df1[df1['company']==pay_agent]
        if not df2.empty and 'Agent Name' in df2.columns: df2 = df2[df2['Agent Name']==pay_agent]
        output=BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            (df1 if not df1.empty else pd.DataFrame([{'Note':'No bookings'}])).to_excel(writer, sheet_name='Bookings', index=False)
            (df2 if not df2.empty else pd.DataFrame([{'Note':'No payments'}])).to_excel(writer, sheet_name='Payments', index=False)
        output.seek(0); return output.getvalue()

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
                if amt <= 0: st.error("Please enter valid amount")
                else:
                    ok = add_payment("Payments", pay_agent, amt, pay_statement, pay_note)
                    if ok:
                        st.cache_data.clear(); st.rerun()
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
            ws_res = get_gspread_sheet("reservations")
            ws_pay = get_gspread_sheet("Payments")
            df_all_bookings = pd.DataFrame(ws_res.get_all_records()) if ws_res else pd.DataFrame()
            df_all_pays = pd.DataFrame(ws_pay.get_all_records()) if ws_pay else pd.DataFrame()
            summary=[]
            for ag in agents_list:
                sales = pd.to_numeric(df_all_bookings[df_all_bookings['company']==ag]['sell'], errors='coerce').sum() if not df_all_bookings.empty and 'company' in df_all_bookings.columns and 'sell' in df_all_bookings.columns else 0
                paid = pd.to_numeric(df_all_pays[df_all_pays['Agent Name']==ag]['Amount'], errors='coerce').sum() if not df_all_pays.empty and 'Agent Name' in df_all_pays.columns and 'Amount' in df_all_pays.columns else 0
                summary.append({"Agent":ag, "Sales":sales, "Paid":paid, "Balance":sales-paid})
            df_summary=pd.DataFrame(summary)
            if not df_summary.empty:
                st.dataframe(df_summary.style.format({"Sales":"${:.2f}","Paid":"${:.2f}","Balance":"${:.2f}"}), use_container_width=True, height=250)
                st.markdown(f"""<div style="background:#0d47a1;color:white;padding:10px;border-radius:8px;text-align:center">
                Sales: ${df_summary['Sales'].sum():.2f} | Paid: ${df_summary['Paid'].sum():.2f} | Due: ${df_summary['Balance'].sum():.2f}
                </div>""", unsafe_allow_html=True)
        except Exception as e: st.error(f"Summary Error: {e}")
        st.divider()
        st.markdown(f"#### Statement")
        try:
            ws_pay = get_gspread_sheet("Payments")
            df_p = pd.DataFrame(ws_pay.get_all_records()) if ws_pay else pd.DataFrame()
            if not df_p.empty: st.dataframe(df_p, use_container_width=True, height=300)
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
                nal = st.text_input("Airlines name", placeholder="Airlines name...", label_visibility="collapsed")
                sal = st.form_submit_button("Add Airline", width='stretch')
                if sal and nal.strip():
                    conn=sqlite3.connect(DB)
                    try: 
                        conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
                        conn.execute("INSERT INTO airlines (name) VALUES (?)", (nal.strip(),))
                        conn.commit()
                    except: pass
                    conn.close(); st.rerun()
            conn=sqlite3.connect(DB)
            try:
                conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
                dfal=pd.read_sql("SELECT name as Airlines FROM airlines ORDER BY name", conn)
            except: dfal=pd.DataFrame(columns=["Airlines"])
            conn.close()
            st.dataframe(dfal, width='stretch', height=250, hide_index=True)
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
