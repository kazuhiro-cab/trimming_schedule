import math
import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta
from typing import Dict, Optional

import pandas as pd
import plotly.express as px
import streamlit as st

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
    ("歯磨き", 5, 500),
    ("部分カット（1箇所）", 5, 500),
    ("肛門腺", 5, 500),
    ("耳掃除", 5, 500),
    ("エチケットカット（1箇所）", 5, 500),
    ("髭カット", 5, 500),
    ("爪切り", 10, 800),
]


def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_column(conn, table: str, column: str, ddl: str):
    cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db():
    with closing(get_conn()) as conn:
        cur = conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY CHECK(id=1),
                business_open_time TEXT NOT NULL DEFAULT '09:00',
                business_close_time TEXT NOT NULL DEFAULT '19:00',
                buffer_minutes INTEGER NOT NULL DEFAULT 30,
                buffer_apply_to_last INTEGER NOT NULL DEFAULT 1,
                tax_rate_percent INTEGER NOT NULL DEFAULT 10,
                tax_rounding_mode TEXT NOT NULL DEFAULT 'FLOOR'
            );

            CREATE TABLE IF NOT EXISTS menu_time_matrix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_kind TEXT NOT NULL,
                body_size TEXT NOT NULL,
                coat_type TEXT NOT NULL,
                minutes INTEGER NOT NULL,
                UNIQUE(menu_kind, body_size, coat_type)
            );

            CREATE TABLE IF NOT EXISTS menu_price_matrix (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                menu_kind TEXT NOT NULL,
                body_size TEXT NOT NULL,
                coat_type TEXT NOT NULL,
                unit_price_excl_tax INTEGER NOT NULL,
                UNIQUE(menu_kind, body_size, coat_type)
            );

            CREATE TABLE IF NOT EXISTS options_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                option_name TEXT NOT NULL UNIQUE,
                minutes INTEGER NOT NULL,
                unit_price_excl_tax INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_date TEXT NOT NULL,
                fixed_start_time TEXT NOT NULL,
                customer_name TEXT NOT NULL,
                dog_name TEXT NOT NULL,
                body_size TEXT NOT NULL,
                coat_type TEXT NOT NULL,
                menu_type TEXT NOT NULL,
                shed_mat_flag INTEGER NOT NULL DEFAULT 0,
                notes TEXT,
                actual_end_time TEXT,
                actual_end_confirmed INTEGER NOT NULL DEFAULT 0,
                early_arrival_confirmed INTEGER NOT NULL DEFAULT 0,
                menu_unit_price_excl_tax INTEGER,
                options_unit_price_excl_tax_total INTEGER,
                subtotal_excl_tax_auto INTEGER NOT NULL DEFAULT 0,
                subtotal_excl_tax_manual_override INTEGER,
                discount_yen INTEGER NOT NULL DEFAULT 0,
                points_used_yen INTEGER NOT NULL DEFAULT 0,
                tax_yen INTEGER NOT NULL DEFAULT 0,
                subtotal_incl_tax_yen INTEGER NOT NULL DEFAULT 0,
                amount_due_yen INTEGER NOT NULL DEFAULT 0,
                payment_status TEXT NOT NULL DEFAULT 'UNPAID',
                points_granted INTEGER NOT NULL DEFAULT 0,
                extra_gap_buffer_minutes INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS booking_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                qty INTEGER NOT NULL,
                minutes_total INTEGER NOT NULL,
                unit_price_excl_tax INTEGER NOT NULL,
                price_excl_tax_total INTEGER NOT NULL,
                FOREIGN KEY(booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
                FOREIGN KEY(option_id) REFERENCES options_master(id)
            );
            """
        )
        cur.execute("INSERT OR IGNORE INTO settings(id) VALUES(1)")
        ensure_column(conn, "bookings", "extra_gap_buffer_minutes", "extra_gap_buffer_minutes INTEGER NOT NULL DEFAULT 0")

        for (kind, body, coat), minutes in MENU_BASE_MINUTES.items():
            cur.execute(
                """INSERT OR IGNORE INTO menu_time_matrix(menu_kind, body_size, coat_type, minutes)
                VALUES(?, ?, ?, ?)""",
                (kind, body, coat, minutes),
            )

        for (kind, body, coat), price in MENU_BASE_PRICES.items():
            cur.execute(
                """INSERT OR IGNORE INTO menu_price_matrix(menu_kind, body_size, coat_type, unit_price_excl_tax)
                VALUES(?, ?, ?, ?)""",
                (kind, body, coat, price),
            )

        for name, minutes, price in DEFAULT_OPTIONS:
            cur.execute(
                "INSERT OR IGNORE INTO options_master(option_name, minutes, unit_price_excl_tax) VALUES(?, ?, ?)",
                (name, minutes, price),
            )
        conn.commit()


def inject_compact_css():
    st.markdown("""
    <style>
    /* 画面全体の上下余白を詰める */
    .block-container { padding-top: 0.8rem; padding-bottom: 0.8rem; }

    /* 見出しを小さくして情報密度を上げる */
    h1 { font-size: 1.6rem !important; margin: 0.35rem 0 0.55rem 0 !important; }
    h2 { font-size: 1.2rem !important; margin: 0.30rem 0 0.40rem 0 !important; }
    h3 { font-size: 1.05rem !important; margin: 0.25rem 0 0.30rem 0 !important; }

    /* ブロック間の隙間を詰める */
    div[data-testid="stVerticalBlock"] > div { gap: 0.35rem; }
    div[data-testid="stForm"] { padding-top: 0.2rem; }

    /* ラベル類の余白を詰める */
    label, .stRadio, .stCheckbox { margin-bottom: 0.1rem !important; }
    </style>
    """, unsafe_allow_html=True)


def parse_hhmm(v: str) -> time:
    return datetime.strptime(v, "%H:%M").time()


def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def combine(d: str, t: str) -> datetime:
    return datetime.combine(datetime.strptime(d, "%Y-%m-%d").date(), parse_hhmm(t))


def parse_optional_int(v: str) -> Optional[int]:
    txt = (v or "").strip()
    if not txt:
        return None
    n = int(txt)
    if n < 0:
        raise ValueError
    return n


def get_settings(conn):
    return conn.execute("SELECT * FROM settings WHERE id=1").fetchone()


def get_options(conn):
    return conn.execute("SELECT * FROM options_master ORDER BY id").fetchall()


def fetch_bookings_for_day(conn, day: str):
    return conn.execute("SELECT * FROM bookings WHERE booking_date=? ORDER BY fixed_start_time, id", (day,)).fetchall()


def fetch_booking_options(conn, booking_id: int):
    return conn.execute(
        """
        SELECT bo.*, om.option_name
        FROM booking_options bo
        JOIN options_master om ON bo.option_id=om.id
        WHERE booking_id=?
        """,
        (booking_id,),
    ).fetchall()


def base_menu_minutes(conn, menu_type: str, body: str, coat: str):
    if menu_type == "OPT_ONLY":
        return 0
    if menu_type == "CS":
        c = conn.execute("SELECT minutes FROM menu_time_matrix WHERE menu_kind='C' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        s = conn.execute("SELECT minutes FROM menu_time_matrix WHERE menu_kind='S' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        return c + s
    return conn.execute(
        "SELECT minutes FROM menu_time_matrix WHERE menu_kind=? AND body_size=? AND coat_type=?",
        (menu_type, body, coat),
    ).fetchone()[0]


def menu_price(conn, menu_type: str, body: str, coat: str):
    if menu_type == "OPT_ONLY":
        return 0
    if menu_type == "CS":
        c = conn.execute("SELECT unit_price_excl_tax FROM menu_price_matrix WHERE menu_kind='C' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        s = conn.execute("SELECT unit_price_excl_tax FROM menu_price_matrix WHERE menu_kind='S' AND body_size=? AND coat_type=?", (body, coat)).fetchone()[0]
        return c + s
    return conn.execute(
        "SELECT unit_price_excl_tax FROM menu_price_matrix WHERE menu_kind=? AND body_size=? AND coat_type=?",
        (menu_type, body, coat),
    ).fetchone()[0]


def recompute_booking(conn, booking_id: int):
    b = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    options = fetch_booking_options(conn, booking_id)
    opt_price = sum(r["price_excl_tax_total"] for r in options)

    menu_auto = menu_price(conn, b["menu_type"], b["body_size"], b["coat_type"])
    menu_snapshot = b["menu_unit_price_excl_tax"] if b["menu_unit_price_excl_tax"] is not None else menu_auto
    subtotal_auto = menu_snapshot + opt_price
    subtotal_excl = b["subtotal_excl_tax_manual_override"] if b["subtotal_excl_tax_manual_override"] is not None else subtotal_auto

    settings = get_settings(conn)
    tax = math.floor(subtotal_excl * settings["tax_rate_percent"] / 100)
    subtotal_incl = subtotal_excl + tax
    amount_due = max(0, subtotal_incl - (b["discount_yen"] or 0) - (b["points_used_yen"] or 0))

    conn.execute(
        """UPDATE bookings SET
            menu_unit_price_excl_tax=?,
            options_unit_price_excl_tax_total=?,
            subtotal_excl_tax_auto=?,
            tax_yen=?, subtotal_incl_tax_yen=?, amount_due_yen=?
            WHERE id=?""",
        (menu_snapshot, opt_price, subtotal_auto, tax, subtotal_incl, amount_due, booking_id),
    )


def save_booking_options(conn, booking_id: int, qty_map: Dict[int, int]):
    conn.execute("DELETE FROM booking_options WHERE booking_id=?", (booking_id,))
    for option_id, qty in qty_map.items():
        if qty <= 0:
            continue
        option = conn.execute("SELECT * FROM options_master WHERE id=?", (option_id,)).fetchone()
        minutes_total = option["minutes"] * qty
        total = option["unit_price_excl_tax"] * qty
        conn.execute(
            """INSERT INTO booking_options(booking_id, option_id, qty, minutes_total, unit_price_excl_tax, price_excl_tax_total)
               VALUES(?, ?, ?, ?, ?, ?)""",
            (booking_id, option_id, qty, minutes_total, option["unit_price_excl_tax"], total),
        )


def compute_day_simulation(conn, day: str):
    settings = get_settings(conn)
    rows = fetch_bookings_for_day(conn, day)
    base_buffer = settings["buffer_minutes"]
    apply_last = bool(settings["buffer_apply_to_last"])
    open_t = combine(day, settings["business_open_time"])
    close_t = combine(day, settings["business_close_time"])

    enriched = []
    for i, r in enumerate(rows):
        opts = fetch_booking_options(conn, r["id"])
        opt_minutes = sum(o["minutes_total"] for o in opts)
        menu_minutes = base_menu_minutes(conn, r["menu_type"], r["body_size"], r["coat_type"])
        add45 = 45 if r["shed_mat_flag"] and r["menu_type"] in ["C", "S", "CS"] else 0
        work_minutes = menu_minutes + add45 + opt_minutes
        fixed_start = combine(day, r["fixed_start_time"])
        fixed_end_work = fixed_start + timedelta(minutes=work_minutes)

        is_last = i == len(rows) - 1
        base_part = base_buffer if (not is_last or apply_last) else 0
        extra_gap = max(0, int(r["extra_gap_buffer_minutes"] or 0)) if not is_last else 0
        applied_buffer = base_part + extra_gap

        enriched.append(
            {
                "raw": r,
                "work_minutes": work_minutes,
                "fixed_start": fixed_start,
                "fixed_end_work": fixed_end_work,
                "fixed_end_with_buffer": fixed_end_work + timedelta(minutes=applied_buffer),
                "applied_buffer": applied_buffer,
                "base_buffer": base_part,
                "extra_gap_used": extra_gap,
                "is_last": is_last,
            }
        )

    previous_virtual_end = open_t
    chain_level = 0
    for i, e in enumerate(enriched):
        e["early_virtual_start"] = None
        if i > 0:
            prev_raw = enriched[i - 1]["raw"]
            if prev_raw["actual_end_confirmed"] and prev_raw["actual_end_time"] and e["raw"]["early_arrival_confirmed"]:
                actual_end = combine(day, prev_raw["actual_end_time"])
                candidate_early = max(actual_end, datetime.now().replace(second=0, microsecond=0))
                if candidate_early < e["fixed_start"]:
                    e["early_virtual_start"] = candidate_early

        virtual_base = previous_virtual_end
        if e["early_virtual_start"] is not None:
            virtual_base = max(virtual_base, e["early_virtual_start"])

        e["virtual_start"] = max(e["fixed_start"], virtual_base)
        e["virtual_end_work"] = e["virtual_start"] + timedelta(minutes=e["work_minutes"])
        e["virtual_end_with_buffer"] = e["virtual_end_work"] + timedelta(minutes=e["applied_buffer"])

        intrusion = previous_virtual_end > e["fixed_start"]
        chain_level = chain_level + 1 if intrusion else 0
        e["warning"] = "RED" if chain_level >= 2 else ("YELLOW" if intrusion else "GREEN")
        e["has_virtual_overlap"] = e["virtual_start"] > e["fixed_start"]
        previous_virtual_end = e["virtual_end_with_buffer"]

        if i < len(enriched) - 1:
            nxt = enriched[i + 1]
            gap = int((nxt["fixed_start"] - e["fixed_end_work"]).total_seconds() // 60)
            e["gap_to_next"] = gap
            e["max_extra_buffer"] = max(0, gap - base_buffer)
            e["extra_buffer_editable"] = gap > base_buffer
        else:
            e["gap_to_next"] = None
            e["max_extra_buffer"] = 0
            e["extra_buffer_editable"] = False

    day_warning = "GREEN"
    if any(e["warning"] == "RED" for e in enriched):
        day_warning = "RED"
    elif any(e["warning"] == "YELLOW" for e in enriched):
        day_warning = "YELLOW"

    if enriched and enriched[-1]["virtual_end_with_buffer"] > close_t:
        day_warning = "RED"
        enriched[-1]["warning"] = "RED"

    return enriched, day_warning


def build_timeline_figure(sim, day_s: str, open_time: str, close_time: str):
    segments = []
    color_map = {
        "GREEN_確定": "#2ca02c",
        "YELLOW_確定": "#e6ac00",
        "RED_確定": "#d62728",
        "GREEN_バッファ": "#91cf91",
        "YELLOW_バッファ": "#ffd76b",
        "RED_バッファ": "#ff8c8c",
        "GREEN_仮想": "#1f77b4",
        "YELLOW_仮想": "#9467bd",
        "RED_仮想": "#8c564b",
    }

    for idx, e in enumerate(sim, 1):
        raw = e["raw"]
        row_label = f"{idx}. #{raw['id']} {raw['customer_name']}/{raw['dog_name']}"
        warn = e["warning"]
        hover_base = f"顧客: {raw['customer_name']}<br>犬: {raw['dog_name']}<br>メニュー: {raw['menu_type']}<br>作業: {e['work_minutes']}分<br>警告: {warn}"

        segments.append(
            {
                "row": row_label,
                "start": e["fixed_start"],
                "end": e["fixed_end_work"],
                "kind": f"{warn}_確定",
                "label": "確定枠",
                "hover": hover_base + "<br>区分: 確定枠",
            }
        )

        if e["applied_buffer"] > 0:
            segments.append(
                {
                    "row": row_label,
                    "start": e["fixed_end_work"],
                    "end": e["fixed_end_with_buffer"],
                    "kind": f"{warn}_バッファ",
                    "label": f"バッファ({e['applied_buffer']}分)",
                    "hover": hover_base + f"<br>区分: バッファ {e['applied_buffer']}分",
                }
            )

        if e["has_virtual_overlap"]:
            segments.append(
                {
                    "row": row_label,
                    "start": e["virtual_start"],
                    "end": e["virtual_end_work"],
                    "kind": f"{warn}_仮想",
                    "label": "仮想枠",
                    "hover": hover_base + "<br>区分: 仮想枠（可視化のみ）",
                }
            )

    if not segments:
        return None

    df = pd.DataFrame(segments)
    fig = px.timeline(
        df,
        x_start="start",
        x_end="end",
        y="row",
        color="kind",
        color_discrete_map=color_map,
        hover_name="label",
        hover_data={"start": True, "end": True, "kind": False, "row": False, "hover": True},
    )
    fig.update_yaxes(autorange="reversed", title=None)
    fig.update_xaxes(range=[combine(day_s, open_time), combine(day_s, close_time)], tickformat="%H:%M", title=None)
    fig.update_layout(height=max(320, len(sim) * 64), margin=dict(l=5, r=5, t=8, b=8), legend_title_text="区分")
    return fig


def monthly_range(start_day: date):
    return [start_day + timedelta(days=i) for i in range(92)]


def upsert_settings(conn, open_t, close_t, buffer_minutes, apply_last, tax_rate):
    conn.execute(
        """UPDATE settings SET business_open_time=?, business_close_time=?, buffer_minutes=?,
           buffer_apply_to_last=?, tax_rate_percent=?, tax_rounding_mode='FLOOR' WHERE id=1""",
        (open_t, close_t, buffer_minutes, int(apply_last), tax_rate),
    )


def create_or_update_booking(conn, booking_id: Optional[int], payload: dict, option_qty: Dict[int, int]):
    previous_status = None
    if booking_id:
        old = conn.execute("SELECT payment_status FROM bookings WHERE id=?", (booking_id,)).fetchone()
        previous_status = old["payment_status"]
        conn.execute(
            """UPDATE bookings SET booking_date=?, fixed_start_time=?, customer_name=?, dog_name=?, body_size=?, coat_type=?,
            menu_type=?, shed_mat_flag=?, notes=?, actual_end_time=?, actual_end_confirmed=?, early_arrival_confirmed=?,
            menu_unit_price_excl_tax=?, subtotal_excl_tax_manual_override=?, discount_yen=?, points_used_yen=?,
            payment_status=?, points_granted=? WHERE id=?""",
            (*payload.values(), booking_id),
        )
    else:
        cur = conn.execute(
            """INSERT INTO bookings(booking_date, fixed_start_time, customer_name, dog_name, body_size, coat_type, menu_type,
            shed_mat_flag, notes, actual_end_time, actual_end_confirmed, early_arrival_confirmed, menu_unit_price_excl_tax,
            subtotal_excl_tax_manual_override, discount_yen, points_used_yen, payment_status, points_granted)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            tuple(payload.values()),
        )
        booking_id = cur.lastrowid

    save_booking_options(conn, booking_id, option_qty)
    recompute_booking(conn, booking_id)

    if previous_status == "UNPAID" and payload["payment_status"] == "PAID":
        pass
    conn.commit()


def set_extra_gap_buffer(conn, booking_id: int, minutes: int):
    conn.execute("UPDATE bookings SET extra_gap_buffer_minutes=? WHERE id=?", (minutes, booking_id))
    conn.commit()


def main():
    st.set_page_config(page_title="トリミング スケジュール調整", layout="wide")
    inject_compact_css()
    init_db()
    conn = get_conn()

    st.title("トリミングサロン スケジュール調整ツール")
    left, mid, right = st.columns([1, 1.4, 1.9])

    with left:
        st.subheader("設定")
        s = get_settings(conn)
        open_t = st.text_input("営業開始", s["business_open_time"])
        close_t = st.text_input("営業終了", s["business_close_time"])
        buffer_minutes = st.number_input("既定バッファ(分)", min_value=0, value=s["buffer_minutes"], step=5)
        apply_last = st.checkbox("最終予約後もバッファを付与", value=bool(s["buffer_apply_to_last"]))
        tax_rate = st.number_input("税率(%)", min_value=0, max_value=20, value=s["tax_rate_percent"])
        if st.button("設定保存"):
            upsert_settings(conn, open_t, close_t, int(buffer_minutes), apply_last, int(tax_rate))
            conn.commit()
            st.success("保存しました")

    with mid:
        st.subheader("予約")
        selected_day = st.date_input("対象日", value=date.today())
        day_s = selected_day.strftime("%Y-%m-%d")
        bookings = fetch_bookings_for_day(conn, day_s)
        ids = ["新規"] + [f"#{b['id']} {b['fixed_start_time']} {b['customer_name']}" for b in bookings]
        choice = st.selectbox("編集対象", ids)
        current = None
        if choice != "新規":
            current_id = int(choice.split()[0][1:])
            current = conn.execute("SELECT * FROM bookings WHERE id=?", (current_id,)).fetchone()

        with st.form("booking_form"):
            c1, c2 = st.columns(2)
            b_date = c1.date_input("予約日", value=selected_day)
            fixed_start = c2.text_input("固定開始時刻(HH:MM) *", value=current["fixed_start_time"] if current else "")
            customer = c1.text_input("顧客名", value=current["customer_name"] if current else "")
            dog = c2.text_input("犬名", value=current["dog_name"] if current else "")
            body = c1.selectbox("体格", ["S", "M", "L"], index=["S", "M", "L"].index(current["body_size"]) if current else 0)
            coat = c2.selectbox("毛質 *", ["LONG", "SHORT"], index=["LONG", "SHORT"].index(current["coat_type"]) if current else 0)
            menu_type = c1.selectbox("メニュー", ["C", "S", "CS", "OPT_ONLY"], index=["C", "S", "CS", "OPT_ONLY"].index(current["menu_type"]) if current else 0)
            shed = c2.checkbox("毛玉/抜け毛が激しい (+45)", value=bool(current["shed_mat_flag"]) if current else False)
            notes = st.text_area("メモ", value=current["notes"] if current and current["notes"] else "")

            d1, d2, d3 = st.columns(3)
            actual_end_time = d1.text_input("実績終了時刻(HH:MM)", value=current["actual_end_time"] if current and current["actual_end_time"] else "")
            actual_confirm = d2.checkbox("作業終了確定", value=bool(current["actual_end_confirmed"]) if current else False)
            early = d3.checkbox("早め来店確認", value=bool(current["early_arrival_confirmed"]) if current else False)

            st.markdown("**会計**")
            menu_snap_default = "" if not current or current["menu_unit_price_excl_tax"] is None else str(current["menu_unit_price_excl_tax"])
            subtotal_override_default = "" if not current or current["subtotal_excl_tax_manual_override"] is None else str(current["subtotal_excl_tax_manual_override"])
            e1, e2, e3, e4 = st.columns(4)
            menu_price_snapshot_input = e1.text_input("メニュー税抜単価（任意上書き）", value=menu_snap_default, placeholder="空欄ならマスタ自動")
            manual_override_input = e2.text_input("税抜小計 手動上書き（任意）", value=subtotal_override_default, placeholder="空欄なら自動")
            discount = e3.number_input("割引(円)", min_value=0, value=current["discount_yen"] if current else 0)
            points_used = e4.number_input("ポイント使用(円)", min_value=0, value=current["points_used_yen"] if current else 0)
            pay1, pay2 = st.columns(2)
            payment_status = pay1.selectbox("支払状況", ["UNPAID", "PAID"], index=["UNPAID", "PAID"].index(current["payment_status"]) if current else 0)
            points_granted = pay2.number_input("付与ポイント", min_value=0, value=current["points_granted"] if current else 0)

            st.markdown("**オプション（数量）**")
            options = get_options(conn)
            option_qty = {}
            existing_qty = {r["option_id"]: r["qty"] for r in fetch_booking_options(conn, current["id"])} if current else {}
            cols = st.columns(2)
            for idx, o in enumerate(options):
                with cols[idx % 2]:
                    option_qty[o["id"]] = st.number_input(
                        f"{o['option_name']} ({o['minutes']}分 / ¥{o['unit_price_excl_tax']})",
                        min_value=0,
                        value=existing_qty.get(o["id"], 0),
                        step=1,
                        key=f"opt_{o['id']}",
                    )

            if st.form_submit_button("保存"):
                if not fixed_start:
                    st.error("固定開始時刻は必須です。")
                else:
                    try:
                        parse_hhmm(fixed_start)
                        payload = {
                            "booking_date": b_date.strftime("%Y-%m-%d"),
                            "fixed_start_time": fixed_start,
                            "customer_name": customer,
                            "dog_name": dog,
                            "body_size": body,
                            "coat_type": coat,
                            "menu_type": menu_type,
                            "shed_mat_flag": int(shed),
                            "notes": notes,
                            "actual_end_time": actual_end_time or None,
                            "actual_end_confirmed": int(actual_confirm),
                            "early_arrival_confirmed": int(early),
                            "menu_unit_price_excl_tax": parse_optional_int(menu_price_snapshot_input),
                            "subtotal_excl_tax_manual_override": parse_optional_int(manual_override_input),
                            "discount_yen": int(discount),
                            "points_used_yen": int(points_used),
                            "payment_status": payment_status,
                            "points_granted": int(points_granted),
                        }
                        create_or_update_booking(conn, current["id"] if current else None, payload, option_qty)
                        st.success("保存しました（開始時刻は自動移動しません）")
                        st.rerun()
                    except ValueError:
                        st.error("時刻形式または金額入力が不正です。")

        if current and st.button("この予約を削除", type="secondary"):
            conn.execute("DELETE FROM booking_options WHERE booking_id=?", (current["id"],))
            conn.execute("DELETE FROM bookings WHERE id=?", (current["id"],))
            conn.commit()
            st.rerun()

    with right:
        st.subheader("結果 / タイムライン")
        view_mode = st.radio("表示", ["日別", "3ヶ月ビュー"], horizontal=True)

        if view_mode == "3ヶ月ビュー":
            rows = []
            for d in monthly_range(date.today()):
                d_s = d.strftime("%Y-%m-%d")
                sim, warn = compute_day_simulation(conn, d_s)
                last = sim[-1]["virtual_end_with_buffer"].strftime("%H:%M") if sim else "-"
                rows.append({"日付": d_s, "件数": len(fetch_bookings_for_day(conn, d_s)), "最終終了見込み": last, "警告": warn})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            s = get_settings(conn)
            sim, day_warn = compute_day_simulation(conn, day_s)
            color = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}[day_warn]
            st.markdown(f"**当日警告:** {color} {day_warn}")

            fig = build_timeline_figure(sim, day_s, s["business_open_time"], s["business_close_time"])
            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("予約がありません。")
            st.caption("※消費税端数切捨")

            st.markdown("#### バッファ余白編集（空き時間 > 既定バッファ の区間のみ）")
            for i, e in enumerate(sim):
                if i >= len(sim) - 1:
                    continue
                booking_id = e["raw"]["id"]
                if e["extra_buffer_editable"]:
                    current_extra = int(e["raw"]["extra_gap_buffer_minutes"] or 0)
                    default_extra = min(current_extra, e["max_extra_buffer"])
                    value = st.number_input(
                        f"予約#{booking_id} の余白バッファ（上限 {e['max_extra_buffer']}分）",
                        min_value=0,
                        max_value=e["max_extra_buffer"],
                        value=default_extra,
                        step=5,
                        key=f"extra_gap_{booking_id}",
                    )
                    if st.button(f"予約#{booking_id} の余白保存", key=f"save_extra_{booking_id}"):
                        set_extra_gap_buffer(conn, booking_id, int(value))
                        st.success(f"予約#{booking_id} の余白バッファを保存しました。")
                        st.rerun()
                else:
                    st.write(f"予約#{booking_id}: 編集不可（空き時間 {e['gap_to_next']}分 <= 既定バッファ）")

            st.markdown("#### 常時ヘルプ（提案のみ）")
            if sim:
                if day_warn == "GREEN":
                    st.success("現時点で食い込みはありません。追加オプションは余白内で検討可能です。")
                if any(e["warning"] == "YELLOW" for e in sim):
                    st.warning("黄警告: 単発食い込み。追加オプションを減らすか、次予約開始を手動調整してください。")
                if any(e["warning"] == "RED" for e in sim):
                    st.error("赤警告: 連鎖波及または営業時間超過。手動で開始時刻再調整か当日追加の見直しが必要です。")
                if any(e["raw"]["subtotal_excl_tax_manual_override"] is not None for e in sim):
                    st.info("手動調整あり: 一部予約で税抜小計の手動上書きが適用されています。")
                st.write("自動で開始時刻は変更されません。確定枠を維持し、必要時のみ手動編集してください。")


if __name__ == "__main__":
    main()
