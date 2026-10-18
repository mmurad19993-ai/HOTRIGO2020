import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import os, re
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

st.set_page_config(layout="wide", page_title="hotrigo")
SHEET_ID_FALLBACK = "1WyJlLeChys_qh_qCxjFUZBq-FlhgHbhBaizMcg21Zqc"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "hotrigo.db")
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Check-in","Nights","Check-out","Price Night","Hotel Total","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]

def to_f(v):
    try: return float(str(v).strip().replace(',', '').replace('$','') or 0)
    except: return 0.0

if "table_version" not in st.session_state:
    st.session_state.table_version = 0

def get_sheet_id_clean():
    raw = st.secrets.get("SHEET_ID", SHEET_ID_FALLBACK)
    raw = str(raw).strip().strip('"').strip("'").strip()
    m = re.search(r"/d/([a-zA-Z0-9-_]+)", raw)
    if m:
        return m.group(1)
    return raw

@st.cache_resource
def get_gspread_client():
    creds_info = dict(st.secrets["gcp_service_account"])
    if "\\n" in creds_info.get("private_key",""):
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    scopes = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
    return gspread.authorize(creds)

def get_gspread_sheet(worksheet_name=None):
    try:
        client = get_gspread_client()
        sid = get_sheet_id_clean()
        
        ss = None
        # الحل النهائي: افتح بالاسم يلي شفناه بالصورة
        try:
            ss = client.open("HOTRIGO_DATABASE")
        except:
            try:
                ss = client.open_by_key(sid)
            except Exception as e:
                # اخر محاولة من الليستة
                files = client.list_spreadsheet_files()
                for f in files:
                    if f['id'] == sid or "HOTRIGO" in f['name'].upper():
                        ss = client.open_by_key(f['id'])
                        break
                if not ss:
                    st.error(f"Sheet Error: {e} - ID: {sid}")
                    with st.expander("الشيتات يلي البوت شايفها"):
                        for f in files:
                            st.write(f"✅ {f['name']} -> {f['id']}")
                    return None

        if worksheet_name:
            try: return ss.worksheet(worksheet_name)
            except: return ss.add_worksheet(title=worksheet_name, rows=2000, cols=30)
        return ss.sheet1
    except Exception as e:
        st.error(f"Sheet Error: {e}")
        return None

def add_payment(tab_name, name_value, amount_val, note_val, note1_val):
    try:
        ws = get_gspread_sheet(tab_name)
        if not ws: return False
        ws.append_row([datetime.now().strftime("%Y-%m-%d"),str(name_value),float(amount_val)], value_input_option='USER_ENTERED')
        return True
    except: return False

def load_lists():
    try:
        conn = sqlite3.connect(DB)
        conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT PRIMARY KEY)")
        agents = [r[0] for r in conn.execute("SELECT name FROM agents ORDER BY name").fetchall()]
        hotels = [r[0] for r in conn.execute("SELECT name FROM hotels ORDER BY name").fetchall()]
        conn.close()
        return agents, hotels
    except: return [], []

agents_for_js, hotels_for_js = load_lists()

@st.dialog("Edit Booking")
def edit_dialog(row):
    sheet = get_gspread_sheet()
    if not sheet: return
    try:
        all_vals = sheet.get_all_values()
        header = all_vals[0]
        d_row = all_vals[row-1]
        d = {h: d_row[i] if i < len(d_row) else "" for i, h in enumerate(header)}
    except: return
    st.info(f"Editing #{row}")
    e_comp=st.text_input("Agent", value=d.get("Agent",""), key=f"ec_{row}")
    e_pas=st.text_area("Passengers", value=d.get("Passengers",""), key=f"ep_{row}")
    e_hotel=st.text_input("Hotel", value=d.get("Hotel",""), key=f"eh_{row}")
    if st.button("Save", type="primary", key=f"es_{row}"):
        try:
            new_row=[str(d.get(h,"")) for h in header]
            if "Agent" in header: new_row[header.index("Agent")]=e_comp
            if "Passengers" in header: new_row[header.index("Passengers")]=e_pas
            if "Hotel" in header: new_row[header.index("Hotel")]=e_hotel
            sheet.update(f"A{row}:ZZ{row}", [new_row], value_input_option="USER_ENTERED")
            st.success("Updated"); st.session_state.table_version+=1; st.rerun()
        except Exception as e: st.error(str(e))

st.markdown("## ✈️ hotrigo | Sheets Sync ✅")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])

with t1:
    l,r=st.columns([1, 4.8])
    with l:
        sd=st.date_input("Sale Date", datetime.now(), key="sd_main")
        emp=st.text_input("Sales Employee *", key="emp_main")
        agents_list, hotels_list = load_lists()
        comp=st.selectbox("Agent *", options=agents_list if agents_list else [""], key="comp_main")
        
        pax_count_str = st.text_input("Passengers Count", value="1", key="pax_count_main")
        try:
            pax_count = int(pax_count_str) if pax_count_str.strip() else 1
        except:
            pax_count = 1
        
        pax_names_list = []
        pas = ""
        if pax_count > 0 and pax_count <= 20:
            for i in range(int(pax_count)):
                nm = st.text_input(f"Passenger {i+1}", key=f"pax_{i}_{st.session_state.table_version}")
                if nm.strip():
                    pax_names_list.append(nm.strip())
            pas = "\n".join(pax_names_list)
        elif pax_count > 20:
            up = st.file_uploader("Upload Excel", type=["xlsx","xls","csv"], key="pax_excel_main")
            if up is not None:
                try:
                    if up.name.lower().endswith(".csv"):
                        df_up = pd.read_csv(up)
                    else:
                        df_up = pd.read_excel(up)
                    pax_names_list = df_up.iloc[:,0].dropna().astype(str).map(lambda x: x.strip()).tolist()
                    pax_names_list = [x for x in pax_names_list if x]
                    pas = "\n".join(pax_names_list)
                    pax_count = len(pax_names_list)
                except Exception as e:
                    st.error(f"{e}")

        hotel=st.selectbox("Hotel *", options=hotels_list if hotels_list else [""], key="hotel_main")

        rooms_count_str = st.text_input("Rooms Count", value="1", key="rooms_count_main")
        try:
            rooms_count = int(rooms_count_str) if rooms_count_str.strip() else 1
        except:
            rooms_count = 1
        
        rooms_list = []
        rooms_str = ""
        if rooms_count > 0 and rooms_count <= 20:
            for i in range(int(rooms_count)):
                rm = st.text_input(f"Room {i+1} Type", key=f"room_{i}_{st.session_state.table_version}")
                if rm.strip():
                    rooms_list.append(rm.strip())
            rooms_str = "\n".join(rooms_list)

        ed=st.date_input("Check-in", datetime.now()+timedelta(days=1), key="ed_main")
        nights=st.text_input("Nights", value="", key="nights_main")
        try: nights_val=int(nights) if nights else 0
        except: nights_val=0
        xd=ed+timedelta(days=nights_val)
        st.caption(f"Check-out: {xd}")
        pn_s=st.text_input("Price per Night $", key="pn_main")
        flight_s=st.text_input("Flight $", key="flight_main")
        trans_s=st.text_input("Transport $", key="trans_main")
        sell_s=st.text_input("Selling Price $ *", key="sell_main")
        pn=to_f(pn_s); flight_p=to_f(flight_s); trans_p=to_f(trans_s); sell=to_f(sell_s)

        hotel_total = (pn * nights_val * rooms_count) if pn and nights_val and rooms_count else 0
        if hotel_total:
            st.caption(f"Hotel Total: {rooms_count} x {nights_val} x ${pn} = ${hotel_total}")
        
        if st.button("SAVE SALE", type="primary", width='stretch', key="save_main"):
            if not comp.strip() or not hotel.strip() or not pas.strip(): 
                st.error("Fill required")
            else:
                try:
                    ws=get_gspread_sheet()
                    if ws:
                        row_dict = {h: "" for h in SHEET_HEADER}
                        row_dict["ID"] = str(int(datetime.now().timestamp()))
                        row_dict["Agent"] = comp
                        row_dict["Passengers"] = pas
                        row_dict["Passengers Count"] = str(int(pax_count))
                        row_dict["Hotel"] = hotel
                        row_dict["Rooms"] = str(int(rooms_count))
                        row_dict["Room Type"] = rooms_str
                        row_dict["Check-in"] = ed.strftime("%Y-%m-%d")
                        row_dict["Nights"] = str(nights_val)
                        row_dict["Check-out"] = xd.strftime("%Y-%m-%d")
                        row_dict["Price Night"] = str(pn) if pn else ""
                        row_dict["Hotel Total"] = str(hotel_total) if hotel_total else ""
                        row_dict["Flight $"] = str(flight_p) if flight_p else ""
                        row_dict["Transport $"] = str(trans_p) if trans_p else ""
                        row_dict["Sell Price"] = str(sell) if sell else ""
                        row_dict["Sale Date"] = sd.strftime("%Y-%m-%d")
                        row_dict["Employee"] = emp
                        
                        new_row = [row_dict.get(h,"") for h in SHEET_HEADER]
                        ws.append_row(new_row, value_input_option='USER_ENTERED')
                        st.success(f"✅ {row_dict['ID']} Saved"); 
                        st.session_state.table_version+=1; 
                        st.rerun()
                except Exception as e: st.error(f"{e}")

    with r:
        search_val=st.text_input("Search", placeholder="Search...", key="search_main")
        sheet=get_gspread_sheet()
        if not sheet: st.error("Sheet not connected"); st.stop()
        all_vals=sheet.get_all_values()
        if len(all_vals)<2: df_raw=pd.DataFrame()
        else:
            header=all_vals[0]; rows=all_vals[1:]
            df_raw=pd.DataFrame([r + [""]*(len(header)-len(r)) for r in rows], columns=header)
            df_raw["_sheet_row"]=[i+2 for i in range(len(df_raw))]
            if search_val.strip():
                s=search_val.lower()
                df_raw=df_raw[df_raw.apply(lambda row: s in str(row.values).lower(), axis=1)]
        event=st.dataframe(df_raw.drop(columns=["_sheet_row"], errors='ignore') if not df_raw.empty else df_raw, width='stretch', height=650, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"main_table_{st.session_state.table_version}")
        st.markdown(f"**Total: {len(df_raw)}**")
        selected_rows=event.selection.rows if hasattr(event, 'selection') else []
        selected_ids=df_raw.iloc[selected_rows]["_sheet_row"].tolist() if selected_rows and not df_raw.empty else []
        if st.button("Edit", width='stretch', key="edit_main"):
            if len(selected_ids)!=1: st.error("حدد سطر واحد")
            else: edit_dialog(int(selected_ids[0]))
with t2:
    st.markdown("### 💰 Payments")
    try:
        ws=get_gspread_sheet("Payments")
        df=pd.DataFrame(ws.get_all_records()) if ws else pd.DataFrame()
        st.dataframe(df, width='stretch')
    except Exception as e: st.error(f"{e}")

with t3:
    conn=sqlite3.connect(DB)
    conn.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT PRIMARY KEY)")
    conn.commit(); conn.close()
    c1,c2=st.columns(2)
    with c1:
        st.markdown("#### 👥 Agents")
        with st.form(key="f_agents_final", clear_on_submit=True):
            na=st.text_input("Agent name", placeholder="Agent name...", label_visibility="collapsed")
            if st.form_submit_button("Add Agent", width='stretch') and na.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO agents (name) VALUES (?)", (na.strip().upper(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB)
        try: dfa=pd.read_sql("SELECT name as Agents FROM agents ORDER BY name", conn)
        except: dfa=pd.DataFrame(columns=["Agents"])
        conn.close()
        st.dataframe(dfa, width='stretch', height=250, hide_index=True)
    with c2:
        st.markdown("#### 🏨 Hotels")
        with st.form(key="f_hotels_final", clear_on_submit=True):
            nh=st.text_input("Hotel name", placeholder="Hotel name...", label_visibility="collapsed")
            if st.form_submit_button("Add Hotel", width='stretch') and nh.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO hotels (name) VALUES (?)", (nh.strip(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB)
        try: dfh=pd.read_sql("SELECT name as Hotels FROM hotels ORDER BY name", conn)
        except: dfh=pd.DataFrame(columns=["Hotels"])
        conn.close()
        st.dataframe(dfh, width='stretch', height=250, hide_index=True)
