import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from components.timeline_dnd import timeline_dnd

DB_PATH = "trimming_schedule.db"

MENU_BASE_MINUTES = {
    ("C", "S", "LONG"): 120,
    ("C", "S", "SHORT"): 10,
    ("C", "M", "LONG"): 120,
    ("C", "M", "SHORT"): 30,
    ("C", "L", "LONG"): 120,
    ("C", "L", "SHORT"): 30,
    ("S", "S", "LONG"): 60,
    ("S", "S", "SHORT"): 20,
    ("S", "M", "LONG"): 60,
    ("S", "M", "SHORT"): 60,
    ("S", "L", "LONG"): 120,
    ("S", "L", "SHORT"): 120,
}
MENU_BASE_PRICES = {
    ("C", "S", "LONG"): 6000,
    ("C", "S", "SHORT"): 3000,
    ("C", "M", "LONG"): 7000,
    ("C", "M", "SHORT"): 3500,
    ("C", "L", "LONG"): 8500,
    ("C", "L", "SHORT"): 4500,
    ("S", "S", "LONG"): 4500,
    ("S", "S", "SHORT"): 2500,
    ("S", "M", "LONG"): 5500,
    ("S", "M", "SHORT"): 5000,
    ("S", "L", "LONG"): 7000,
    ("S", "L", "SHORT"): 7000,
}
DEFAULT_OPTIONS = [
    ("歯磨き", 5, 500), ("部分カット（1箇所）", 5, 500), ("肛門腺", 5, 500),
    ("耳掃除", 5, 500), ("エチケットカット（1箇所）", 5, 500), ("髭カット", 5, 500), ("爪切り", 10, 800),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_column(conn, table: str, column: str, ddl: str):
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY CHECK(id=1), business_open_time TEXT NOT NULL DEFAULT '09:00',
            business_close_time TEXT NOT NULL DEFAULT '19:00', buffer_minutes INTEGER NOT NULL DEFAULT 30,
            buffer_apply_to_last INTEGER NOT NULL DEFAULT 1, tax_rate_percent INTEGER NOT NULL DEFAULT 10,
            tax_rounding_mode TEXT NOT NULL DEFAULT 'FLOOR');
        CREATE TABLE IF NOT EXISTS menu_time_matrix (
            id INTEGER PRIMARY KEY AUTOINCREMENT, menu_kind TEXT NOT NULL, body_size TEXT NOT NULL,
            coat_type TEXT NOT NULL, minutes INTEGER NOT NULL, UNIQUE(menu_kind, body_size, coat_type));
        CREATE TABLE IF NOT EXISTS menu_price_matrix (
            id INTEGER PRIMARY KEY AUTOINCREMENT, menu_kind TEXT NOT NULL, body_size TEXT NOT NULL,
            coat_type TEXT NOT NULL, unit_price_excl_tax INTEGER NOT NULL, UNIQUE(menu_kind, body_size, coat_type));
        CREATE TABLE IF NOT EXISTS options_master (
            id INTEGER PRIMARY KEY AUTOINCREMENT, option_name TEXT NOT NULL UNIQUE,
            minutes INTEGER NOT NULL, unit_price_excl_tax INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, booking_date TEXT NOT NULL, fixed_start_time TEXT NOT NULL,
            customer_name TEXT NOT NULL, dog_name TEXT NOT NULL, body_size TEXT NOT NULL, coat_type TEXT NOT NULL,
            menu_type TEXT NOT NULL, shed_mat_flag INTEGER NOT NULL DEFAULT 0, notes TEXT,
            actual_end_time TEXT, actual_end_confirmed INTEGER NOT NULL DEFAULT 0, early_arrival_confirmed INTEGER NOT NULL DEFAULT 0,
            menu_unit_price_excl_tax INTEGER, options_unit_price_excl_tax_total INTEGER,
            subtotal_excl_tax_auto INTEGER NOT NULL DEFAULT 0, subtotal_excl_tax_manual_override INTEGER,
            discount_yen INTEGER NOT NULL DEFAULT 0, points_used_yen INTEGER NOT NULL DEFAULT 0,
            tax_yen INTEGER NOT NULL DEFAULT 0, subtotal_incl_tax_yen INTEGER NOT NULL DEFAULT 0,
            amount_due_yen INTEGER NOT NULL DEFAULT 0, payment_status TEXT NOT NULL DEFAULT 'UNPAID',
            points_granted INTEGER NOT NULL DEFAULT 0, extra_gap_buffer_minutes INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS booking_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id INTEGER NOT NULL, option_id INTEGER NOT NULL,
            qty INTEGER NOT NULL, minutes_total INTEGER NOT NULL, unit_price_excl_tax INTEGER NOT NULL,
            price_excl_tax_total INTEGER NOT NULL, FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
            FOREIGN KEY(option_id) REFERENCES options_master(id));
        """)
        cur.execute("INSERT OR IGNORE INTO settings(id) VALUES(1)")
        ensure_column(conn, "bookings", "extra_gap_buffer_minutes", "extra_gap_buffer_minutes INTEGER NOT NULL DEFAULT 0")
        for (k, b, c), m in MENU_BASE_MINUTES.items():
            cur.execute("INSERT OR IGNORE INTO menu_time_matrix(menu_kind, body_size, coat_type, minutes) VALUES(?,?,?,?)", (k, b, c, m))
        for (k, b, c), p in MENU_BASE_PRICES.items():
            cur.execute("INSERT OR IGNORE INTO menu_price_matrix(menu_kind, body_size, coat_type, unit_price_excl_tax) VALUES(?,?,?,?)", (k, b, c, p))
        for n, m, p in DEFAULT_OPTIONS:
            cur.execute("INSERT OR IGNORE INTO options_master(option_name, minutes, unit_price_excl_tax) VALUES(?,?,?)", (n, m, p))
        conn.commit()


def inject_compact_css():
    st.markdown("""
    <style>
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }
    h1 { font-size: 1.6rem !important; margin: 0.35rem 0 0.55rem 0 !important; }
    h2 { font-size: 1.2rem !important; margin: 0.30rem 0 0.40rem 0 !important; }
    h3 { font-size: 1.05rem !important; margin: 0.25rem 0 0.30rem 0 !important; }
    div[data-testid="stVerticalBlock"] > div { gap: 0.35rem; }
    div[data-testid="stForm"] { padding-top: 0.2rem; }
    label, .stRadio, .stCheckbox { margin-bottom: 0.1rem !important; }
    </style>
    """, unsafe_allow_html=True)


def parse_hhmm(v: str) -> time:
    return datetime.strptime(v, "%H:%M").time()


def combine(d: str, t: str) -> datetime:
    return datetime.combine(datetime.strptime(d, "%Y-%m-%d").date(), parse_hhmm(t))


def parse_optional_int(v: str) -> Optional[int]:
    t = (v or "").strip()
    return None if not t else int(t)


def get_settings(conn): return conn.execute("SELECT * FROM settings WHERE id=1").fetchone()
def get_options(conn): return conn.execute("SELECT * FROM options_master ORDER BY id").fetchall()
def fetch_bookings_for_day(conn, day): return conn.execute("SELECT * FROM bookings WHERE booking_date=? ORDER BY fixed_start_time, id", (day,)).fetchall()
def fetch_booking_options(conn, bid):
    return conn.execute("SELECT bo.*,om.option_name FROM booking_options bo JOIN options_master om ON bo.option_id=om.id WHERE booking_id=?", (bid,)).fetchall()


def base_menu_minutes(conn, menu_type, body, coat):
    if menu_type == "OPT_ONLY": return 0
    if menu_type == "CS":
        c = conn.execute("SELECT minutes FROM menu_time_matrix WHERE menu_kind='C' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        s = conn.execute("SELECT minutes FROM menu_time_matrix WHERE menu_kind='S' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        return c + s
    return conn.execute("SELECT minutes FROM menu_time_matrix WHERE menu_kind=? AND body_size=? AND coat_type=?", (menu_type, body, coat)).fetchone()[0]


def menu_price(conn, menu_type, body, coat):
    if menu_type == "OPT_ONLY": return 0
    if menu_type == "CS":
        c = conn.execute("SELECT unit_price_excl_tax FROM menu_price_matrix WHERE menu_kind='C' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        s = conn.execute("SELECT unit_price_excl_tax FROM menu_price_matrix WHERE menu_kind='S' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        return c + s
    return conn.execute("SELECT unit_price_excl_tax FROM menu_price_matrix WHERE menu_kind=? AND body_size=? AND coat_type=?", (menu_type, body, coat)).fetchone()[0]


def save_booking_options(conn, booking_id, qty_map):
    conn.execute("DELETE FROM booking_options WHERE booking_id=?", (booking_id,))
    for oid, qty in qty_map.items():
        if qty <= 0: continue
        o = conn.execute("SELECT * FROM options_master WHERE id=?", (oid,)).fetchone()
        conn.execute("INSERT INTO booking_options(booking_id, option_id, qty, minutes_total, unit_price_excl_tax, price_excl_tax_total) VALUES(?,?,?,?,?,?)",
                     (booking_id, oid, qty, o["minutes"] * qty, o["unit_price_excl_tax"], o["unit_price_excl_tax"] * qty))


def recompute_booking(conn, booking_id):
    b = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    opt_price = sum(r["price_excl_tax_total"] for r in fetch_booking_options(conn, booking_id))
    menu_auto = menu_price(conn, b["menu_type"], b["body_size"], b["coat_type"])
    menu_snapshot = b["menu_unit_price_excl_tax"] if b["menu_unit_price_excl_tax"] is not None else menu_auto
    subtotal_auto = menu_snapshot + opt_price
    subtotal_excl = b["subtotal_excl_tax_manual_override"] if b["subtotal_excl_tax_manual_override"] is not None else subtotal_auto
    s = get_settings(conn)
    tax = math.floor(subtotal_excl * s["tax_rate_percent"] / 100)
    incl = subtotal_excl + tax
    due = max(0, incl - (b["discount_yen"] or 0) - (b["points_used_yen"] or 0))
    conn.execute("UPDATE bookings SET menu_unit_price_excl_tax=?, options_unit_price_excl_tax_total=?, subtotal_excl_tax_auto=?, tax_yen=?, subtotal_incl_tax_yen=?, amount_due_yen=? WHERE id=?",
                 (menu_snapshot, opt_price, subtotal_auto, tax, incl, due, booking_id))


def create_or_update_booking(conn, booking_id, payload, option_qty):
    cols = list(payload.keys())
    if booking_id:
        sets = ",".join([f"{c}=?" for c in cols])
        conn.execute(f"UPDATE bookings SET {sets} WHERE id=?", tuple(payload[c] for c in cols) + (booking_id,))
    else:
        q = ",".join(["?"] * len(cols))
        cur = conn.execute(f"INSERT INTO bookings({','.join(cols)}) VALUES({q})", tuple(payload[c] for c in cols))
        booking_id = cur.lastrowid
    save_booking_options(conn, booking_id, option_qty)
    recompute_booking(conn, booking_id)
    conn.commit()


def update_day_ops(conn, booking_id, shed_mat_flag, actual_end_time, actual_end_confirmed, early_arrival_confirmed, option_qty):
    conn.execute("UPDATE bookings SET shed_mat_flag=?, actual_end_time=?, actual_end_confirmed=?, early_arrival_confirmed=? WHERE id=?",
                 (shed_mat_flag, actual_end_time, actual_end_confirmed, early_arrival_confirmed, booking_id))
    save_booking_options(conn, booking_id, option_qty)
    recompute_booking(conn, booking_id)
    conn.commit()


def update_start_by_drag(conn, booking_id, new_start_hhmm, day_s):
    s = get_settings(conn)
    if not (parse_hhmm(s["business_open_time"]) <= parse_hhmm(new_start_hhmm) <= parse_hhmm(s["business_close_time"])):
        return False, "営業時間外のため更新できません"
    conn.execute("UPDATE bookings SET fixed_start_time=? WHERE id=? AND booking_date=?", (new_start_hhmm, booking_id, day_s))
    conn.commit()
    return True, "開始時刻を更新しました"


def compute_day_simulation(conn, day):
    s = get_settings(conn)
    rows = fetch_bookings_for_day(conn, day)
    base_buffer = s["buffer_minutes"]
    apply_last = bool(s["buffer_apply_to_last"])
    open_t = combine(day, s["business_open_time"])
    close_t = combine(day, s["business_close_time"])
    enriched = []
    for i, r in enumerate(rows):
        opt_minutes = sum(o["minutes_total"] for o in fetch_booking_options(conn, r["id"]))
        work = base_menu_minutes(conn, r["menu_type"], r["body_size"], r["coat_type"]) + (45 if r["shed_mat_flag"] and r["menu_type"] in ["C", "S", "CS"] else 0) + opt_minutes
        fixed_start = combine(day, r["fixed_start_time"])
        fixed_end_work = fixed_start + timedelta(minutes=work)
        is_last = i == len(rows) - 1
        applied_buffer = (base_buffer if (not is_last or apply_last) else 0) + (max(0, int(r["extra_gap_buffer_minutes"] or 0)) if not is_last else 0)
        enriched.append({"raw": r, "work_minutes": work, "fixed_start": fixed_start, "fixed_end_work": fixed_end_work,
                         "fixed_end_with_buffer": fixed_end_work + timedelta(minutes=applied_buffer), "applied_buffer": applied_buffer, "is_last": is_last})
    prev_end = open_t
    chain = 0
    for i, e in enumerate(enriched):
        early = None
        if i > 0:
            p = enriched[i - 1]["raw"]
            if p["actual_end_confirmed"] and p["actual_end_time"] and e["raw"]["early_arrival_confirmed"]:
                cand = max(combine(day, p["actual_end_time"]), datetime.now().replace(second=0, microsecond=0))
                if cand < e["fixed_start"]: early = cand
        base = max(prev_end, early) if early else prev_end
        e["virtual_start"] = max(e["fixed_start"], base)
        e["virtual_end_work"] = e["virtual_start"] + timedelta(minutes=e["work_minutes"])
        e["virtual_end_with_buffer"] = e["virtual_end_work"] + timedelta(minutes=e["applied_buffer"])
        intrusion = prev_end > e["fixed_start"]
        chain = chain + 1 if intrusion else 0
        e["warning"] = "RED" if chain >= 2 else ("YELLOW" if intrusion else "GREEN")
        prev_end = e["virtual_end_with_buffer"]
    day_warning = "RED" if any(e["warning"] == "RED" for e in enriched) else ("YELLOW" if any(e["warning"] == "YELLOW" for e in enriched) else "GREEN")
    if enriched and enriched[-1]["virtual_end_with_buffer"] > close_t:
        day_warning = "RED"
        enriched[-1]["warning"] = "RED"
    return enriched, day_warning


def hhmm(dt: datetime):
    return dt.strftime("%H:%M")


def ui_settings(conn):
    with st.popover("⚙ 設定"):
        s = get_settings(conn)
        open_t = st.text_input("営業開始", s["business_open_time"], key="set_open")
        close_t = st.text_input("営業終了", s["business_close_time"], key="set_close")
        buffer_minutes = st.number_input("既定バッファ", 0, 180, s["buffer_minutes"], 5, key="set_buffer")
        apply_last = st.checkbox("最終後バッファ", bool(s["buffer_apply_to_last"]), key="set_apply_last")
        if st.button("設定保存"):
            conn.execute("UPDATE settings SET business_open_time=?, business_close_time=?, buffer_minutes=?, buffer_apply_to_last=? WHERE id=1",
                         (open_t, close_t, int(buffer_minutes), int(apply_last)))
            conn.commit()
            st.success("保存しました")
            st.rerun()


def ui_new_booking(conn, day_s):
    with st.popover("＋ 予約"):
        with st.form("new_booking"):
            fixed_start = st.text_input("固定開始(HH:MM) *")
            customer = st.text_input("顧客名 *")
            dog = st.text_input("犬名 *")
            c1, c2, c3 = st.columns(3)
            body = c1.selectbox("体格", ["S", "M", "L"])
            coat = c2.selectbox("毛質", ["LONG", "SHORT"])
            menu_type = c3.selectbox("メニュー", ["C", "S", "CS", "OPT_ONLY"])
            notes = st.text_input("メモ")
            if st.form_submit_button("作成"):
                parse_hhmm(fixed_start)
                payload = {
                    "booking_date": day_s, "fixed_start_time": fixed_start, "customer_name": customer or "(未入力)", "dog_name": dog or "(未入力)",
                    "body_size": body, "coat_type": coat, "menu_type": menu_type, "shed_mat_flag": 0, "notes": notes,
                    "actual_end_time": None, "actual_end_confirmed": 0, "early_arrival_confirmed": 0,
                    "menu_unit_price_excl_tax": None, "subtotal_excl_tax_manual_override": None,
                    "discount_yen": 0, "points_used_yen": 0, "payment_status": "UNPAID", "points_granted": 0,
                }
                create_or_update_booking(conn, None, payload, {})
                st.success("予約を作成")
                st.rerun()


def main():
    st.set_page_config(page_title="トリミング スケジュール調整", layout="wide")
    inject_compact_css()
    init_db()
    conn = get_conn()

    top1, top2, top3 = st.columns([2, 1, 1])
    with top1:
        st.title("トリミング スケジュール調整")
    day = top2.date_input("対象日", value=date.today())
    day_s = day.strftime("%Y-%m-%d")
    with top3:
        ui_settings(conn)
        ui_new_booking(conn, day_s)

    sim, day_warn = compute_day_simulation(conn, day_s)
    warn_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}[day_warn]
    st.markdown(f"**当日警告:** {warn_emoji} {day_warn}（衝突は自動解消しません）")

    left, main_area, right = st.columns([1.2, 5.5, 1.8])

    with left:
        st.subheader("当日予約")
        rows = [{"id": e["raw"]["id"], "時刻": e["raw"]["fixed_start_time"], "顧客": e["raw"]["customer_name"], "犬": e["raw"]["dog_name"], "警告": e["warning"]} for e in sim]
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True, height=520)
        ids = [e["raw"]["id"] for e in sim]
        selected_id = st.selectbox("選択予約", ids, index=0 if ids else None) if ids else None

    with main_area:
        st.subheader("タイムライン（D&Dで開始時刻を手動変更）")
        s = get_settings(conn)
        items = []
        for e in sim:
            r = e["raw"]
            label = f"{r['customer_name']}/{r['dog_name']}"
            items.append({"id": f"c-{r['id']}", "booking_id": r["id"], "kind": "confirmed", "content": label,
                          "start": e["fixed_start"].isoformat(), "end": e["fixed_end_work"].isoformat(), "warning": e["warning"], "editable": True})
            if e["applied_buffer"] > 0:
                items.append({"id": f"b-{r['id']}", "booking_id": r["id"], "kind": "buffer", "content": "buffer",
                              "start": e["fixed_end_work"].isoformat(), "end": e["fixed_end_with_buffer"].isoformat(), "warning": e["warning"], "editable": False})
            if e["virtual_start"] > e["fixed_start"]:
                items.append({"id": f"v-{r['id']}", "booking_id": r["id"], "kind": "virtual", "content": "virtual",
                              "start": e["virtual_start"].isoformat(), "end": e["virtual_end_work"].isoformat(), "warning": e["warning"], "editable": False})

        event = timeline_dnd(items=items, start=combine(day_s, s["business_open_time"]).isoformat(),
                             end=combine(day_s, s["business_close_time"]).isoformat(), key=f"timeline-{day_s}-{len(items)}")
        if event and event.get("booking_id"):
            dt = datetime.fromisoformat(event["new_start_iso"]).replace(second=0, microsecond=0)
            ok, msg = update_start_by_drag(conn, int(event["booking_id"]), dt.strftime("%H:%M"), day_s)
            (st.success if ok else st.error)(msg)
            st.rerun()

    with right:
        st.subheader("詳細")
        if selected_id:
            b = conn.execute("SELECT * FROM bookings WHERE id=?", (selected_id,)).fetchone()
            tab_a, tab_b = st.tabs(["詳細/会計", "当日運用"])
            with tab_a:
                st.write(f"{b['customer_name']} / {b['dog_name']}")
                st.write(f"固定開始: {b['fixed_start_time']}  メニュー: {b['menu_type']}")
                st.write(f"税抜自動: ¥{b['subtotal_excl_tax_auto']} / 支払額: ¥{b['amount_due_yen']}")
            with tab_b:
                options = get_options(conn)
                exist = {r["option_id"]: r["qty"] for r in fetch_booking_options(conn, selected_id)}
                shed = st.checkbox("毛玉/抜け毛", value=bool(b["shed_mat_flag"]))
                actual_end = st.text_input("実績終了(HH:MM)", value=b["actual_end_time"] or "")
                actual_conf = st.checkbox("終了確定", value=bool(b["actual_end_confirmed"]))
                early = st.checkbox("早め来店", value=bool(b["early_arrival_confirmed"]))
                qty = {}
                for o in options:
                    qty[o["id"]] = st.number_input(f"{o['option_name']}", 0, 20, exist.get(o["id"], 0), 1, key=f"ops_{selected_id}_{o['id']}")
                if st.button("当日運用を保存"):
                    update_day_ops(conn, selected_id, int(shed), actual_end or None, int(actual_conf), int(early), qty)
                    st.success("保存しました")
                    st.rerun()


if __name__ == "__main__":
    main()
