import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import os, re, threading

st.set_page_config(layout="wide", page_title="hotrigo")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE_DIR, "hotrigo.db")
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

def init_db():
    conn = sqlite3.connect(DB, check_same_thread=False)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        Agent TEXT, Passengers TEXT, Passengers_Count INTEGER,
        Hotel TEXT, Rooms INTEGER, Room_Type TEXT,
        Checkin TEXT, Nights INTEGER, Checkout TEXT,
        Price_Night REAL, Hotel_Total REAL, Flight REAL, Transport REAL,
        Sell_Price REAL, Cost REAL, Profit REAL,
        Sale_Date TEXT, Voucher_No TEXT, Notes TEXT,
        Airline TEXT, Employee TEXT, Dep_Time TEXT, Ret_Time TEXT,
        Flight_No_Dep TEXT, Flight_No_Ret TEXT, Transport_Co TEXT
    )""")
    c.execute("CREATE TABLE IF NOT EXISTS Agents_Balance (ID INTEGER PRIMARY KEY AUTOINCREMENT, Agent TEXT UNIQUE, Total REAL DEFAULT 0, Total_Pay REAL DEFAULT 0, Balance REAL DEFAULT 0, Note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS HOTELS (ID INTEGER PRIMARY KEY AUTOINCREMENT, Hotel TEXT UNIQUE, Total REAL DEFAULT 0, Total_Pay REAL DEFAULT 0, Balance REAL DEFAULT 0, Note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS Airlines (ID INTEGER PRIMARY KEY AUTOINCREMENT, Airline TEXT UNIQUE, Total REAL DEFAULT 0, Total_Pay REAL DEFAULT 0, Balance REAL DEFAULT 0, Note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS TransportCo (ID INTEGER PRIMARY KEY AUTOINCREMENT, Company TEXT UNIQUE, Total REAL DEFAULT 0, Total_Pay REAL DEFAULT 0, Balance REAL DEFAULT 0, Note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS Payments (ID INTEGER PRIMARY KEY AUTOINCREMENT, Date TEXT, Agent TEXT, Amount REAL, Note TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT UNIQUE)")
    conn.commit()
    conn.close()

init_db()

if "table_version" not in st.session_state:
    st.session_state.table_version = 0

def load_list_sql(table, col):
    try:
        conn = sqlite3.connect(DB)
        cur = conn.cursor()
        if table == "Agents_Balance": t = "Agents_Balance"; c = "Agent"
        elif table == "HOTELS": t = "HOTELS"; c = "Hotel"
        elif table == "Airlines": t = "Airlines"; c = "Airline"
        elif table == "TransportCo": t = "TransportCo"; c = "Company"
        else: t = table; c = col
        cur.execute(f"SELECT {c} FROM {t} WHERE {c} IS NOT NULL AND {c}!='' ORDER BY {c}")
        rows = [r[0].strip() for r in cur.fetchall() if r[0] and r[0].strip()]
        conn.close()
        seen=set(); clean=[]
        for v in rows:
            low=v.lower()
            if low not in seen:
                seen.add(low)
                clean.append(v)
        return clean
    except:
        return []

def load_lists():
    v = st.session_state.get("table_version", 0)
    agents = load_list_sql("Agents_Balance", "Agent")
    hotels = load_list_sql("HOTELS", "Hotel")
    return agents, hotels

@st.dialog("Edit Booking")
def edit_dialog(row_id):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT * FROM bookings WHERE id=?", (row_id,))
    row = cur.fetchone()
    cols = [d[0] for d in cur.description]
    conn.close()
    if not row: return
    d = dict(zip(cols, row))
    st.info(f"Editing #{row_id}")
    e_comp=st.text_input("Agent", value=d.get("Agent",""), key=f"ec_{row_id}")
    e_pas=st.text_area("Passengers", value=d.get("Passengers",""), key=f"ep_{row_id}")
    e_hotel=st.text_input("Hotel", value=d.get("Hotel",""), key=f"eh_{row_id}")
    if st.button("Save", type="primary", key=f"es_{row_id}"):
    if not e_comp or not str(e_comp).strip():
        st.error("Agent is required")
    else:
        conn = sqlite3.connect(DB)
        conn.execute("UPDATE bookings SET Agent=?, Passengers=?, Hotel=? WHERE id=?", (str(e_comp).strip(), str(e_pas).strip(), str(e_hotel).strip(), row_id))
        conn.commit()
        conn.close()
        st.session_state.table_version += 1
        st.rerun()
st.markdown("## ✈️ hotrigo | SQL - Server Ready ✅")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])

with t1:
    l,r=st.columns([1, 4.8])
    with l:
        enable_arrow_enter()
        sd=st.date_input("Sale Date", datetime.now(), key="sd_main")
        emp=st.text_input("Sales Employee *", key="emp_main")
        agents_list, hotels_list = load_lists()
        airlines_list = load_list_sql("Airlines", "Airline")
        transport_list = load_list_sql("TransportCo", "Company")

        comp_options = [""] + sorted(agents_list) if agents_list else [""]
        comp = st.selectbox("Agent *", options=comp_options, index=0, key="comp_main")

        pax_count_str = st.text_input("Passengers Count", value="1", key="pax_count_main")

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
            st.caption(f"Hotel: ${hotel_total:.0f} | Flight: ${flight_p:.0f} | Transport: ${trans_p:.0f} | Cost: ${cost_val:.0f}")

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
            if not comp or not str(comp).strip() or not hotel or not str(hotel).strip() or not pas or not str(pas).strip(): 
                st.error("Fill required")
            else:
                try:
                    with lock:
                        conn = sqlite3.connect(DB)
                        cur = conn.cursor()
                        cur.execute("""INSERT INTO bookings 
                        (Agent, Passengers, Passengers_Count, Hotel, Rooms, Room_Type, Checkin, Nights, Checkout, Price_Night, Hotel_Total, Flight, Transport, Sell_Price, Cost, Profit, Sale_Date, Voucher_No, Notes, Airline, Employee, Dep_Time, Ret_Time, Flight_No_Dep, Flight_No_Ret, Transport_Co)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (comp, pas, int(pax_count), hotel, int(rooms_count), rooms_str, ed.strftime("%Y-%m-%d"), nights_val, xd.strftime("%Y-%m-%d"), pn, hotel_total, flight_p, trans_p, sell, cost_val, sell-cost_val, sd.strftime("%Y-%m-%d"), voucher_no, note, airline_sel, emp, dep_time, ret_time, flight_no_dep, flight_no_ret, transport_co_sel))
                        
                        try:
                            cur.execute("SELECT Total FROM Agents_Balance WHERE lower(Agent)=lower(?)", (comp.strip(),))
                            r = cur.fetchone()
                            if r:
                                new_t = (r[0] or 0) + (sell or 0)
                                cur.execute("UPDATE Agents_Balance SET Total=?, Balance=Total-Total_Pay WHERE lower(Agent)=lower(?)", (new_t, comp.strip()))
                            else:
                                cur.execute("INSERT INTO Agents_Balance (Agent, Total, Balance) VALUES (?,?,?)", (comp.strip(), sell or 0, sell or 0))
                        except: pass
                        try:
                            cur.execute("SELECT Total FROM HOTELS WHERE lower(Hotel)=lower(?)", (hotel.strip(),))
                            r = cur.fetchone()
                            if r:
                                new_t = (r[0] or 0) + (hotel_total or 0)
                                cur.execute("UPDATE HOTELS SET Total=?, Balance=Total-Total_Pay WHERE lower(Hotel)=lower(?)", (new_t, hotel.strip()))
                            else:
                                cur.execute("INSERT INTO HOTELS (Hotel, Total, Balance) VALUES (?,?,?)", (hotel.strip(), hotel_total or 0, hotel_total or 0))
                        except: pass

                        conn.commit()
                        last_id = cur.lastrowid
                        conn.close()
                    st.success(f"✅ {last_id} Saved - {len(pax_names_list)} Passengers") 
                    st.session_state.table_version+=1
                    st.session_state.show_more=False
                    st.rerun()
                except Exception as e: st.error(f"{e}")

    with r:
        search_val=st.text_input("Search", placeholder="Search...", key="search_main")
        conn = sqlite3.connect(DB)
        try:
            df_raw = pd.read_sql("SELECT * FROM bookings ORDER BY id DESC", conn)
        except:
            df_raw = pd.DataFrame()
        conn.close()
        if not df_raw.empty and search_val.strip():
            s=search_val.lower()
            df_raw=df_raw[df_raw.apply(lambda row: s in str(row.values).lower(), axis=1)]
        event=st.dataframe(df_raw, width='stretch', height=650, hide_index=True, on_select="rerun", selection_mode="multi-row", key=f"main_table_{st.session_state.table_version}")
        st.markdown(f"**Total: {len(df_raw)}**")
        selected_rows=event.selection.rows if hasattr(event, 'selection') else []
        selected_ids=[int(df_raw.iloc[i]["id"]) for i in selected_rows] if selected_rows and not df_raw.empty else []
        if st.button("Edit", width='stretch', key="edit_main"):
            if len(selected_ids)!=1: st.error("Select one row")
            else: edit_dialog(int(selected_ids[0]))

with t2:
    st.markdown("### 💰 Payments")
    try:
        conn = sqlite3.connect(DB)
        df = pd.read_sql("SELECT * FROM Payments ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df, width='stretch')
    except Exception as e: st.error(f"{e}")

with t3:
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown("#### 👥 Agents")
        with st.form(key="f_agents_final", clear_on_submit=True):
            na = st.text_input("Agent name", placeholder="", label_visibility="collapsed")
            if st.form_submit_button("Add Agent", width='stretch') and na.strip():
                conn = sqlite3.connect(DB)
                conn.execute("INSERT OR IGNORE INTO Agents_Balance (Agent, Total, Total_Pay, Balance) VALUES (?,?,?,?)", (na.strip(), 0, 0, 0))
                conn.commit()
                conn.close()
                st.session_state.table_version += 1
                st.rerun()
        try:
            conn = sqlite3.connect(DB)
            dfa = pd.read_sql("SELECT * FROM Agents_Balance ORDER BY Agent", conn)
            conn.close()
        except:
            dfa = pd.DataFrame(columns=["ID", "Agent"])
        st.dataframe(dfa, width='stretch', height=400, hide_index=True)

    with c2:
        st.markdown("#### 🏨 Hotels")
        with st.form(key="f_hotels_final", clear_on_submit=True):
            nh = st.text_input("Hotel name", placeholder="", label_visibility="collapsed")
            if st.form_submit_button("Add Hotel", width='stretch') and nh.strip():
                conn = sqlite3.connect(DB)
                conn.execute("INSERT OR IGNORE INTO HOTELS (Hotel, Total, Total_Pay, Balance) VALUES (?,?,?,?)", (nh.strip(), 0, 0, 0))
                conn.commit()
                conn.close()
                st.session_state.table_version += 1
                st.rerun()
        try:
            conn = sqlite3.connect(DB)
            dfh = pd.read_sql("SELECT * FROM HOTELS ORDER BY Hotel", conn)
            conn.close()
        except:
            dfh = pd.DataFrame(columns=["ID", "Hotel"])
        st.dataframe(dfh, width='stretch', height=400, hide_index=True)

    with c3:
        st.markdown("#### 🚌 Transport")
        with st.form(key="f_trans_final", clear_on_submit=True):
            nt = st.text_input("Transport name", placeholder="", label_visibility="collapsed")
            if st.form_submit_button("Add Transport", width='stretch') and nt.strip():
                conn = sqlite3.connect(DB)
                conn.execute("INSERT OR IGNORE INTO TransportCo (Company) VALUES (?)", (nt.strip(),))
                conn.commit()
                conn.close()
                st.session_state.table_version += 1
                st.rerun()
        try:
            conn = sqlite3.connect(DB)
            df_t = pd.read_sql("SELECT * FROM TransportCo ORDER BY Company", conn)
            conn.close()
        except:
            df_t = pd.DataFrame(columns=["ID", "Company"])
        st.dataframe(df_t, width='stretch', height=400, hide_index=True)

    with c4:
        st.markdown("#### ✈️ Airlines")
        with st.form(key="f_air_final", clear_on_submit=True):
            nl = st.text_input("Airline name", placeholder="", label_visibility="collapsed")
            if st.form_submit_button("Add Airline", width='stretch') and nl.strip():
                conn = sqlite3.connect(DB)
                conn.execute("INSERT OR IGNORE INTO Airlines (Airline) VALUES (?)", (nl.strip(),))
                conn.commit()
                conn.close()
                st.session_state.table_version += 1
                st.rerun()
        try:
            conn = sqlite3.connect(DB)
            dfa2 = pd.read_sql("SELECT * FROM Airlines ORDER BY Airline", conn)
            conn.close()
        except:
            dfa2 = pd.DataFrame(columns=["ID", "Airline"])
        st.dataframe(dfa2, width='stretch', height=400, hide_index=True)
