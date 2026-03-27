from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

DB_PATH = Path("schedule.db")
SCHEMA_VERSION = "v279"
TRIMMER_ID = 1

MENU_TYPES = ["C", "S", "CS", "オプションのみ"]
OPTION_TYPES = ["爪切り", "耳掃除", "肛門腺", "歯磨き", "ヒゲカット", "エチケットカット", "部分カット（1箇所）"]
BOOKING_STATUSES = [
    "予約済み",
    "未着",
    "施術中",
    "完了済み",
    "キャンセル",
    "当日キャンセル",
    "施術中断",
    "中断完了",
    "中断終了",
    "無断キャンセル",
]
MENU_DURATION_DEFAULTS = {
    "menu_duration_c_small_long": 120,
    "menu_duration_c_small_short": 10,
    "menu_duration_c_medium_long": 120,
    "menu_duration_c_medium_short": 30,
    "menu_duration_c_large_long": 120,
    "menu_duration_c_large_short": 30,
    "menu_duration_s_small_long": 60,
    "menu_duration_s_small_short": 20,
    "menu_duration_s_medium_long": 60,
    "menu_duration_s_medium_short": 60,
    "menu_duration_s_large_long": 120,
    "menu_duration_s_large_short": 120,
}
OPTION_DURATION_DEFAULTS = {
    "option_duration_nail": 10,
    "option_duration_ear": 5,
    "option_duration_anal": 5,
    "option_duration_tooth": 5,
    "option_duration_beard": 5,
    "option_duration_etiquette": 5,
    "option_duration_partial": 5,
}
OPTION_KEY_MAP = {
    "爪切り": "option_duration_nail",
    "耳掃除": "option_duration_ear",
    "肛門腺": "option_duration_anal",
    "歯磨き": "option_duration_tooth",
    "ヒゲカット": "option_duration_beard",
    "エチケットカット": "option_duration_etiquette",
    "部分カット（1箇所）": "option_duration_partial",
}


@dataclass
class ValidationResult:
    ok: bool
    message: str = ""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                schema_version TEXT NOT NULL
            )
            """
        )
        row = conn.execute("SELECT schema_version FROM app_meta WHERE id = 1").fetchone()
        if row is None:
            conn.execute("INSERT INTO app_meta (id, schema_version) VALUES (1, ?)", (SCHEMA_VERSION,))
            recreate_schema(conn)
        elif row["schema_version"] != SCHEMA_VERSION:
            recreate_schema(conn)
            conn.execute("UPDATE app_meta SET schema_version = ? WHERE id = 1", (SCHEMA_VERSION,))


def recreate_schema(conn: sqlite3.Connection) -> None:
    tables = [
        "booking_options",
        "bookings",
        "dogs",
        "customers",
        "operation_logs",
        "day_buffer_overrides",
        "booking_duration_overrides",
        "system_settings",
        "business_calendar",
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")

    conn.executescript(
        """
        CREATE TABLE customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            caution_flag INTEGER NOT NULL DEFAULT 0,
            caution_reason TEXT,
            late_count INTEGER NOT NULL DEFAULT 0,
            no_show_count INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            note TEXT,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE dogs (
            dog_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            dog_name TEXT NOT NULL,
            breed TEXT,
            birth_date TEXT,
            sex TEXT,
            neutered TEXT,
            size TEXT NOT NULL,
            coat_type TEXT NOT NULL,
            allergy TEXT,
            medical_history TEXT,
            medication_flag TEXT,
            medication_name TEXT,
            biting_habit TEXT,
            rough_habit TEXT,
            no_touch_area TEXT,
            dryer_ok TEXT,
            note TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        );

        CREATE TABLE bookings (
            booking_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trimmer_id INTEGER NOT NULL,
            customer_id INTEGER NOT NULL,
            dog_id INTEGER NOT NULL,
            fixed_start_time TEXT NOT NULL,
            menu_type TEXT NOT NULL,
            matted_flag INTEGER NOT NULL DEFAULT 0,
            manual_override_duration INTEGER,
            size_snapshot TEXT NOT NULL,
            coat_type_snapshot TEXT NOT NULL,
            menu_duration_snapshot INTEGER NOT NULL,
            buffer_minutes_snapshot INTEGER NOT NULL,
            buffer_after_last_snapshot INTEGER NOT NULL,
            status TEXT NOT NULL,
            late_flag INTEGER NOT NULL DEFAULT 0,
            actual_start_time TEXT,
            actual_end_time TEXT,
            time_change_confirmed INTEGER NOT NULL DEFAULT 0,
            time_change_confirmed_at TEXT,
            no_show_confirmed INTEGER NOT NULL DEFAULT 0,
            no_show_confirmed_at TEXT,
            note TEXT,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY (dog_id) REFERENCES dogs(dog_id)
        );

        CREATE TABLE booking_options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id INTEGER NOT NULL,
            option_type TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            option_duration_snapshot INTEGER NOT NULL,
            is_day_of_addition INTEGER NOT NULL DEFAULT 0,
            is_deleted INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE CASCADE
        );

        CREATE TABLE day_buffer_overrides (
            override_id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_date TEXT NOT NULL,
            start_booking_id INTEGER NOT NULL,
            is_last_interval INTEGER NOT NULL,
            requested_buffer_minutes INTEGER NOT NULL,
            override_buffer_minutes INTEGER NOT NULL,
            created_source TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(target_date, start_booking_id, is_last_interval),
            FOREIGN KEY (start_booking_id) REFERENCES bookings(booking_id)
        );

        CREATE TABLE booking_duration_overrides (
            override_id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_date TEXT NOT NULL,
            booking_id INTEGER NOT NULL,
            override_duration_minutes INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(target_date, booking_id),
            FOREIGN KEY (booking_id) REFERENCES bookings(booking_id)
        );

        CREATE TABLE system_settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE business_calendar (
            calendar_date TEXT PRIMARY KEY,
            is_holiday INTEGER NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE operation_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            booking_id INTEGER,
            booking_number_snapshot INTEGER,
            operation TEXT NOT NULL,
            before_value TEXT,
            after_value TEXT,
            operated_at TEXT NOT NULL,
            operator_name TEXT NOT NULL,
            reason_memo TEXT
        );
        """
    )

    now = datetime.now().isoformat(timespec="seconds")
    defaults = {
        "open_time": "09:00",
        "close_time": "19:00",
        "default_buffer_minutes": "30",
        "buffer_after_last": "true",
        **{k: str(v) for k, v in MENU_DURATION_DEFAULTS.items()},
        **{k: str(v) for k, v in OPTION_DURATION_DEFAULTS.items()},
    }
    for key, value in defaults.items():
        conn.execute(
            "INSERT INTO system_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )


def log_operation(conn: sqlite3.Connection, target_type: str, target_id: str, operation: str, before: Any, after: Any, booking_id: int | None = None) -> None:
    conn.execute(
        """
        INSERT INTO operation_logs (
            target_type, target_id, booking_id, booking_number_snapshot, operation,
            before_value, after_value, operated_at, operator_name, reason_memo
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'user', NULL)
        """,
        (
            target_type,
            str(target_id),
            booking_id,
            booking_id,
            operation,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def load_settings(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT setting_key, setting_value FROM system_settings").fetchall()
    return {row["setting_key"]: row["setting_value"] for row in rows}


def get_dog(conn: sqlite3.Connection, dog_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM dogs WHERE dog_id = ?", (dog_id,)).fetchone()
    if row is None:
        raise ValueError("犬情報が存在しません。")
    return row


def is_holiday(conn: sqlite3.Connection, target: date) -> bool:
    row = conn.execute("SELECT 1 FROM business_calendar WHERE calendar_date = ?", (target.isoformat(),)).fetchone()
    return row is not None


def within_business_hours(start_dt: datetime, settings: dict[str, str]) -> bool:
    open_t = time.fromisoformat(settings["open_time"])
    close_t = time.fromisoformat(settings["close_time"])
    return open_t <= start_dt.time() <= close_t


def validate_booking_datetime(conn: sqlite3.Connection, start_dt: datetime, settings: dict[str, str]) -> ValidationResult:
    if not within_business_hours(start_dt, settings):
        return ValidationResult(False, "固定開始時刻が営業時間外のため保存できません。")
    if is_holiday(conn, start_dt.date()):
        return ValidationResult(False, "休業日のため保存できません。")
    if start_dt.date() > (date.today() + timedelta(days=92)):
        return ValidationResult(False, "固定開始時刻が現在日から3ヶ月超先のため保存できません。")
    return ValidationResult(True)


def resolve_menu_duration(settings: dict[str, str], menu_type: str, size: str, coat_type: str) -> int:
    size_part = {"小": "small", "中": "medium", "大": "large"}[size]
    coat_part = {"長毛": "long", "短毛": "short"}[coat_type]
    if menu_type == "オプションのみ":
        return 0
    if menu_type == "CS":
        return int(settings[f"menu_duration_c_{size_part}_{coat_part}"]) + int(settings[f"menu_duration_s_{size_part}_{coat_part}"])
    menu_prefix = "c" if menu_type == "C" else "s"
    return int(settings[f"menu_duration_{menu_prefix}_{size_part}_{coat_part}"])


def calculate_work_duration(conn: sqlite3.Connection, booking_id: int, booking: sqlite3.Row) -> int:
    today = booking["fixed_start_time"][:10]
    override = conn.execute(
        "SELECT override_duration_minutes FROM booking_duration_overrides WHERE target_date = ? AND booking_id = ?",
        (today, booking_id),
    ).fetchone()
    if override:
        return int(override["override_duration_minutes"])
    if booking["manual_override_duration"]:
        return int(booking["manual_override_duration"])

    options = conn.execute(
        "SELECT option_duration_snapshot, quantity FROM booking_options WHERE booking_id = ? AND is_deleted = 0",
        (booking_id,),
    ).fetchall()
    option_total = sum(int(r["option_duration_snapshot"]) * int(r["quantity"]) for r in options)
    matted = 45 if booking["matted_flag"] and booking["menu_type"] in {"C", "S", "CS"} else 0
    return int(booking["menu_duration_snapshot"]) + matted + option_total


def create_customer(conn: sqlite3.Connection, name: str, phone: str, caution_flag: bool, caution_reason: str, note: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    if not name.strip() or not phone.strip():
        st.error("顧客名と電話番号は必須です。")
        return
    if caution_flag and not caution_reason.strip():
        st.error("注意ありの場合は注意理由が必須です。")
        return
    conn.execute(
        """
        INSERT INTO customers (customer_name, phone, caution_flag, caution_reason, note, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (name.strip(), phone.strip(), int(caution_flag), caution_reason.strip() if caution_flag else None, note.strip()[:1000], now),
    )


def create_dog(conn: sqlite3.Connection, customer_id: int, dog_name: str, size: str, coat_type: str, note: str) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    if not dog_name.strip():
        st.error("犬名は必須です。")
        return
    conn.execute(
        """
        INSERT INTO dogs (customer_id, dog_name, size, coat_type, note, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (customer_id, dog_name.strip(), size, coat_type, note.strip()[:1000], now),
    )


def create_booking(conn: sqlite3.Connection, payload: dict[str, Any]) -> ValidationResult:
    settings = load_settings(conn)
    validation = validate_booking_datetime(conn, payload["fixed_start"], settings)
    if not validation.ok:
        return validation

    dog = get_dog(conn, payload["dog_id"])
    menu_duration = resolve_menu_duration(settings, payload["menu_type"], dog["size"], dog["coat_type"])
    now = datetime.now().isoformat(timespec="seconds")

    cur = conn.execute(
        """
        INSERT INTO bookings (
            trimmer_id, customer_id, dog_id, fixed_start_time, menu_type,
            matted_flag, manual_override_duration, size_snapshot, coat_type_snapshot,
            menu_duration_snapshot, buffer_minutes_snapshot, buffer_after_last_snapshot,
            status, note, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '予約済み', ?, ?)
        """,
        (
            TRIMMER_ID,
            payload["customer_id"],
            payload["dog_id"],
            payload["fixed_start"].isoformat(timespec="minutes"),
            payload["menu_type"],
            int(payload["matted_flag"]),
            payload["manual_override_duration"],
            dog["size"],
            dog["coat_type"],
            menu_duration,
            int(settings["default_buffer_minutes"]),
            1 if settings["buffer_after_last"] == "true" else 0,
            payload["note"][:1000],
            now,
        ),
    )
    booking_id = cur.lastrowid

    for option_name, quantity in payload["options"]:
        if option_name != "部分カット（1箇所）" and quantity != 1:
            return ValidationResult(False, f"{option_name} は数量1のみ保存可能です。")
        snapshot = int(settings[OPTION_KEY_MAP[option_name]])
        conn.execute(
            """
            INSERT INTO booking_options (
                booking_id, option_type, quantity, option_duration_snapshot, is_day_of_addition, is_deleted, updated_at
            ) VALUES (?, ?, ?, ?, 0, 0, ?)
            """,
            (booking_id, option_name, quantity, snapshot, now),
        )

    booking_row = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
    log_operation(conn, "booking", str(booking_id), "create", None, dict(booking_row), booking_id)
    return ValidationResult(True, "予約を保存しました。")


def get_bookings_for_day(conn: sqlite3.Connection, target_date: date) -> pd.DataFrame:
    rows = conn.execute(
        """
        SELECT b.*, c.customer_name, d.dog_name
        FROM bookings b
        JOIN customers c ON b.customer_id = c.customer_id
        JOIN dogs d ON b.dog_id = d.dog_id
        WHERE date(b.fixed_start_time) = ?
        ORDER BY b.fixed_start_time ASC, b.booking_id ASC
        """,
        (target_date.isoformat(),),
    ).fetchall()
    records: list[dict[str, Any]] = []
    for row in rows:
        work_minutes = calculate_work_duration(conn, row["booking_id"], row)
        start_dt = datetime.fromisoformat(row["fixed_start_time"])
        end_dt = start_dt + timedelta(minutes=work_minutes)
        pred_end = end_dt + timedelta(minutes=int(row["buffer_minutes_snapshot"]))
        records.append(
            {
                "予約ID": row["booking_id"],
                "顧客": row["customer_name"],
                "犬": row["dog_name"],
                "固定開始": start_dt.strftime("%H:%M"),
                "作業分": work_minutes,
                "予測終了": pred_end.strftime("%H:%M"),
                "状態": row["status"],
            }
        )
    return pd.DataFrame(records)


def change_status(conn: sqlite3.Connection, booking_id: int, new_status: str) -> None:
    row = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
    if not row:
        return
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute("UPDATE bookings SET status = ?, updated_at = ? WHERE booking_id = ?", (new_status, now, booking_id))
    if new_status == "施術中":
        conn.execute("UPDATE bookings SET actual_start_time = ? WHERE booking_id = ?", (now, booking_id))
    if new_status in {"完了済み", "中断完了", "中断終了", "施術中断"}:
        conn.execute("UPDATE bookings SET actual_end_time = ? WHERE booking_id = ?", (now, booking_id))
    if new_status == "無断キャンセル":
        conn.execute("UPDATE bookings SET no_show_confirmed = 1, no_show_confirmed_at = ? WHERE booking_id = ?", (now, booking_id))
        conn.execute("UPDATE customers SET no_show_count = no_show_count + 1, updated_at = ? WHERE customer_id = ?", (now, row["customer_id"]))
    log_operation(conn, "booking", str(booking_id), "status_change", {"status": row["status"]}, {"status": new_status}, booking_id)


def render_html_output(day_df: pd.DataFrame, target_date: date) -> str:
    total = len(day_df)
    rows_html = "".join(
        f"<tr><td>{r['予約ID']}</td><td>{r['顧客']}</td><td>{r['犬']}</td><td>{r['固定開始']}</td><td>{r['作業分']}分</td><td>{r['予測終了']}</td><td>{r['状態']}</td></tr>"
        for _, r in day_df.iterrows()
    )
    return f"""
    <html><head><meta charset='utf-8'><title>日次サマリー</title></head>
    <body>
      <h1>トリミングサロン 日次出力 ({target_date.isoformat()})</h1>
      <p>当日対応頭数: {total}件</p>
      <h2>ガント / タイムライン参照</h2>
      <p>理由: メニュー時間 + オプション時間 + 毛玉加算 + バッファを用いて予測終了時刻を表示。</p>
      <h2>詳細参照</h2>
      <table border='1' cellspacing='0' cellpadding='4'>
        <tr><th>予約ID</th><th>顧客</th><th>犬</th><th>固定開始</th><th>作業時間</th><th>予測終了</th><th>状態</th></tr>
        {rows_html}
      </table>
      <h2>提出用短縮サマリー</h2>
      <p>本HTMLはブラウザ印刷でPDF出力可能。</p>
    </body></html>
    """


def main() -> None:
    st.set_page_config(page_title="トリミングサロン スケジュール調整ツール v279", layout="wide")
    init_db()
    st.title("トリミングサロン スケジュール調整ツール（仕様v279）")

    with get_conn() as conn:
        tabs = st.tabs([
            "ガント / タイムライン",
            "予約済み一覧",
            "予約検索結果",
            "予約情報タブ",
            "当日対応タブ",
            "施術履歴一覧",
            "設定画面",
            "出力HTML",
        ])

        with tabs[0]:
            target_date = st.date_input("表示日", value=date.today(), key="timeline_date")
            day_df = get_bookings_for_day(conn, target_date)
            st.dataframe(day_df, use_container_width=True)

        with tabs[1]:
            rows = conn.execute(
                """
                SELECT b.booking_id, b.fixed_start_time, b.status, c.customer_name, d.dog_name
                FROM bookings b
                JOIN customers c ON b.customer_id = c.customer_id
                JOIN dogs d ON b.dog_id = d.dog_id
                WHERE b.status IN ('予約済み','未着','施術中','施術中断')
                ORDER BY b.fixed_start_time ASC, b.booking_id ASC
                """
            ).fetchall()
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

        with tabs[2]:
            q = st.text_input("顧客名または犬名で検索")
            status_filter = st.multiselect("状態", BOOKING_STATUSES, default=["予約済み", "未着", "施術中"])
            if st.button("検索実行"):
                rows = conn.execute(
                    """
                    SELECT b.booking_id, b.fixed_start_time, b.status, c.customer_name, d.dog_name
                    FROM bookings b
                    JOIN customers c ON b.customer_id = c.customer_id
                    JOIN dogs d ON b.dog_id = d.dog_id
                    WHERE (c.customer_name LIKE ? OR d.dog_name LIKE ?)
                    AND b.status IN ({})
                    ORDER BY b.fixed_start_time DESC
                    """.format(",".join("?" * len(status_filter))),
                    [f"%{q}%", f"%{q}%", *status_filter],
                ).fetchall()
                st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

        with tabs[3]:
            st.subheader("顧客登録")
            with st.form("customer_form"):
                c_name = st.text_input("顧客名")
                c_phone = st.text_input("電話")
                c_caution = st.checkbox("注意あり")
                c_reason = st.text_input("注意理由")
                c_note = st.text_area("顧客備考", max_chars=1000)
                if st.form_submit_button("顧客保存"):
                    create_customer(conn, c_name, c_phone, c_caution, c_reason, c_note)
                    conn.commit()
                    st.success("顧客を保存しました。")

            customers = conn.execute("SELECT customer_id, customer_name FROM customers WHERE is_active = 1 ORDER BY customer_name").fetchall()
            if customers:
                st.subheader("犬登録")
                with st.form("dog_form"):
                    selected_customer = st.selectbox("顧客", customers, format_func=lambda r: f"{r['customer_name']} (ID:{r['customer_id']})")
                    d_name = st.text_input("犬名")
                    d_size = st.selectbox("体格", ["小", "中", "大"])
                    d_coat = st.selectbox("毛質", ["長毛", "短毛"])
                    d_note = st.text_area("犬備考", max_chars=1000)
                    if st.form_submit_button("犬保存"):
                        create_dog(conn, selected_customer["customer_id"], d_name, d_size, d_coat, d_note)
                        conn.commit()
                        st.success("犬を保存しました。")

            dogs = conn.execute(
                """
                SELECT d.dog_id, d.dog_name, d.customer_id, c.customer_name
                FROM dogs d JOIN customers c ON d.customer_id = c.customer_id
                WHERE d.is_active = 1 ORDER BY d.dog_name
                """
            ).fetchall()
            if customers and dogs:
                st.subheader("新規予約保存（OP-01）")
                with st.form("booking_form"):
                    customer = st.selectbox("顧客", customers, format_func=lambda r: f"{r['customer_name']} (ID:{r['customer_id']})", key="booking_customer")
                    dog_candidates = [d for d in dogs if d["customer_id"] == customer["customer_id"]]
                    dog = st.selectbox("犬", dog_candidates, format_func=lambda r: f"{r['dog_name']} (ID:{r['dog_id']})")
                    booking_date = st.date_input("予約日", value=date.today())
                    booking_time = st.time_input("固定開始時刻", value=time(9, 0), step=300)
                    menu_type = st.selectbox("メニュー", MENU_TYPES)
                    matted_flag = st.checkbox("毛玉/抜け毛が激しい")
                    manual_override = st.number_input("作業時間手動上書き（分、任意）", min_value=1, step=1, value=None)
                    selected_options = st.multiselect("オプション", OPTION_TYPES)
                    options: list[tuple[str, int]] = []
                    for opt in selected_options:
                        qty = st.number_input(f"{opt} 数量", min_value=1, value=1, step=1, key=f"qty_{opt}")
                        options.append((opt, qty))
                    note = st.text_area("予約備考", max_chars=1000)

                    if st.form_submit_button("予約保存"):
                        res = create_booking(
                            conn,
                            {
                                "customer_id": customer["customer_id"],
                                "dog_id": dog["dog_id"],
                                "fixed_start": datetime.combine(booking_date, booking_time),
                                "menu_type": menu_type,
                                "matted_flag": matted_flag,
                                "manual_override_duration": manual_override,
                                "options": options,
                                "note": note,
                            },
                        )
                        if res.ok:
                            conn.commit()
                            st.success(res.message)
                        else:
                            conn.rollback()
                            st.error(res.message)

        with tabs[4]:
            today_rows = conn.execute(
                """
                SELECT b.booking_id, b.status, b.fixed_start_time, c.customer_name, d.dog_name
                FROM bookings b
                JOIN customers c ON b.customer_id = c.customer_id
                JOIN dogs d ON b.dog_id = d.dog_id
                WHERE date(b.fixed_start_time) = date('now', 'localtime')
                ORDER BY b.fixed_start_time ASC, b.booking_id ASC
                """
            ).fetchall()
            for r in today_rows:
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                col1.write(f"ID {r['booking_id']} | {r['fixed_start_time'][11:16]} | {r['customer_name']} / {r['dog_name']} | {r['status']}")
                if col2.button("未着", key=f"late_{r['booking_id']}"):
                    change_status(conn, r["booking_id"], "未着")
                    conn.commit()
                if col3.button("施術中", key=f"start_{r['booking_id']}"):
                    change_status(conn, r["booking_id"], "施術中")
                    conn.commit()
                if col4.button("完了", key=f"done_{r['booking_id']}"):
                    change_status(conn, r["booking_id"], "完了済み")
                    conn.commit()

        with tabs[5]:
            rows = conn.execute(
                """
                SELECT b.booking_id, b.fixed_start_time, b.status, b.actual_start_time, b.actual_end_time, c.customer_name, d.dog_name
                FROM bookings b
                JOIN customers c ON b.customer_id = c.customer_id
                JOIN dogs d ON b.dog_id = d.dog_id
                WHERE b.status IN ('完了済み','中断完了','中断終了','キャンセル','当日キャンセル','無断キャンセル')
                ORDER BY b.fixed_start_time DESC
                """
            ).fetchall()
            st.dataframe(pd.DataFrame([dict(r) for r in rows]), use_container_width=True)

        with tabs[6]:
            st.subheader("設定画面")
            settings = load_settings(conn)
            set_tabs = st.tabs(["設定画面 基本設定タブ", "設定画面 営業日カレンダータブ", "設定画面 監査ログタブ"])
            with set_tabs[0]:
                with st.form("settings_basic"):
                    open_time = st.time_input("営業開始時刻", value=time.fromisoformat(settings["open_time"]), step=300)
                    close_time = st.time_input("営業終了時刻", value=time.fromisoformat(settings["close_time"]), step=300)
                    default_buffer = st.number_input("既定バッファ分数", min_value=0, value=int(settings["default_buffer_minutes"]))
                    after_last = st.checkbox("最終予約後バッファ適用", value=settings["buffer_after_last"] == "true")
                    if st.form_submit_button("保存"):
                        now = datetime.now().isoformat(timespec="seconds")
                        updates = {
                            "open_time": open_time.strftime("%H:%M"),
                            "close_time": close_time.strftime("%H:%M"),
                            "default_buffer_minutes": str(default_buffer),
                            "buffer_after_last": "true" if after_last else "false",
                        }
                        for k, v in updates.items():
                            before = settings[k]
                            conn.execute("UPDATE system_settings SET setting_value = ?, updated_at = ? WHERE setting_key = ?", (v, now, k))
                            log_operation(conn, "system_setting", k, "update", before, v)
                        conn.commit()
                        st.success("基本設定を保存しました。")
            with set_tabs[1]:
                holiday_date = st.date_input("休業日設定日")
                c1, c2 = st.columns(2)
                if c1.button("休業日にする"):
                    now = datetime.now().isoformat(timespec="seconds")
                    conn.execute(
                        "INSERT OR REPLACE INTO business_calendar (calendar_date, is_holiday, updated_at) VALUES (?, 1, ?)",
                        (holiday_date.isoformat(), now),
                    )
                    log_operation(conn, "business_calendar", holiday_date.isoformat(), "set_holiday", None, {"is_holiday": True})
                    conn.commit()
                if c2.button("営業日に戻す"):
                    before = conn.execute("SELECT * FROM business_calendar WHERE calendar_date = ?", (holiday_date.isoformat(),)).fetchone()
                    conn.execute("DELETE FROM business_calendar WHERE calendar_date = ?", (holiday_date.isoformat(),))
                    log_operation(conn, "business_calendar", holiday_date.isoformat(), "unset_holiday", dict(before) if before else None, None)
                    conn.commit()
                holidays = conn.execute("SELECT calendar_date FROM business_calendar ORDER BY calendar_date").fetchall()
                st.write("休業日一覧")
                st.dataframe(pd.DataFrame([dict(r) for r in holidays]), use_container_width=True)
            with set_tabs[2]:
                logs = conn.execute(
                    "SELECT operated_at, target_type, target_id, operation, before_value, after_value FROM operation_logs ORDER BY operated_at DESC LIMIT 200"
                ).fetchall()
                st.dataframe(pd.DataFrame([dict(r) for r in logs]), use_container_width=True)

        with tabs[7]:
            html_date = st.date_input("出力対象日", value=date.today(), key="html_date")
            html_df = get_bookings_for_day(conn, html_date)
            html = render_html_output(html_df, html_date)
            st.download_button("HTML出力を保存", data=html.encode("utf-8"), file_name=f"daily_summary_{html_date.isoformat()}.html", mime="text/html")
            st.code(html[:2000] + ("\n..." if len(html) > 2000 else ""), language="html")


if __name__ == "__main__":
    main()
