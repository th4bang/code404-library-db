# University Library Lending System (MySQL + Python)

**Course:** CSC312 – Practical Assignment 2, University of the Western Cape
**Team:** Code 404


A normalised MySQL database for a university library (members, books, physical copies, authors,
categories, publishers, loans, fines, librarians) and a Python program that connects to it, runs the
ten report queries (Section 6.0 of the report) and offers an interactive menu with a catalogue
search, borrowing and returning.

## What is in this repository

| File | Purpose |
|---|---|
| `library_db.sql` | Creates the `university_library` database, 10 tables with constraints, the sample data, and the ten report queries (Q1–Q10). |
| `app.py` | The Python application: connection, running Q1–Q10, interactive menu, borrow/return transactions. |
| `queries.py` | All SQL used by the application (the same ten queries as in `library_db.sql`). |
| `test_library.py` | 89 automated tests (schema, constraints, queries, application logic, data consistency). |
| `requirements.txt` | Python dependency (`mysql-connector-python`). |
| `docs/sample_run_output.txt` | Output of `python app.py` (all ten queries). |
| `docs/test_results.txt` | Output of the full test run. |

## Requirements

* **MySQL Server 8.0.16 or newer** (older versions silently ignore `CHECK` constraints).
* **Python 3.9 or newer** (developed and tested with 3.12).
* A MySQL user that can create databases (for example `root`).

## Quick start

```bash
# 1. install the driver
pip install -r requirements.txt

# 2. tell the program how to reach MySQL (or just wait for the password prompt)
export DB_USER=root                  # Windows PowerShell:  $env:DB_USER = "root"
export DB_PASSWORD=your_password     # Windows PowerShell:  $env:DB_PASSWORD = "your_password"
# optional: DB_HOST (default 127.0.0.1), DB_PORT (3306), DB_NAME (university_library)

# 3. create + fill the database from library_db.sql, then run all ten queries
python app.py --setup --yes
```

The last line of the output should read `SUMMARY: 10/10 queries executed successfully`.

You can also build the database in MySQL Workbench instead of step 3: *File → Run SQL Script…* and
choose `library_db.sql`; then run `python app.py`.

## Using the program

| Command | What it does |
|---|---|
| `python app.py` | Runs all ten report queries and prints each result as a table (default). |
| `python app.py --query 7` | Runs one query (1–10). |
| `python app.py --list` | Lists the queries and their difficulty level (no database needed). |
| `python app.py --menu` | Interactive menu: run queries, search the catalogue by title or author, show a member's loans, borrow a copy, return a copy. |
| `python app.py --setup --yes` | Drops and re-creates the database from `library_db.sql` (asks for confirmation without `--yes`). |
| `python app.py --as-of 2026-10-11` | Sets the program's "today" (see below). |

Connection options can also be given as `--host`, `--port`, `--user`, `--database`.
The password is never stored in the code: it comes from `DB_PASSWORD` or an interactive prompt.

### About the date

The sample data was prepared on **11 October 2026**, so the program's "today" defaults to that date.
This keeps the "overdue" results (Q7, member loan status, fines on return) reproducible when the
project is marked later. Use `--as-of today` to run against the real current date.

### Business rules implemented by borrow/return

* A member must exist and be **Active** to borrow; the librarian (by staff number) must exist.
* Only a copy that is **Available** (and has no open loan) can be lent; the loan period is **14 days**.
* The new loan and the copy's `On Loan` status are saved in **one transaction**; a failure rolls both back.
* On return, a copy returned **late** is fined **R5.00 per day late**; a copy returned **Damaged**
  is fined a flat **R150.00** and set to `Under Repair`. A loan has at most one fine, so the damage fine
  takes precedence over a late fine. These rates match the sample data in `library_db.sql`.

## Running the tests

```bash
python -m unittest -v test_library
```

The tests build a scratch database called `university_library_test`, run against it, and drop it at the
end; your real `university_library` database is not touched. Expected result: `Ran 89 tests ... OK`.

## Troubleshooting

| Message | Fix |
|---|---|
| `Access denied for user ...` | Check `DB_USER` / `DB_PASSWORD`. |
| `Cannot connect to MySQL at 127.0.0.1:3306` | Start the MySQL server, or set `DB_HOST` / `DB_PORT`. |
| `Database 'university_library' does not exist` | Run `python app.py --setup --yes`. |
| `The MySQL driver is not installed` | Run `pip install -r requirements.txt`. |
| Tests report skipped / CHECK errors | Use MySQL 8.0.16 or newer. |
