import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import os, re, threading
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

st.set_page_config(layout="wide", page_title="hotrigo")
SHEET_ID_FALLBACK = "1WyJlLeChys_qh_qCxjFUZBq-FlhgHbhBaizMcg21Zqc"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "hotrigo.db")
SHEET_HEADER = ["ID","Agent","Passengers","Passengers Count","Hotel","Rooms","Room Type","Check-in","Nights","Check-out","Price Night","Hotel Total","Flight $","Transport $","Sell Price","Cost","Profit","Sale Date","Voucher No","Notes","Airline","Employee","Dep Time","Ret Time","Flight No Dep","Flight No Ret","Transport Co"]
lock = threading.Lock()

import streamlit.components.v1 as components

def enable_arrow_enter():
    components.html("""
    <script>
    const doc = window.parent.document;
    function getInputs(){
        return Array.from(doc.querySelectorAll('input[type="text"], input[type="number"], textarea, input[type="date"]'))
               .filter(el => el.offsetParent !== null && !el.disabled);
    }
    doc.addEventListener('keydown', function(e){
        const keys = ['Enter','ArrowDown','ArrowUp','Tab'];
        if(!keys.includes(e.key)) return;
        const active = doc.activeElement;
        const inputs = getInputs();
        const idx = inputs.indexOf(active);
        if(idx === -1) return;
        if(active.tagName === 'TEXTAREA' && e.key === 'Enter' && e.shiftKey) return;
        e.preventDefault();
        let next = idx;
        if(e.key === 'Enter' || e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)){
            next = idx + 1;
        } else if(e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)){
            next = idx - 1;
        }
        if(next >=0 && next < inputs.length){
            inputs[next].focus();
            if(inputs[next].select) inputs[next].select();
        }
    }, true);
    </script>
    """, height=0, width=0)

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

@st.cache_resource
def get_spreadsheet():
    client = get_gspread_client()
    sid = get_sheet_id_clean()
    try:
        return client.open("HOTRIGO_DATABASE")
    except:
        return client.open_by_key(sid)

def get_gspread_sheet(worksheet_name=None):
    try:
        ss = get_spreadsheet()
        if worksheet_name:
            try: return ss.worksheet(worksheet_name)
            except: return ss.add_worksheet(title=worksheet_name, rows=2000, cols=30)
        return ss.sheet1
    except Exception as e:
        st.error(f"Sheet Error: {e}")
        return None

@st.cache_data(ttl=600)
def load_list_sheet(_version, name):
    try:
        return [x.strip() for x in get_gspread_sheet(name).col_values(1)[1:] if x.strip()]
    except:
        return []

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
            st.session_state.table_version+=1
            st.rerun()
        except Exception as e: st.error(str(e))

st.markdown("## ✈️ hotrigo | Sheets Sync ✅")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])

@st.dialog("Confirm Sale")
def confirm_sale_dialog(row_dict, new_row):
    st.write(f"**Agent:** {row_dict['Agent']}")
    st.write(f"**Hotel:** {row_dict['Hotel']} - {row_dict['Nights']} Nights")
    st.write(f"**Passengers:** {row_dict['Passengers Count']}")
    st.write(f"**Sell:** ${row_dict['Sell Price']} | **Cost:** ${row_dict['Cost']} | **Profit:** ${row_dict['Profit']}")
    if row_dict.get("Voucher No"): st.write(f"**Voucher:** {row_dict['Voucher No']}")
    if row_dict.get("Notes"): st.write(f"**Notes:** {row_dict['Notes']}")
    if row_dict.get("Airline"): 
        st.write(f"**Airline:** {row_dict['Airline']} | Dep: {row_dict['Dep Time']} Ret: {row_dict['Ret Time']}")
    if row_dict.get("Flight No Dep"): 
        st.write(f"**Flight:** {row_dict['Flight No Dep']} -> {row_dict['Flight No Ret']}")
    if row_dict.get("Transport Co"): 
        st.write(f"**Transport:** {row_dict['Transport Co']}")
    st.divider()
    c1,c2 = st.columns(2)
    with c1:
        if st.button("✅ Confirm Save", type="primary", width='stretch', key="confirm_save_dialog"):
            ws=get_gspread_sheet()
            ws.append_row(new_row, value_input_option='USER_ENTERED')
            st.success(f"✅ {row_dict['ID']} Saved")
            st.session_state.table_version+=1
            st.session_state.show_more=False
            st.rerun()
    with c2:
        if st.button("❌ Cancel", width='stretch', key="cancel_save_dialog"):
            st.rerun()

with t1:
    l,r=st.columns([1, 4.8])
    with l:
        enable_arrow_enter()
        sd=st.date_input("Sale Date", datetime.now(), key="sd_main")
        emp=st.text_input("Sales Employee *", key="emp_main")
        agents_list, hotels_list = load_lists()
        airlines_list = load_list_sheet(st.session_state.table_version, "Airlines")
        transport_list = load_list_sheet(st.session_state.table_version, "TransportCo")

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
        cost_val = hotel_total + flight_p + trans_p

        if cost_val > 0:
            st.caption(f"فندق: ${hotel_total:.0f} | طيران: ${flight_p:.0f} | نقل: ${trans_p:.0f}")
            st.caption(f"توتال الكوست علينا: ${cost_val:.0f}")

        note = st.text_input("Notes", key="note_main")
        voucher_no = st.text_input("Voucher No", key="voucher_main")

        if "show_more" not in st.session_state: st.session_state.show_more=False
        if st.button("View More ⏬" if not st.session_state.show_more else "View Less ⏫", key="view_more_btn"):
            st.session_state.show_more = not st.session_state.show_more

        dep_time=""; ret_time=""; flight_no_dep=""; flight_no_ret=""; airline_sel=""; transport_co_sel=""
        if st.session_state.show_more:
            with st.container(border=True):
                airline_sel = st.selectbox("Airline *", options=[""]+airlines_list, key="airline_more")
                transport_co_sel = st.selectbox("Transport Co *", options=[""]+transport_list, key="transport_co_more")
                dep_time = st.text_input("Dep Time", key="dep_time_more", placeholder="10:30")
                ret_time = st.text_input("Ret Time", key="ret_time_more", placeholder="18:00")
                flight_no_dep = st.text_input("Airport Dep / Flight No Dep", key="flight_no_dep_more")
                flight_no_ret = st.text_input("Airport Ret / Flight No Ret", key="flight_no_ret_more")
        
        if st.button("SAVE SALE", type="primary", width='stretch', key="save_main"):
            if not comp.strip() or not hotel.strip() or not pas.strip(): 
                st.error("Fill required")
            elif st.session_state.show_more and airline_sel and airline_sel not in airlines_list:
                st.error(f"Airline '{airline_sel}' مو معرفة! لازم تعرفها اول بشيت Airlines")
            elif st.session_state.show_more and transport_co_sel and transport_co_sel not in transport_list:
                st.error(f"Transport Co '{transport_co_sel}' مو معرفة! لازم تعرفها اول بشيت TransportCo")
            else:
                try:
                    with lock:
                        ws=get_gspread_sheet()
                        if ws:
                            row_dict = {h: "" for h in SHEET_HEADER}
                            all_ids = ws.col_values(1)[1:]
                            ids = [int(x) for x in all_ids if str(x).isdigit() and int(x) < 1000000]
                            row_dict["ID"] = str(max(ids)+1 if ids else 1)
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
                            row_dict["Cost"] = str(cost_val) if cost_val else ""
                            row_dict["Profit"] = str(sell - cost_val) if sell else ""
                            row_dict["Notes"] = note
                            row_dict["Voucher No"] = voucher_no
                            row_dict["Sale Date"] = sd.strftime("%Y-%m-%d")
                            row_dict["Employee"] = emp
                            row_dict["Airline"] = airline_sel if st.session_state.show_more else ""
                            row_dict["Dep Time"] = dep_time if st.session_state.show_more else ""
                            row_dict["Ret Time"] = ret_time if st.session_state.show_more else ""
                            row_dict["Flight No Dep"] = flight_no_dep if st.session_state.show_more else ""
                            row_dict["Flight No Ret"] = flight_no_ret if st.session_state.show_more else ""
                            row_dict["Transport Co"] = transport_co_sel if st.session_state.show_more else ""
                            
                            new_row = [row_dict.get(h,"") for h in SHEET_HEADER]
                            ws.append_row(new_row, value_input_option='USER_ENTERED')
                    st.success(f"✅ {row_dict['ID']} Saved") 
                    st.session_state.table_version+=1
                    st.session_state.show_more=False
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
    conn.execute("CREATE TABLE IF NOT EXISTS transports (name TEXT PRIMARY KEY)")
    conn.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT PRIMARY KEY)")
    conn.commit(); conn.close()
    
    c1,c2,c3,c4=st.columns(4)
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
        st.dataframe(dfa, width='stretch', height=400, hide_index=True)
        
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
        st.dataframe(dfh, width='stretch', height=400, hide_index=True)

    with c3:
        st.markdown("#### 🚌 Transport")
        with st.form(key="f_trans_final", clear_on_submit=True):
            nt=st.text_input("Transport name", placeholder="Transport company...", label_visibility="collapsed")
            if st.form_submit_button("Add Transport", width='stretch') and nt.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO transports (name) VALUES (?)", (nt.strip(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB)
        try: dft=pd.read_sql("SELECT name as Transport FROM transports ORDER BY name", conn)
        except: dft=pd.DataFrame(columns=["Transport"])
        conn.close()
        st.dataframe(dft, width='stretch', height=400, hide_index=True)
        
    with c4:
        st.markdown("#### ✈️ Airlines")
        with st.form(key="f_air_final", clear_on_submit=True):
            nl=st.text_input("Airline name", placeholder="Airline name...", label_visibility="collapsed")
            if st.form_submit_button("Add Airline", width='stretch') and nl.strip():
                conn=sqlite3.connect(DB)
                try: conn.execute("INSERT INTO airlines (name) VALUES (?)", (nl.strip(),)); conn.commit()
                except: pass
                conn.close(); st.rerun()
        conn=sqlite3.connect(DB)
        try: dfa2=pd.read_sql("SELECT name as Airlines FROM airlines ORDER BY name", conn)
        except: dfa2=pd.DataFrame(columns=["Airlines"])
        conn.close()
        st.dataframe(dfa2, width='stretch', height=400, hide_index=True)
