import streamlit as st
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import streamlit.components.v1 as components
import os, io, re, json
from pathlib import Path

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
except:
    os.system("pip install reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

DB = os.path.join(os.path.dirname(__file__), "hotrigo.db")

def init():
    conn=sqlite3.connect(DB, check_same_thread=False)
    c=conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS bookings (id INTEGER PRIMARY KEY AUTOINCREMENT, sale_date TEXT, entry_date TEXT, exit_date TEXT, company TEXT, passengers TEXT, hotel TEXT, nights INTEGER, price_night REAL, hotel_total REAL, flight REAL, transport REAL, sell REAL, cost REAL, profit REAL, voucher TEXT, notes TEXT, airline TEXT, emp TEXT, flight_dep_time TEXT, flight_ret_time TEXT, room_type TEXT, transport_company TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS hotels (name TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS airlines (name TEXT UNIQUE)")
    c.execute("CREATE TABLE IF NOT EXISTS transport_companies (name TEXT UNIQUE)")
    cols = [x[1] for x in c.execute("PRAGMA table_info(bookings)").fetchall()]
    for col in ["flight_dep_time","flight_ret_time","airline","emp","room_type","transport_company"]:
        if col not in cols:
            c.execute(f"ALTER TABLE bookings ADD COLUMN {col} TEXT")
    conn.commit(); conn.close()
init()

if "pending" not in st.session_state: st.session_state.pending=None
if "do_clear" not in st.session_state: st.session_state.do_clear=False
if st.session_state.do_clear:
    for k in ["emp","pas","comp","hotel","pn","fl","tr","sell","airline","notes","vno","nights","ed","sd","dep_time","ret_time","room_type","transport_co"]:
        if k in st.session_state:
            try: del st.session_state[k]
            except: pass
    st.session_state.do_clear=False
    st.session_state.pending=None

def to_f(s):
    try: return float(str(s).replace(",","").strip()) if str(s).strip()!="" else 0.0
    except: return 0.0

def smart_match(input_val, full_list, upper_list):
    v = input_val.strip().upper()
    if not v or v=="0":
        return "", True
    if v in upper_list:
        idx = upper_list.index(v)
        return full_list[idx], True
    for i, name in enumerate(upper_list):
        if name.startswith(v):
            return full_list[i], True
    for i, name in enumerate(upper_list):
        if v in name:
            return full_list[i], True
    return input_val, False

def sanitize_filename(name):
    name = str(name).split('\n')[0].strip()
    name = re.sub(r'[\\/*?:"<>|]', '', name).replace(' ', '_')
    return name[:60] if name else "Traveler"

def clear_filters():
    st.session_state.entry_date_filter=None
    st.session_state.exit_date_filter=None
    st.session_state.search=""

def generate_invoice_pdf(data, save_path=None):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.setFillColorRGB(0.1, 0.2, 0.4)
    c.rect(0, height-80, width, 80, fill=1, stroke=0)
    c.setFillColorRGB(1,1,1)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(30, height-50, "HOTRIGO - INVOICE")
    c.setFont("Helvetica", 10)
    c.drawString(30, height-68, f"Voucher: {data.get('voucher','')} | Date: {datetime.now().strftime('%Y-%m-%d')}")
    c.setFillColorRGB(0,0,0)
    y = height-120
    c.setFont("Helvetica-Bold", 14)
    c.drawString(30, y, f"Agent: {data.get('company','')}")
    y -= 20
    c.setFont("Helvetica", 11)
    airline_txt = data.get('airline','') if data.get('airline','') else "NO FLIGHT"
    transport_txt = data.get('transport_company','') if data.get('transport_company','') else "NO TRANSFER"
    c.drawString(30, y, f"Airline: {airline_txt} | Transport: {transport_txt}")
    y -= 25
    c.setFont("Helvetica-Bold", 12)
    c.drawString(30, y, "Passengers:")
    y -= 18
    c.setFont("Helvetica", 11)
    for name in str(data.get('passengers','')).strip().split('\n'):
        if name.strip():
            c.drawString(45, y, f"- {name.strip()}")
            y-=16
    y-=10
    c.setFont("Helvetica", 11)
    c.drawString(30, y, f"Room Type: {data.get('room_type','')} | Hotel: {data.get('hotel','')}")
    y-=20
    c.drawString(30, y, f"Check-in: {data.get('entry_date','')} | Nights: {data.get('nights','')} | Dep: {data.get('flight_dep_time','')} - Ret: {data.get('flight_ret_time','')}")
    y-=40
    c.setFillColorRGB(0.95,0.95,0.95); c.rect(30, y-10, width-60, 50, fill=1, stroke=0)
    c.setFillColorRGB(0,0,0); c.setFont("Helvetica-Bold", 18)
    c.drawString(40, y+15, f"Selling Price: ${float(data.get('sell',0)):,.2f}")
    c.showPage(); c.save()
    pdf_bytes=buffer.getvalue(); buffer.close()
    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "wb") as f: f.write(pdf_bytes)
    return pdf_bytes

st.set_page_config(page_title="hotrigo", page_icon="✈️", layout="wide")

conn=sqlite3.connect(DB)
agents_for_js=[x[0] for x in conn.execute("SELECT name FROM agents ORDER BY name").fetchall()]
hotels_for_js=[x[0] for x in conn.execute("SELECT name FROM hotels ORDER BY name").fetchall()]
airlines_for_js=[x[0] for x in conn.execute("SELECT name FROM airlines ORDER BY name").fetchall()]
transport_for_js=[x[0] for x in conn.execute("SELECT name FROM transport_companies ORDER BY name").fetchall()]
conn.close()

agents_upper=[a.upper() for a in agents_for_js]
hotels_upper=[h.upper() for h in hotels_for_js]
airlines_upper=[a.upper() for a in airlines_for_js]
transport_upper=[a.upper() for a in transport_for_js]

components.html(f"""
<script>
const doc = window.parent.document;
const AGENTS = {json.dumps(agents_for_js)};
const HOTELS = {json.dumps(hotels_for_js)};
const AIRLINES = {json.dumps(airlines_for_js)};
const TRANSPORT = {json.dumps(transport_for_js)};

function killAutofill() {{
  doc.querySelectorAll('input, textarea').forEach(inp=>{{
    inp.setAttribute('autocomplete','new-password');
    inp.setAttribute('data-form-type','other');
    inp.setAttribute('data-lpignore','true');
    inp.setAttribute('autocorrect','off');
    inp.setAttribute('spellcheck','false');
    if (inp.tagName==='INPUT' &&!inp.name.startsWith('no_autofill_')) {{
      inp.name = 'no_autofill_' + Math.random().toString(36).slice(2);
    }}
  }});
  doc.querySelectorAll('form').forEach(f=> f.setAttribute('autocomplete','off'));
}}
killAutofill();
setTimeout(killAutofill, 100);
setTimeout(killAutofill, 500);
setInterval(killAutofill, 1000);

function getFieldType(input) {{
  const cont = input.closest('div[data-testid="stTextInput"], div[data-testid="stTextArea"]');
  if (!cont) return null;
  const txt = (cont.innerText || '').toLowerCase();
  if (txt.includes('agent')) return 'AGENT';
  if (txt.includes('hotel')) return 'HOTEL';
  if (txt.includes('airline')) return 'AIRLINE';
  if (txt.includes('transport company') || txt.includes('transport co')) return 'TRANSPORT';
  if (txt.includes('passengers')) return 'PASSENGERS';
  if (txt.includes('room type')) return 'ROOM';
  if (txt.includes('employee')) return 'EMP';
  return 'OTHER';
}}

doc.addEventListener('focusin', (e)=>{{
  const t = e.target;
  if (!t || (t.tagName!=='INPUT' && t.tagName!=='TEXTAREA')) return;
  t.setAttribute('autocomplete','new-password');
  const type = getFieldType(t);
  if (['AGENT','HOTEL','AIRLINE','TRANSPORT','ROOM','EMP','OTHER'].includes(type) && t.tagName==='INPUT') {{
    setTimeout(()=>{{ try{{ t.select(); }}catch(_ ){{}} }}, 60);
  }}
}});

doc.addEventListener('click', (e)=>{{
  const t = e.target;
  if (!t || t.tagName!=='INPUT') return;
  const type = getFieldType(t);
  if (['AGENT','HOTEL','AIRLINE','TRANSPORT','ROOM','EMP','OTHER'].includes(type)) {{
    setTimeout(()=>{{ try{{ t.select(); }}catch(_ ){{}} }}, 10);
  }}
}});

function getFields() {{
  const els = Array.from(doc.querySelectorAll('input:not([type=hidden]), textarea'));
  return els.filter(e => e.offsetParent!== null &&!e.disabled && e.type!== 'checkbox' && e.type!== 'radio' && e.getClientRects().length>0);
}}

function setNativeValue(input, value) {{
  const lastValue = input.value;
  input.value = value;
  if (input._valueTracker) input._valueTracker.setValue(lastValue);
  try {{
    if (input.tagName==='TEXTAREA') {{
      const tSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      tSetter.call(input, value);
    }} else {{
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
      setter.call(input, value);
    }}
  }} catch(e) {{}}
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  input.dispatchEvent(new Event('change', {{ bubbles: true }}));
}}

function findBestMatch(val, list) {{
  val = val.toUpperCase().trim();
  if (!val || val=="0") return null;
  let exact = list.find(x => x.toUpperCase() === val);
  if (exact) return exact;
  let starts = list.find(x => x.toUpperCase().startsWith(val));
  if (starts) return starts;
  let contains = list.find(x => x.toUpperCase().includes(val));
  return contains || null;
}}

let activeList = null;
let activeIndex = -1;
let currentInput = null;

function closeList() {{
  if (activeList) {{ activeList.remove(); activeList=null; activeIndex=-1; currentInput=null; }}
}}

function moveToNext(input) {{
  const fields = getFields();
  let idx = fields.indexOf(input);
  if (idx===-1) {{
    const box = input.closest('div[data-testid="stDateInput"], div[data-testid="stNumberInput"]');
    if (box) {{ const inp = box.querySelector('input'); if (inp) idx = fields.indexOf(inp); }}
  }}
  if (idx!==-1 && idx+1 < fields.length) {{
    setTimeout(()=> {{
      const next = fields[idx+1];
      if (next) {{ next.focus(); next.select?.(); }}
    }}, 80);
  }}
}}

function findNearest(active, dir) {{
  const fields = getFields();
  const ar = active.getBoundingClientRect();
  const ax = ar.left + ar.width/2;
  const ay = ar.top + ar.height/2;
  let best = null;
  let bestScore = Infinity;
  for (let f of fields) {{
    if (f===active) continue;
    const r = f.getBoundingClientRect();
    const x = r.left + r.width/2;
    const y = r.top + r.height/2;
    const dx = x - ax;
    const dy = y - ay;
    if (dir==='right' && dx <= 20) continue;
    if (dir==='left' && dx >= -20) continue;
    if (dir==='down' && dy <= 15) continue;
    if (dir==='up' && dy >= -15) continue;
    if ((dir==='left' || dir==='right') && Math.abs(dy) > 120) continue;
    if ((dir==='up' || dir==='down') && Math.abs(dx) > 400) continue;
    let score = Math.hypot(dx, dy);
    if (dir==='right' || dir==='left') score = Math.abs(dx) + Math.abs(dy)*0.8;
    if (dir==='up' || dir==='down') score = Math.abs(dy) + Math.abs(dx)*0.8;
    if (score < bestScore) {{ bestScore=score; best=f; }}
  }}
  return best;
}}

function moveDir(active, dir) {{
  const target = findNearest(active, dir);
  if (target) {{
    setTimeout(()=>{{ target.focus(); target.select?.(); }}, 30);
    return true;
  }}
  return false;
}}

function createList(input, items) {{
  closeList();
  if (!items.length) return;
  currentInput = input;
  activeIndex = 0;
  const rect = input.getBoundingClientRect();
  const div = doc.createElement('div');
  div.style.position='fixed';
  div.style.left=rect.left+'px';
  div.style.top=(rect.bottom+2)+'px';
  div.style.width=rect.width+'px';
  div.style.maxHeight='200px';
  div.style.overflowY='auto';
  div.style.background='white';
  div.style.border='1px solid #ccc';
  div.style.borderRadius='6px';
  div.style.boxShadow='0 4px 12px rgba(0,0,0,0.3)';
  div.style.zIndex='999999999';
  items.forEach((txt,i) => {{
    const item = doc.createElement('div');
    item.textContent=txt;
    item.style.padding='12px';
    item.style.cursor='pointer';
    item.style.background = i===0? '#1976d2' : 'white';
    item.style.color = i===0? 'white' : 'black';
    item.style.fontWeight='bold';
    item.addEventListener('mousedown', (e) => {{
      e.preventDefault(); e.stopPropagation();
      setNativeValue(input, txt);
      closeList();
      moveToNext(input);
    }});
    item.addEventListener('mouseenter', () => {{ activeIndex=i; updateHighlight(); }});
    div.appendChild(item);
  }});
  doc.body.appendChild(div);
  activeList = div;
}}

function updateHighlight() {{
  if (!activeList) return;
  Array.from(activeList.children).forEach((el,i) => {{
    el.style.background = i===activeIndex? '#1976d2' : 'white';
    el.style.color = i===activeIndex? 'white' : 'black';
  }});
}}

doc.addEventListener('input', function(e) {{
  const input = e.target;
  if (!input || input.tagName!=='INPUT') return;
  const type = getFieldType(input);
  if (!type || type==='PASSENGERS') return;
  const val = input.value.trim().toUpperCase();
  if (val.length < 1 || val==="0") {{ closeList(); return; }}
  let list = type==='AGENT'? AGENTS : type==='HOTEL'? HOTELS : type==='AIRLINE'? AIRLINES : TRANSPORT;
  let filtered = list.filter(x => x.toUpperCase().includes(val)).slice(0,10);
  if (filtered.length) createList(input, filtered);
  else closeList();
}});

doc.addEventListener('keydown', function(e) {{
  const active = doc.activeElement;
  if (!active || (active.tagName!=='INPUT' && active.tagName!=='TEXTAREA')) return;

  const type = getFieldType(active);
  const isTextArea = active.tagName==='TEXTAREA';

  if (activeList && currentInput===active) {{
    if (e.key==='ArrowDown') {{ e.preventDefault(); activeIndex = Math.min(activeList.children.length-1, activeIndex+1); updateHighlight(); return; }}
    if (e.key==='ArrowUp') {{ e.preventDefault(); activeIndex = Math.max(0, activeIndex-1); updateHighlight(); return; }}
    if (e.key==='Enter') {{
      e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
      const chosen = activeList.children[activeIndex]?.textContent;
      if (chosen) {{ setNativeValue(active, chosen); closeList(); moveToNext(active); }}
      return;
    }}
    if (e.key==='Escape') {{ closeList(); return; }}
    if (e.key==='ArrowLeft' || e.key==='ArrowRight') {{ closeList(); }}
  }}

  if (isTextArea && type==='PASSENGERS') {{
    if (e.key==='ArrowDown') {{
      e.preventDefault(); e.stopPropagation();
      moveDir(active, 'down') || moveToNext(active);
      return;
    }}
    if (e.key==='ArrowUp') {{
      e.preventDefault(); e.stopPropagation();
      moveDir(active, 'up');
      return;
    }}
    if (e.key==='ArrowLeft') {{
      const pos = active.selectionStart;
      if (pos===0) {{ e.preventDefault(); moveDir(active, 'left'); return; }}
      return;
    }}
    if (e.key==='ArrowRight') {{
      const pos = active.selectionStart;
      const len = active.value.length;
      if (pos===len) {{ e.preventDefault(); moveDir(active, 'right'); return; }}
      return;
    }}
    return;
  }}

  if (e.key==='ArrowLeft') {{
    if (active.selectionStart!==0 || active.selectionEnd!==active.selectionStart) return;
    e.preventDefault(); e.stopPropagation();
    moveDir(active, 'left');
    return;
  }}
  if (e.key==='ArrowRight') {{
    if (active.selectionStart < active.value.length || active.selectionEnd!==active.selectionStart) return;
    e.preventDefault(); e.stopPropagation();
    moveDir(active, 'right') || moveToNext(active);
    return;
  }}
  if (e.key==='ArrowDown') {{
    e.preventDefault(); e.stopPropagation();
    if (!moveDir(active, 'down')) moveToNext(active);
    return;
  }}
  if (e.key==='ArrowUp') {{
    e.preventDefault(); e.stopPropagation();
    moveDir(active, 'up');
    return;
  }}

  if (e.key==='Enter' && type &&!activeList &&!isTextArea) {{
    let list = type==='AGENT'? AGENTS : type==='HOTEL'? HOTELS : type==='AIRLINE'? AIRLINES : TRANSPORT;
    let best = findBestMatch(active.value, list);
    if (best && active.value.toUpperCase()!== best.toUpperCase()) {{
      e.preventDefault();
      setNativeValue(active, best);
      closeList();
      moveToNext(active);
      return;
    }}
    if (type) {{
      e.preventDefault();
      closeList();
      moveToNext(active);
      return;
    }}
  }}

  if (e.key==='Enter') {{
    e.preventDefault(); e.stopPropagation();
    moveToNext(active);
  }}
}}, true);

doc.addEventListener('click', (e) => {{
  if (activeList &&!activeList.contains(e.target) && e.target!==currentInput) closeList();
}});
</script>
""", height=0)

@st.dialog("Delete", width="small")
def delete_dialog(ids):
    conn=sqlite3.connect(DB); conn.executemany("DELETE FROM bookings WHERE id=?", [(int(i),) for i in ids]); conn.commit(); conn.close(); st.rerun()

@st.dialog("Edit Booking", width="large")
def edit_dialog(row):
    st.info(f"Editing booking #{row[0]}")
    c1,c2=st.columns(2)
    with c1:
        e_sale=st.text_input("Sale Date", value=row[1], key="dlg_sale")
        e_comp=st.text_input("Agent *", value=row[4], key="dlg_comp", placeholder="")
        e_pas=st.text_area("Passengers", value=row[5], height=100, key="dlg_pas")
        e_room=st.text_input("Room Type", value=row[21] if len(row)>21 and row[21] else "", key="dlg_room", placeholder="")
        e_hotel=st.text_input("Hotel *", value=row[6], key="dlg_hotel", placeholder="")
    with c2:
        e_entry=st.text_input("Entry Date", value=row[2], key="dlg_en")
        e_exit=st.text_input("Exit Date", value=row[3], key="dlg_ex")
        e_sell=st.text_input("Selling Price $", value=str(row[12]), key="dlg_sell")
        e_dep=st.text_input("Departure Time", value=row[19] or "", key="dlg_dep", placeholder="10:30")
        e_ret=st.text_input("Return Time", value=row[20] or "", key="dlg_ret", placeholder="18:45")
        e_air=st.text_input("Airline (empty=no flight)", value=row[17] or "", key="dlg_air", placeholder="")
        e_trans_co=st.text_input("Transport Company (empty=no transfer)", value=row[22] if len(row)>22 and row[22] else "", key="dlg_transco", placeholder="")
        e_emp=st.text_input("Employee", value=row[18] or "", key="dlg_emp")

    if st.button("Save", type="primary", use_container_width=True):
        comp_full, comp_ok = smart_match(e_comp, agents_for_js, agents_upper)
        hotel_full, hotel_ok = smart_match(e_hotel, hotels_for_js, hotels_upper)
        is_no_flight = e_air.strip()=="" or e_air.strip()=="0"
        is_no_trans = e_trans_co.strip()=="" or e_trans_co.strip()=="0"
        air_full, air_ok = ("", True) if is_no_flight else smart_match(e_air, airlines_for_js, airlines_upper)
        trans_full, trans_ok = ("", True) if is_no_trans else smart_match(e_trans_co, transport_for_js, transport_upper)
        if not comp_ok:
            st.error(f"❌ Agent '{e_comp}' not found!"); return
        if not hotel_ok:
            st.error(f"❌ Hotel '{e_hotel}' not found!"); return
        if not air_ok:
            st.error(f"❌ Airline '{e_air}' not found!"); return
        if not trans_ok:
            st.error(f"❌ Transport '{e_trans_co}' not found!"); return
        conn=sqlite3.connect(DB)
        conn.execute("UPDATE bookings SET sale_date=?, company=?, passengers=?, room_type=?, hotel=?, entry_date=?, exit_date=?, sell=?, airline=?, notes=?, emp=?, voucher=?, nights=?, flight_dep_time=?, flight_ret_time=?, transport_company=? WHERE id=?",
                     (e_sale, comp_full, e_pas, e_room, hotel_full, e_entry, e_exit, to_f(e_sell), air_full, "", e_emp, "", int(5), e_dep, e_ret, trans_full, row[0]))
        conn.commit(); conn.close(); st.rerun()

@st.dialog("Invoice", width="large")
def invoice_dialog(row):
    conn=sqlite3.connect(DB); full=conn.execute("SELECT * FROM bookings WHERE id=?", (int(row[0]),)).fetchone(); conn.close()
    if not full: return
    data={"company":full[4],"passengers":full[5],"hotel":full[6],"room_type":full[21] if len(full)>21 else "","entry_date":full[2],"exit_date":full[3],"sell":full[12],"sale_date":full[1],"airline":full[17],"emp":full[18],"flight_dep_time":full[19],"flight_ret_time":full[20],"nights":full[7],"voucher":full[15],"transport_company":full[22] if len(full)>22 else ""}
    st.markdown(f"## Invoice - {data['company']}")
    for name in str(data['passengers']).split('\n'): st.markdown(f"- {name.strip()}")
    booking_num=data['voucher'] if data['voucher'] and str(data['voucher']).strip()!="" else f"BOOK-{full[0]}"
    filename=f"{booking_num}_{sanitize_filename(data['passengers'])}.pdf"
    full_path=Path.home() / "Desktop" / "invoice" / filename
    pdf_bytes=generate_invoice_pdf(data, save_path=str(full_path))
    st.success(f"Saved: {full_path}")
    st.download_button("Download PDF", data=pdf_bytes, file_name=filename, mime="application/pdf", use_container_width=True, type="primary")

st.markdown("## ✈️ hotrigo | tourism2020-hotrigo")
t1,t2,t3=st.tabs(["Sales", "Account Statement", "Agents & Hotels"])
with t1:
    l,r=st.columns([1, 4.8])
    with l:
        sd=st.date_input("Sale Date", datetime.now(), key="sd")
        emp=st.text_input("Sales Employee *", key="emp")
        comp=st.text_input("Agent *", key="comp", placeholder="")
        pas=st.text_area("Passengers *", height=90, key="pas", placeholder="One name per line")
        room_type=st.text_input("Room Type *", key="room_type", placeholder="SNG - DBL - TRP")
        hotel=st.text_input("Hotel *", key="hotel", placeholder="")
        ed=st.date_input("Check-in Date", datetime.now()+timedelta(days=1), key="ed")
        nights=st.number_input("Nights", 1, 30, 5, key="nights")
        xd=ed+timedelta(days=nights); st.caption(f"Check-out: {xd}")
        pn_s=st.text_input("Price per Night $", key="pn")
        fl_s=st.text_input("Flight $", key="fl")
        tr_s=st.text_input("Transport $", key="tr")
        sell_s=st.text_input("Selling Price $ *", key="sell")
        c_dep, c_ret=st.columns(2)
        with c_dep: dep_time=st.text_input("Departure Time", key="dep_time", placeholder="10:30")
        with c_ret: ret_time=st.text_input("Return Time", key="ret_time", placeholder="18:45")
        pn=to_f(pn_s); fl=to_f(fl_s); tr=to_f(tr_s); sell=to_f(sell_s)
        airline=st.text_input("Airline (empty=no flight)", key="airline", placeholder="")
        transport_co=st.text_input("Transport Company (empty=no transfer)", key="transport_co", placeholder="")
        notes=st.text_input("Note", key="notes")
        vno=st.text_input("Voucher No", key="vno")
        if st.button("SAVE SALE", type="primary", use_container_width=True):
            airline_val = airline.strip()
            transport_val = transport_co.strip()
            comp_full, comp_ok = smart_match(comp, agents_for_js, agents_upper)
            hotel_full, hotel_ok = smart_match(hotel, hotels_for_js, hotels_upper)
            is_no_flight = airline_val == "" or airline_val == "0"
            is_no_transport = transport_val == "" or transport_val == "0"
            airline_full, airline_ok = ("", True) if is_no_flight else smart_match(airline_val, airlines_for_js, airlines_upper)
            transport_full, transport_ok = ("", True) if is_no_transport else smart_match(transport_val, transport_for_js, transport_upper)
            if not comp.strip() or not hotel.strip() or not emp.strip() or not pas.strip():
                st.error("Fill required: Agent, Hotel, Employee, Passengers")
            elif not comp_ok:
                st.error(f"❌ Agent '{comp}' not found!")
            elif not hotel_ok:
                st.error(f"❌ Hotel '{hotel}' not found!")
            elif not airline_ok:
                st.error(f"❌ Airline '{airline}' not found! Leave empty or 0")
            elif not transport_ok:
                st.error(f"❌ Transport '{transport_co}' not found! Leave empty or 0")
            else:
                ht_tot=nights*pn; cost=ht_tot+fl+tr; profit=sell-cost
                st.session_state.pending={"sale_date":str(sd),"entry_date":str(ed),"exit_date":str(xd),"company":comp_full,"passengers":pas.strip(),"hotel":hotel_full,"room_type":room_type.strip(),"nights":int(nights),"price_night":float(pn),"hotel_total":float(ht_tot),"flight":float(fl),"transport":float(tr),"sell":float(sell),"cost":float(cost),"profit":float(profit),"voucher":vno,"notes":notes,"airline":airline_full,"emp":emp.strip(),"dep":dep_time.strip(),"ret":ret_time.strip(),"transport_company":transport_full}
        if st.session_state.pending:
            st.warning(f"{st.session_state.pending['company']} - {st.session_state.pending['passengers'].split(chr(10))[0]} - ${st.session_state.pending['sell']}")
            c1,c2=st.columns(2)
            with c1:
                if st.button("YES", type="primary", use_container_width=True):
                    d=st.session_state.pending
                    conn=sqlite3.connect(DB, check_same_thread=False)
                    conn.execute("INSERT INTO bookings (sale_date,entry_date,exit_date,company,passengers,hotel,nights,price_night,hotel_total,flight,transport,sell,cost,profit,voucher,notes,airline,emp,flight_dep_time,flight_ret_time,room_type,transport_company) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (d["sale_date"],d["entry_date"],d["exit_date"],d["company"],d["passengers"],d["hotel"],d["nights"],d["price_night"],d["hotel_total"],d["flight"],d["transport"],d["sell"],d["cost"],d["profit"],d["voucher"],d["notes"],d["airline"],d["emp"],d["dep"],d["ret"],d["room_type"],d["transport_company"]))
                    conn.commit(); conn.close(); st.session_state.do_clear=True; st.rerun()
            with c2:
                if st.button("NO", use_container_width=True):
                    st.session_state.pending=None; st.rerun()
    with r:
        col_f1, col_f2, col_f3=st.columns([1.2, 1.2, 1.3])
        with col_f1: entry_date_val=st.date_input("entry_date_filter", value=None, key="entry_date_filter", label_visibility="collapsed")
        with col_f2: exit_date_val=st.date_input("exit_date_filter", value=None, key="exit_date_filter", label_visibility="collapsed")
        with col_f3: st.button("Show All", use_container_width=True, on_click=clear_filters)
        b1, b2, b3, scol=st.columns([0.7, 0.7, 0.9, 1.8])
        with b1: del_btn=st.button("Delete", type="primary", use_container_width=True, key="del_small")
        with b2: edit_btn=st.button("Edit", use_container_width=True, key="edit_small")
        with b3: inv_btn=st.button("Invoice", use_container_width=True, key="inv_btn")
        with scol: search_val=st.text_input("Search", placeholder="Search...", label_visibility="collapsed", key="search")
        conn=sqlite3.connect(DB)
        base="SELECT id, sale_date, company, passengers, room_type, hotel, entry_date, exit_date, sell, airline, flight_dep_time, flight_ret_time, notes, emp, transport_company FROM bookings WHERE 1=1"
        if entry_date_val: base+=f" AND entry_date = '{entry_date_val}'"
        if exit_date_val: base+=f" AND exit_date = '{exit_date_val}'"
        if search_val.strip():
            s=search_val.strip()
            if s.isdigit(): base+=f" AND (id = {int(s)} OR voucher LIKE '%{s}%')"
            else: base+=f" AND (company LIKE '%{s}%' OR passengers LIKE '%{s}%' OR hotel LIKE '%{s}%' OR room_type LIKE '%{s}%' OR voucher LIKE '%{s}%' OR transport_company LIKE '%{s}%')"
        base+=" ORDER BY id DESC"
        df=pd.read_sql(base, conn); conn.close()
        if df.empty:
            display_df=pd.DataFrame(columns=["ID","Sale Date","Agent","Passengers","Room Type","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co","Delete"])
        else:
            display_df=df.copy()
            display_df.columns=["ID","Sale Date","Agent","Passengers","Room Type","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co"]
            display_df["Delete"]=False
        edited_df=st.data_editor(display_df, use_container_width=True, height=650, hide_index=True, key="editor_data",
            disabled=["ID","Sale Date","Agent","Passengers","Room Type","Hotel","Check-in","Check-out","Sell Price","Airline","Dep Time","Ret Time","Note","Employee","Transport Co"])
        st.markdown(f"**Total bookings: {len(df)}**")
        def get_selected_ids():
            return edited_df[edited_df["Delete"]==True]["ID"].tolist() if not edited_df.empty else []
        if del_btn:
            ids=get_selected_ids()
            if not ids: st.error("Check Delete first")
            else: delete_dialog(ids)
        if edit_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("Select one booking")
            else:
                conn=sqlite3.connect(DB); row=conn.execute("SELECT * FROM bookings WHERE id=?", (int(ids[0]),)).fetchone(); conn.close()
                if row: edit_dialog(row)
        if inv_btn:
            ids=get_selected_ids()
            if len(ids)!=1: st.error("Select one booking")
            else:
                conn=sqlite3.connect(DB); row=conn.execute("SELECT * FROM bookings WHERE id=?", (int(ids[0]),)).fetchone(); conn.close()
                if row: invoice_dialog(row)

with t2: st.write("Account Statement - coming soon")
with t3:
    c1,c2,c3,c4=st.columns(4)
    with c1:
        st.markdown("#### 👥 Agents")
        na=st.text_input("New Agent", key="na")
        if st.button("Add Agent", key="add_agent"):
            if na.strip():
                conn=sqlite3.connect(DB); conn.execute("INSERT OR IGNORE INTO agents VALUES (?)",(na.strip().upper(),)); conn.commit(); conn.close(); st.rerun()
        conn=sqlite3.connect(DB); agents_df=pd.read_sql("SELECT name FROM agents ORDER BY name", conn); conn.close()
        st.dataframe(agents_df, use_container_width=True, height=400)
    with c2:
        st.markdown("#### 🏨 Hotels")
        nh=st.text_input("New Hotel", key="nh")
        if st.button("Add Hotel", key="add_hotel"):
            if nh.strip():
                conn=sqlite3.connect(DB); conn.execute("INSERT OR IGNORE INTO hotels VALUES (?)",(nh.strip().upper(),)); conn.commit(); conn.close(); st.rerun()
        conn=sqlite3.connect(DB); hotels_df=pd.read_sql("SELECT name FROM hotels ORDER BY name", conn); conn.close()
        st.dataframe(hotels_df, use_container_width=True, height=400)
    with c3:
        st.markdown("#### ✈️ Airlines")
        nal=st.text_input("New Airline", key="nal")
        if st.button("Add Airline", key="add_airline"):
            if nal.strip():
                conn=sqlite3.connect(DB); conn.execute("INSERT OR IGNORE INTO airlines VALUES (?)",(nal.strip().upper(),)); conn.commit(); conn.close(); st.rerun()
        conn=sqlite3.connect(DB); airlines_df=pd.read_sql("SELECT name FROM airlines ORDER BY name", conn); conn.close()
        st.dataframe(airlines_df, use_container_width=True, height=400)
    with c4:
        st.markdown("#### 🚌 Transport Companies")
        ntr=st.text_input("New Transport Co", key="ntr")
        if st.button("Add Transport Co", key="add_transport"):
            if ntr.strip():
                conn=sqlite3.connect(DB); conn.execute("INSERT OR IGNORE INTO transport_companies VALUES (?)",(ntr.strip().upper(),)); conn.commit(); conn.close(); st.rerun()
        conn=sqlite3.connect(DB); transport_df=pd.read_sql("SELECT name FROM transport_companies ORDER BY name", conn); conn.close()
        st.dataframe(transport_df, use_container_width=True, height=400)