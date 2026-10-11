"""
=====================================================================
Team Name       : Code 404
Student numbers : <STUDENT_NO_1>, <STUDENT_NO_2>, <STUDENT_NO_3>,
                  <STUDENT_NO_4>, <STUDENT_NO_5>
File name       : app.py
Course          : CSC312 - Practical Assignment 2 (University of the Western Cape)
Project         : University Library Lending System (MySQL + Python)
=====================================================================

Python application for the university_library MySQL database.

What it does
------------
1. Connects to MySQL with the official MySQL Connector/Python driver.
2. Runs the ten report queries from Section 6.0 (Q1-Q10) and prints the
   results as tables.  This is the default action.
3. Offers an interactive menu (--menu) with a catalogue search, a member
   loan list, and two transactional operations: borrowing and returning
   a book copy (fines are created automatically for late/damaged returns).

Quick start
-----------
    pip install -r requirements.txt
    python app.py --setup --yes     # create + fill the database, then run Q1-Q10
    python app.py                   # run Q1-Q10 again
    python app.py --menu            # interactive menu
    python app.py --query 7         # run a single query

Connection settings are read from the environment (DB_HOST, DB_PORT,
DB_USER, DB_PASSWORD, DB_NAME) or from command-line options.  If no
password is given, the program asks for it; passwords are never stored
in the source code.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
import textwrap
import time
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional, Sequence

try:
    import mysql.connector
    from mysql.connector import Error as MySQLError
except ImportError:  # pragma: no cover - only happens when the driver is missing
    sys.exit(
        "The MySQL driver is not installed.\n"
        "Install it with:  pip install -r requirements.txt"
    )

import queries as q

# ---------------------------------------------------------------------
# Constants (business rules taken from the sample data in library_db.sql)
# ---------------------------------------------------------------------
SQL_FILE = Path(__file__).with_name("library_db.sql")
DEFAULT_DATABASE = "university_library"
# The sample data was prepared on this date, so the application's "today"
# defaults to it.  This keeps "overdue" results reproducible; use
# --as-of today to run against the real current date.
DEFAULT_AS_OF = date(2026, 10, 11)
LOAN_PERIOD_DAYS = 14                        # "Loan period = 14 days"
OVERDUE_FINE_PER_DAY = Decimal("5.00")       # "R5.00 per day late"
DAMAGE_FINE = Decimal("150.00")              # "damaged book = flat R150.00"
CONDITIONS = ("New", "Good", "Fair", "Damaged")
LINE_WIDTH = 78


# ---------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------
class AppError(Exception):
    """Base class for errors that are shown to the user as a message."""


class DatabaseConnectionError(AppError):
    """The program could not connect to MySQL (message explains how to fix it)."""


class LibraryError(AppError):
    """A library business rule was broken (e.g. the copy is already on loan)."""


# ---------------------------------------------------------------------
# Configuration and connection
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class DBConfig:
    host: str
    port: int
    user: str
    password: str
    database: str


def load_config(args: Optional[argparse.Namespace] = None, prompt: bool = True) -> DBConfig:
    """Build the connection settings: command line > environment > defaults."""

    def pick(arg_name: str, env_name: str, default: Any) -> Any:
        value = getattr(args, arg_name, None) if args is not None else None
        if value not in (None, ""):
            return value
        return os.environ.get(env_name) or default

    try:
        port = int(pick("port", "DB_PORT", 3306))
    except ValueError:
        raise AppError("The MySQL port must be a whole number (e.g. 3306).") from None

    if "DB_PASSWORD" in os.environ:
        password = os.environ["DB_PASSWORD"]
    elif prompt and sys.stdin.isatty():
        password = getpass.getpass("MySQL password (press Enter for none): ")
    else:
        password = ""

    return DBConfig(
        host=pick("host", "DB_HOST", "127.0.0.1"),
        port=port,
        user=pick("user", "DB_USER", "root"),
        password=password,
        database=pick("database", "DB_NAME", DEFAULT_DATABASE),
    )


def describe_connection_error(err: MySQLError, cfg: DBConfig) -> str:
    """Turn a MySQL error number into a message that says what to do next."""
    hints = {
        1045: f"Access denied for user '{cfg.user}'. Check DB_USER and DB_PASSWORD.",
        1044: f"User '{cfg.user}' is not allowed to use database '{cfg.database}'.",
        1049: (f"Database '{cfg.database}' does not exist. "
               "Create it first with:  python app.py --setup"),
        2002: f"Cannot reach the MySQL server through its socket ({err.msg}).",
        2003: (f"Cannot connect to MySQL at {cfg.host}:{cfg.port}. "
               "Is the server running, and are the host and port correct?"),
        2005: f"Unknown MySQL host '{cfg.host}'.",
    }
    return hints.get(err.errno, f"MySQL error {err.errno}: {err.msg}")


def connect(cfg: DBConfig, use_database: bool = True, as_of: Optional[date] = None):
    """Open a connection (autocommit on).  Raises DatabaseConnectionError."""
    settings: dict[str, Any] = dict(
        host=cfg.host, port=cfg.port, user=cfg.user, password=cfg.password,
        connection_timeout=10, autocommit=True, charset="utf8mb4",
    )
    if use_database:
        settings["database"] = cfg.database
    try:
        conn = mysql.connector.connect(**settings)
    except MySQLError as err:
        raise DatabaseConnectionError(describe_connection_error(err, cfg)) from err
    if as_of is not None:
        set_clock(conn, as_of)
    return conn


def set_clock(conn, as_of: date) -> None:
    """Store the application's 'today' in the session variable @as_of (used by Q7)."""
    cur = conn.cursor()
    cur.execute("SET @as_of = %s", (as_of.isoformat(),))
    cur.close()


def parse_as_of(text: str) -> date:
    """Parse --as-of: either 'today' or a date written as YYYY-MM-DD."""
    if text.lower() == "today":
        return date.today()
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"'{text}' is not a valid date; use YYYY-MM-DD or the word 'today'."
        ) from None


# ---------------------------------------------------------------------
# Building the database from library_db.sql
# ---------------------------------------------------------------------
_DDL_DML_WORDS = {"DROP", "CREATE", "USE", "INSERT", "SET", "ALTER"}


def split_sql_statements(text: str) -> list[str]:
    """Split an SQL script into statements.

    Handles -- and # comments, /* */ comments and quoted strings (a ';'
    inside quotes does not end a statement).
    """
    statements: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)
    quote: Optional[str] = None
    while i < n:
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\" and quote != "`" and i + 1 < n:
                buf.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                if i + 1 < n and text[i + 1] == quote:   # doubled quote = literal quote
                    buf.append(text[i + 1])
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
            i += 1
        elif ch == "#" or (text.startswith("--", i) and (i + 2 >= n or text[i + 2] in " \t\r\n")):
            end = text.find("\n", i)
            i = n if end == -1 else end
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        elif ch == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            i += 1
        else:
            buf.append(ch)
            i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def _check_db_name(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name):
        raise AppError(f"'{name}' is not a valid database name (use letters, digits, underscore).")
    return name


def setup_database(cfg: DBConfig, sql_path: Path = SQL_FILE) -> int:
    """Drop and re-create cfg.database from library_db.sql; return statements run.

    Only schema/data statements are run (DROP, CREATE, USE, INSERT, SET);
    the SELECT queries at the end of the file are skipped.
    """
    name = _check_db_name(cfg.database)
    if not sql_path.exists():
        raise AppError(f"Cannot find the SQL script: {sql_path}")
    script = re.sub(r"\buniversity_library\b", name, sql_path.read_text(encoding="utf8"))
    conn = connect(cfg, use_database=False)
    cur = conn.cursor()
    executed = 0
    try:
        for statement in split_sql_statements(script):
            if statement.split(None, 1)[0].upper() not in _DDL_DML_WORDS:
                continue
            cur.execute(statement)
            if cur.with_rows:
                cur.fetchall()
            executed += 1
    except MySQLError as err:
        raise AppError(f"Setup failed on statement #{executed + 1}: {err.msg}") from err
    finally:
        cur.close()
        conn.close()
    return executed


def drop_database(cfg: DBConfig) -> None:
    """Drop cfg.database (used by the tests to remove their scratch database)."""
    name = _check_db_name(cfg.database)
    conn = connect(cfg, use_database=False)
    try:
        cur = conn.cursor()
        cur.execute(f"DROP DATABASE IF EXISTS `{name}`")
        cur.close()
    finally:
        conn.close()


# ---------------------------------------------------------------------
# Running queries and printing tables
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class QueryResult:
    columns: tuple[str, ...]
    rows: list[tuple]
    seconds: float


def run_sql(conn, sql: str, params: Optional[Sequence[Any]] = None) -> QueryResult:
    """Execute one statement and return all rows.  Values go in via params."""
    cur = conn.cursor()
    try:
        start = time.perf_counter()
        cur.execute(sql, params)
        rows = cur.fetchall()
        elapsed = time.perf_counter() - start
        return QueryResult(tuple(cur.column_names), rows, elapsed)
    finally:
        cur.close()


def run_query(conn, query: q.Query) -> QueryResult:
    """Run one of the ten report queries."""
    return run_sql(conn, query.sql)


def format_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf8", "replace")
    return str(value)          # dates print as YYYY-MM-DD


def format_table(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> str:
    """Draw a result set as a text table (numbers right-aligned)."""
    cells = [[format_value(v) for v in row] for row in rows]
    numeric = [
        bool(rows) and all(isinstance(r[i], (int, float, Decimal)) for r in rows if r[i] is not None)
        and any(r[i] is not None for r in rows)
        for i in range(len(columns))
    ]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(columns)]
    rule = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def line(values: Sequence[str]) -> str:
        parts = [
            f" {v.rjust(widths[i]) if numeric[i] else v.ljust(widths[i])} "
            for i, v in enumerate(values)
        ]
        return "|" + "|".join(parts) + "|"

    out = [rule, line(list(columns)), rule]
    out += [line(r) for r in cells]
    out.append(rule)
    return "\n".join(out)


def print_result(result: QueryResult) -> None:
    print(format_table(result.columns, result.rows))
    print(f"{len(result.rows)} row(s) in {result.seconds * 1000:.1f} ms")


def print_query_header(query: q.Query) -> None:
    print("=" * LINE_WIDTH)
    print(f"Q{query.number}  [{query.level}]  {query.title}")
    purpose = query.purpose[0].upper() + query.purpose[1:]
    print(textwrap.fill("Purpose: " + purpose, LINE_WIDTH, subsequent_indent="         ",
                        break_on_hyphens=False))
    print("-" * LINE_WIDTH)


def run_report(conn, numbers: Optional[Sequence[int]] = None) -> int:
    """Run the chosen report queries (default: all ten); return the failure count."""
    selected = [q.get_query(n) for n in numbers] if numbers else list(q.QUERIES)
    failures: list[str] = []
    total = 0.0
    for query in selected:
        print_query_header(query)
        try:
            result = run_query(conn, query)
        except MySQLError as err:
            failures.append(f"Q{query.number}")
            print(f"FAILED: MySQL error {err.errno}: {err.msg}")
            continue
        total += result.seconds
        print_result(result)
    print("=" * LINE_WIDTH)
    ok = len(selected) - len(failures)
    print(f"SUMMARY: {ok}/{len(selected)} queries executed successfully "
          f"(total {total * 1000:.1f} ms)")
    if failures:
        print("Failed: " + ", ".join(failures))
    return len(failures)


# ---------------------------------------------------------------------
# Application features: search, member loans
# ---------------------------------------------------------------------
def like_pattern(keyword: str) -> str:
    """Wrap a keyword as a LIKE pattern, treating % and _ typed by the user literally."""
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_catalogue(conn, keyword: str) -> QueryResult:
    """Find books whose title or author name contains the keyword."""
    keyword = keyword.strip()
    if not keyword:
        raise LibraryError("Please enter a search word.")
    pattern = like_pattern(keyword)
    return run_sql(conn, q.SEARCH_CATALOGUE_SQL, (pattern, pattern))


def member_loans(conn, campus_number: str) -> QueryResult:
    """List every loan of the member with this campus number."""
    campus_number = campus_number.strip()
    if not _fetch_one(conn, q.FIND_MEMBER_SQL, (campus_number,)):
        raise LibraryError(f"There is no member with campus number '{campus_number}'.")
    return run_sql(conn, q.MEMBER_LOANS_SQL, (campus_number,))


def _fetch_one(conn, sql: str, params: Sequence[Any]) -> Optional[dict]:
    cur = conn.cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        cur.close()


# ---------------------------------------------------------------------
# Application features: borrowing and returning (transactions)
# ---------------------------------------------------------------------
@dataclass(frozen=True)
class BorrowReceipt:
    loan_id: int
    member_name: str
    title: str
    copy_id: int
    loan_date: date
    due_date: date


@dataclass(frozen=True)
class ReturnReceipt:
    loan_id: int
    member_name: str
    title: str
    return_date: date
    days_late: int
    fine_amount: Optional[Decimal]
    fine_reason: Optional[str]
    copy_status: str


def _librarian_id(conn, staff_number: str) -> int:
    row = _fetch_one(conn, q.FIND_LIBRARIAN_SQL, (staff_number.strip(),))
    if not row:
        raise LibraryError(f"There is no librarian with staff number '{staff_number}'.")
    return row["librarian_id"]


def borrow_copy(conn, campus_number: str, copy_id: int, staff_number: str,
                today: date) -> BorrowReceipt:
    """Lend one copy to a member.

    Rules: the member must exist and be Active; the librarian must exist;
    the copy must exist and be 'Available' with no open loan.  The new Loan
    row and the copy's 'On Loan' status are saved together (one transaction),
    so a failure can never leave only half of the change in the database.
    """
    conn.start_transaction()
    try:
        member = _fetch_one(conn, q.FIND_MEMBER_SQL, (campus_number.strip(),))
        if not member:
            raise LibraryError(f"There is no member with campus number '{campus_number}'.")
        if member["status"] != "Active":
            raise LibraryError(
                f"{member['first_name']} {member['last_name']} is {member['status']}; "
                "only Active members may borrow."
            )
        librarian_id = _librarian_id(conn, staff_number)

        copy = _fetch_one(conn, q.FIND_COPY_FOR_UPDATE_SQL, (copy_id,))
        if not copy:
            raise LibraryError(f"There is no book copy with id {copy_id}.")
        if copy["availability_status"] != "Available":
            raise LibraryError(
                f"Copy {copy_id} of '{copy['title']}' cannot be lent: "
                f"it is {copy['availability_status']}."
            )
        open_loans = _fetch_one(conn, q.COUNT_ACTIVE_LOANS_OF_COPY_SQL, (copy_id,))["n"]
        if open_loans:
            raise LibraryError(
                f"Copy {copy_id} is marked Available but has an open loan; "
                "please ask a librarian to correct the record."
            )

        due = today + timedelta(days=LOAN_PERIOD_DAYS)
        cur = conn.cursor()
        cur.execute(q.INSERT_LOAN_SQL, (member["member_id"], copy_id, librarian_id, today, due))
        loan_id = cur.lastrowid
        cur.execute(q.MARK_COPY_ON_LOAN_SQL, (copy_id,))
        cur.close()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return BorrowReceipt(
        loan_id=loan_id,
        member_name=f"{member['first_name']} {member['last_name']}",
        title=copy["title"], copy_id=copy_id, loan_date=today, due_date=due,
    )


def return_copy(conn, copy_id: int, staff_number: str, today: date,
                condition: Optional[str] = None) -> ReturnReceipt:
    """Take a copy back and create a fine if it is damaged or late.

    The librarian may record the copy's condition on return (None = unchanged).
    A loan has at most one fine (UNIQUE on Fine.loan_id), so a damaged copy
    gets the flat damage fine, which takes precedence over a late fine.
    """
    if condition is not None and condition not in CONDITIONS:
        raise LibraryError(f"Condition must be one of: {', '.join(CONDITIONS)}.")
    conn.start_transaction()
    try:
        librarian_id = _librarian_id(conn, staff_number)
        loan = _fetch_one(conn, q.FIND_ACTIVE_LOAN_FOR_UPDATE_SQL, (copy_id,))
        if not loan:
            raise LibraryError(f"Copy {copy_id} is not currently on loan.")
        if today < loan["loan_date"]:
            raise LibraryError(
                f"The return date {today} is before the loan date {loan['loan_date']}."
            )

        new_condition = condition or loan["condition_status"]
        days_late = max((today - loan["due_date"]).days, 0)
        fine_amount: Optional[Decimal] = None
        fine_reason: Optional[str] = None
        if new_condition == "Damaged":
            fine_amount, fine_reason = DAMAGE_FINE, "Damaged"
        elif days_late > 0:
            fine_amount, fine_reason = OVERDUE_FINE_PER_DAY * days_late, "Overdue"
        copy_status = "Under Repair" if new_condition == "Damaged" else "Available"

        cur = conn.cursor()
        cur.execute(q.CLOSE_LOAN_SQL, (today, librarian_id, loan["loan_id"]))
        if fine_amount is not None:
            cur.execute(q.INSERT_FINE_SQL, (loan["loan_id"], fine_amount, fine_reason, today))
        cur.execute(q.RELEASE_COPY_SQL, (copy_status, new_condition, copy_id))
        cur.close()
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return ReturnReceipt(
        loan_id=loan["loan_id"],
        member_name=f"{loan['first_name']} {loan['last_name']}",
        title=loan["title"], return_date=today, days_late=days_late,
        fine_amount=fine_amount, fine_reason=fine_reason, copy_status=copy_status,
    )


# ---------------------------------------------------------------------
# Interactive menu
# ---------------------------------------------------------------------
MENU = """
Library Lending System - Code 404
  1) Run all report queries (Q1-Q10)
  2) Run one report query
  3) Search the catalogue (title or author)
  4) Show a member's loans
  5) Borrow a book copy
  6) Return a book copy
  0) Exit"""


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        raise KeyboardInterrupt from None


def _ask_int(prompt: str) -> int:
    text = _ask(prompt)
    try:
        return int(text)
    except ValueError:
        raise LibraryError(f"'{text}' is not a whole number.") from None


def menu_loop(conn, as_of: date) -> None:
    print(f"System date: {as_of}")
    while True:
        print(MENU)
        try:
            choice = _ask("Choose an option: ")
            if choice == "0":
                print("Goodbye.")
                return
            if choice == "1":
                run_report(conn)
            elif choice == "2":
                number = _ask_int(f"Query number (1-{len(q.QUERIES)}): ")
                if not 1 <= number <= len(q.QUERIES):
                    raise LibraryError(f"Query number must be between 1 and {len(q.QUERIES)}.")
                run_report(conn, [number])
            elif choice == "3":
                print_result(search_catalogue(conn, _ask("Search word: ")))
            elif choice == "4":
                print_result(member_loans(conn, _ask("Member campus number (e.g. S3900101): ")))
            elif choice == "5":
                receipt = borrow_copy(
                    conn, _ask("Member campus number: "), _ask_int("Copy id: "),
                    _ask("Your staff number (e.g. LIB001): "), as_of)
                print(f"OK: loan {receipt.loan_id} - '{receipt.title}' lent to "
                      f"{receipt.member_name}, due {receipt.due_date}.")
            elif choice == "6":
                copy_id = _ask_int("Copy id: ")
                staff = _ask("Your staff number (e.g. LIB001): ")
                cond = _ask("Condition on return (New/Good/Fair/Damaged, Enter = unchanged): ")
                receipt = return_copy(conn, copy_id, staff, as_of, cond.capitalize() or None)
                print(f"OK: '{receipt.title}' returned by {receipt.member_name}; "
                      f"copy is now {receipt.copy_status}.")
                if receipt.fine_amount is not None:
                    print(f"Fine recorded: R{receipt.fine_amount} "
                          f"({receipt.fine_reason}; {receipt.days_late} day(s) late).")
                else:
                    print("No fine.")
            else:
                print("Please choose a number from the menu.")
        except LibraryError as err:
            print(f"Cannot do that: {err}")
        except MySQLError as err:
            print(f"Database error {err.errno}: {err.msg}")
        except KeyboardInterrupt:
            print("\nGoodbye.")
            return


# ---------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="University Library Lending System (CSC312, team Code 404). "
                    "By default the ten report queries are run and printed.")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--menu", action="store_true", help="start the interactive menu")
    mode.add_argument("--query", type=int, metavar="N", help="run only report query N (1-10)")
    mode.add_argument("--list", action="store_true", help="list the report queries and exit")
    p.add_argument("--setup", action="store_true",
                   help="DROP and re-create the database from library_db.sql first")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation with --setup")
    p.add_argument("--as-of", type=parse_as_of, default=DEFAULT_AS_OF, metavar="DATE",
                   help="the application's 'today' (YYYY-MM-DD or 'today'; default %(default)s)")
    p.add_argument("--host", help="MySQL host (env DB_HOST, default 127.0.0.1)")
    p.add_argument("--port", help="MySQL port (env DB_PORT, default 3306)")
    p.add_argument("--user", help="MySQL user (env DB_USER, default root)")
    p.add_argument("--database", help=f"database name (env DB_NAME, default {DEFAULT_DATABASE})")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.list:
        for query in q.QUERIES:
            print(f"Q{query.number:<2} [{query.level:<7}] {query.title}")
        return 0
    if args.query is not None and not 1 <= args.query <= len(q.QUERIES):
        print(f"ERROR: --query must be between 1 and {len(q.QUERIES)}.", file=sys.stderr)
        return 2

    try:
        cfg = load_config(args)
        if args.setup:
            if not args.yes:
                if not sys.stdin.isatty():
                    raise AppError("--setup needs confirmation; add --yes to run it unattended.")
                answer = input(f"This will DROP and re-create database '{cfg.database}'. "
                               "Type YES to continue: ")
                if answer.strip() != "YES":
                    print("Setup cancelled.")
                    return 1
            count = setup_database(cfg)
            print(f"Database '{cfg.database}' created from {SQL_FILE.name} "
                  f"({count} statements).")
        conn = connect(cfg, as_of=args.as_of)
    except AppError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 2

    try:
        version = run_sql(conn, "SELECT VERSION()").rows[0][0]
        print(f"Connected to MySQL {version} at {cfg.host}:{cfg.port}, "
              f"database '{cfg.database}' (system date {args.as_of}).")
        if args.menu:
            menu_loop(conn, args.as_of)
            return 0
        failures = run_report(conn, [args.query] if args.query else None)
        return 1 if failures else 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
