"""
=====================================================================
Team Name       : Code 404
Student numbers : <STUDENT_NO_1>, <STUDENT_NO_2>, <STUDENT_NO_3>,
                  <STUDENT_NO_4>, <STUDENT_NO_5>
File name       : test_library.py
Course          : CSC312 - Practical Assignment 2 (University of the Western Cape)
Project         : University Library Lending System (MySQL + Python)
=====================================================================

Automated tests for the database, the ten report queries and app.py.

How it works
------------
The tests never touch the real 'university_library' database.  They build
a scratch database called 'university_library_test' from library_db.sql,
run all tests against it and drop it again at the end.

Run (same connection settings as app.py):
    python -m unittest -v test_library
Needs MySQL 8.0.16 or newer (earlier versions ignore CHECK constraints) and
a MySQL user that may CREATE / DROP databases.

Test groups
-----------
A  schema     : tables, keys, foreign keys, checks, row counts
B  constraints: invalid data is rejected; cascades and defaults work
C  queries    : Q1-Q10 return the exact expected results
D  application: search, borrow, return, fines, rollback, locking
E  consistency: business-rule invariants hold in the data
F  plumbing   : SQL splitter, formatter, config, connection errors, CLI
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import subprocess
import sys
import threading
import time
import unittest
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from mysql.connector import Error as MySQLError
from mysql.connector.errors import Error as ConnectorError

import app
import queries
import queries as q

HERE = Path(__file__).resolve().parent
TEST_DB = "university_library_test"
TODAY = app.DEFAULT_AS_OF                      # 2026-10-11

# MySQL error numbers (MariaDB reports CHECK violations as 4025)
CHECK_FAILED = (3819, 4025)
DUPLICATE = (1062,)
FK_CHILD = (1452,)        # cannot add/update a child row
FK_PARENT = (1451,)       # cannot delete/update a parent row
NOT_NULL = (1048,)
BAD_ENUM = (1265, 1366)

# Expected results of Q1-Q10 on the sample data, as of 2026-10-11.
# Q1-Q5 were checked against the MySQL Workbench screenshots in the report;
# Q6-Q10 were checked by hand calculation from the INSERT statements.
GOLDEN = {1: (['fine_id', 'loan_id', 'fine_amount', 'reason', 'fine_date'],
     [('5', '10', '150.00', 'Damaged', '2026-09-28'),
      ('4', '9', '40.00', 'Overdue', '2026-10-02'),
      ('3', '7', '20.00', 'Overdue', '2026-09-20')]),
 2: (['category_name', 'titles', 'total_copies', 'available_copies'],
     [('Databases', '3', '7', '5'),
      ('Biography', '2', '4', '4'),
      ('Operating Systems', '2', '4', '3'),
      ('Algorithms', '1', '2', '1'),
      ('Artificial Intelligence', '1', '2', '1'),
      ('Literature', '1', '2', '1')]),
 3: (['member_name', 'member_type', 'total_loans', 'total_fines'],
     [('Sipho Ndlovu', 'Student', '1', '150.00'),
      ('Aisha Patel', 'Student', '2', '95.00'),
      ('Naledi Khumalo', 'Student', '1', '50.00'),
      ('Zanele Nkosi', 'Student', '1', '20.00'),
      ('Thabo Mokoena', 'Student', '3', '0.00'),
      ('Lwazi Dlamini', 'Student', '2', '0.00'),
      ('Ruan van der Merwe', 'Student', '2', '0.00'),
      ('Fatima Abrahams', 'Student', '1', '0.00'),
      ('Nomsa Zulu', 'Staff', '1', '0.00'),
      ('Pieter Botha', 'Lecturer', '1', '0.00'),
      ('Lerato Mahlangu', 'Student', '0', '0.00')]),
 4: (['title', 'authors', 'times_borrowed'],
     [('Fundamentals of Database Systems', 'Ramez Elmasri, Shamkant Navathe', '3'),
      ('Artificial Intelligence: A Modern Approach', 'Peter Norvig, Stuart Russell', '2'),
      ('Database System Concepts', 'Henry Korth, Abraham Silberschatz, S. Sudarshan', '2'),
      ('Introduction to Algorithms',
       'Thomas Cormen, Charles Leiserson, Ronald Rivest, Clifford Stein',
       '2')]),
 5: (['category_name', 'fines_issued', 'total_fines', 'outstanding'],
     [('Literature', '1', '150.00', '150.00'),
      ('Databases', '2', '95.00', '40.00'),
      ('Artificial Intelligence', '1', '50.00', '0.00')]),
 6: (['book_id', 'isbn', 'title', 'publication_year'],
     [('2', '9780078022159', 'Database System Concepts', '2019'),
      ('1', '9780133970777', 'Fundamentals of Database Systems', '2016'),
      ('3', '9780132943260', 'Database Systems: A Practical Approach', '2014')]),
 7: (['member_name', 'email', 'overdue_loans', 'titles', 'max_days_overdue', 'estimated_fine'],
     [('Lwazi Dlamini', 'lwazi.dlamini@myuwc.ac.za', '1', 'Operating System Concepts', '7', '35.00'),
      ('Nomsa Zulu',
       'nomsa.zulu@uwc.ac.za',
       '1',
       'Artificial Intelligence: A Modern Approach',
       '2',
       '10.00')]),
 8: (['loan_month',
      'member_type',
      'loans_issued',
      'returned',
      'late_returns',
      'avg_days_kept',
      'pct_of_all_loans'],
     [('2026-08', 'Student', '5', '5', '2', '17.4', '33.3'),
      ('2026-09', 'Student', '6', '5', '2', '15.8', '40.0'),
      ('2026-09', 'Lecturer', '1', '0', '0', 'NULL', '6.7'),
      ('2026-09', 'Staff', '1', '0', '0', 'NULL', '6.7'),
      ('2026-10', 'Student', '2', '0', '0', 'NULL', '13.3')]),
 9: (['member_name',
      'member_type',
      'status',
      'returned_loans',
      'late_returns',
      'late_rate_pct',
      'total_fines'],
     [('Sipho Ndlovu', 'Student', 'Suspended', '1', '0', '0.0', '150.00'),
      ('Aisha Patel', 'Student', 'Active', '2', '2', '100.0', '95.00')]),
 10: (['copy_id',
       'title',
       'copy_no',
       'category_name',
       'publisher_name',
       'condition_status',
       'availability_status',
       'times_loaned',
       'last_loaned'],
      [('18',
        'Things Fall Apart',
        '1',
        'Literature',
        'Heinemann',
        'Damaged',
        'Under Repair',
        '1',
        '2026-09-15'),
       ('14',
        'Long Walk to Freedom',
        '1',
        'Biography',
        'Little, Brown',
        'Fair',
        'Available',
        '1',
        '2026-09-02'),
       ('6',
        'Database Systems: A Practical Approach',
        '1',
        'Databases',
        'Pearson',
        'Fair',
        'Available',
        '1',
        '2026-08-20')])}


def test_config() -> app.DBConfig:
    return dataclasses.replace(app.load_config(prompt=False), database=TEST_DB)


def setUpModule() -> None:
    cfg = test_config()
    conn = app.connect(cfg, use_database=False)
    version = app.run_sql(conn, "SELECT VERSION()").rows[0][0]
    conn.close()
    numbers = tuple(int(x) for x in re.match(r"(\d+)\.(\d+)\.(\d+)", version).groups())
    if "MariaDB" not in version and numbers < (8, 0, 16):
        raise unittest.SkipTest(f"MySQL {version} ignores CHECK constraints; use 8.0.16 or newer.")


def tearDownModule() -> None:
    app.drop_database(test_config())


class DBTestCase(unittest.TestCase):
    """Base class: opens a connection to the scratch database."""

    rebuild_each_test = False

    @classmethod
    def build(cls) -> None:
        cls.cfg = test_config()
        app.setup_database(cls.cfg)

    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = test_config()
        if not cls.rebuild_each_test:
            cls.build()

    def setUp(self) -> None:
        if self.rebuild_each_test:
            self.build()
        self.conn = app.connect(self.cfg, as_of=TODAY)
        self.addCleanup(self.conn.close)

    # -- helpers ------------------------------------------------------
    def rows(self, sql, params=None):
        return app.run_sql(self.conn, sql, params).rows

    def scalar(self, sql, params=None):
        return self.rows(sql, params)[0][0]

    def execute(self, sql, params=None):
        cur = self.conn.cursor()
        try:
            cur.execute(sql, params)
        finally:
            cur.close()

    def assertDbError(self, errnos, sql, params=None):
        with self.assertRaises(MySQLError) as ctx:
            self.execute(sql, params)
        self.assertIn(ctx.exception.errno, errnos, f"unexpected error: {ctx.exception}")


# =====================================================================
# A. Schema
# =====================================================================
class TestA_Schema(DBTestCase):

    TABLES = {"Author", "Author_Book", "Book", "Book_Copy", "Category",
              "Fine", "Librarian", "Loan", "Member", "Publisher"}

    def q(self, what):
        return f"""SELECT COUNT(*) FROM information_schema.{what}
                   WHERE {'TABLE_SCHEMA' if what != 'CHECK_CONSTRAINTS' else 'CONSTRAINT_SCHEMA'} = %s"""

    def test_A01_all_ten_tables_exist(self):
        """The database contains exactly the ten designed tables."""
        found = {r[0] for r in self.rows(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s", (TEST_DB,))}
        self.assertEqual(found, self.TABLES)

    def test_A02_every_table_has_a_primary_key(self):
        """Each of the ten tables has a PRIMARY KEY."""
        n = self.scalar(self.q("TABLE_CONSTRAINTS") + " AND CONSTRAINT_TYPE = 'PRIMARY KEY'", (TEST_DB,))
        self.assertEqual(n, 10)

    def test_A03_foreign_keys_match_the_design(self):
        """The ten foreign keys link exactly the tables shown in the ERD."""
        found = {(r[0], r[1], r[2]) for r in self.rows(
            """SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME
               FROM information_schema.KEY_COLUMN_USAGE
               WHERE TABLE_SCHEMA = %s AND REFERENCED_TABLE_NAME IS NOT NULL""", (TEST_DB,))}
        expected = {
            ("Book", "category_id", "Category"), ("Book", "publisher_id", "Publisher"),
            ("Author_Book", "book_id", "Book"), ("Author_Book", "author_id", "Author"),
            ("Book_Copy", "book_id", "Book"),
            ("Loan", "member_id", "Member"), ("Loan", "copy_id", "Book_Copy"),
            ("Loan", "issued_by", "Librarian"), ("Loan", "received_by", "Librarian"),
            ("Fine", "loan_id", "Loan"),
        }
        self.assertEqual(found, expected)

    def test_A04_unique_constraints_exist(self):
        """Natural keys (ISBN, campus number, e-mail ...) are UNIQUE."""
        found = {(r[0], r[1]) for r in self.rows(
            """SELECT TABLE_NAME, COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE
               WHERE TABLE_SCHEMA = %s AND CONSTRAINT_NAME LIKE 'uq\\_%%'""", (TEST_DB,))}
        for pair in [("Book", "isbn"), ("Member", "campus_number"), ("Member", "email"),
                     ("Librarian", "staff_number"), ("Librarian", "email"),
                     ("Publisher", "publisher_name"), ("Category", "category_name"),
                     ("Fine", "loan_id"), ("Book_Copy", "book_id"), ("Book_Copy", "copy_no")]:
            self.assertIn(pair, found)

    def test_A05_eight_check_constraints_exist(self):
        """The eight CHECK constraints of the design are present and enforced."""
        n = self.scalar(self.q("CHECK_CONSTRAINTS"), (TEST_DB,))
        self.assertEqual(n, 8)

    def test_A06_row_counts_match_the_sample_data(self):
        """Every table holds the number of rows described in Section 5.2."""
        expected = {"Category": 6, "Publisher": 7, "Author": 20, "Librarian": 3, "Member": 11,
                    "Book": 10, "Author_Book": 21, "Book_Copy": 21, "Loan": 15, "Fine": 5}
        for table, count in expected.items():
            self.assertEqual(self.scalar(f"SELECT COUNT(*) FROM `{table}`"), count, table)

    def test_A07_tables_use_innodb(self):
        """All tables use InnoDB, which enforces foreign keys and transactions."""
        engines = {r[0] for r in self.rows(
            "SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s", (TEST_DB,))}
        self.assertEqual(engines, {"InnoDB"})


# =====================================================================
# B. Constraints (each bad statement must be rejected by the database)
# =====================================================================
class TestB_Constraints(DBTestCase):
    rebuild_each_test = True

    def test_B01_negative_fine_rejected(self):
        """CHECK: a fine amount cannot be negative."""
        self.assertDbError(CHECK_FAILED, "INSERT INTO Fine (loan_id, fine_amount, reason, fine_date) "
                           "VALUES (1, -5, 'Overdue', '2026-10-10')")

    def test_B02_second_fine_for_one_loan_rejected(self):
        """UNIQUE: a loan can have at most one fine."""
        self.assertDbError(DUPLICATE, "INSERT INTO Fine (loan_id, fine_amount, reason, fine_date) "
                           "VALUES (2, 10, 'Overdue', '2026-10-10')")

    def test_B03_due_date_before_loan_date_rejected(self):
        """CHECK: the due date cannot be before the loan date."""
        self.assertDbError(CHECK_FAILED, "INSERT INTO Loan (member_id, copy_id, issued_by, loan_date, due_date) "
                           "VALUES (1, 1, 1, '2026-10-10', '2026-10-01')")

    def test_B04_unknown_category_rejected(self):
        """FOREIGN KEY: a book cannot reference a category that does not exist."""
        self.assertDbError(FK_CHILD, "INSERT INTO Book (category_id, publisher_id, isbn, title, publication_year) "
                           "VALUES (99, 1, '9780000000000', 'X', 2020)")

    def test_B05_duplicate_isbn_rejected(self):
        """UNIQUE: two books cannot share an ISBN."""
        self.assertDbError(DUPLICATE, "INSERT INTO Book (category_id, publisher_id, isbn, title, publication_year) "
                           "VALUES (1, 1, '9780133970777', 'X', 2020)")

    def test_B06_publication_year_out_of_range_rejected(self):
        """CHECK: publication year must be between 1000 and 2100."""
        self.assertDbError(CHECK_FAILED, "INSERT INTO Book (category_id, publisher_id, isbn, title, publication_year) "
                           "VALUES (1, 1, '9780000000001', 'X', 999)")

    def test_B07_invalid_member_email_rejected(self):
        """CHECK: a member's e-mail must look like name@domain."""
        self.assertDbError(CHECK_FAILED, "INSERT INTO Member (campus_number, email, first_name, last_name, "
                           "member_type, registration_date, phone_number) "
                           "VALUES ('S9', 'not-an-email', 'A', 'B', 'Student', '2026-10-01', '0820000000')")

    def test_B08_duplicate_campus_number_rejected(self):
        """UNIQUE: two members cannot share a campus number."""
        self.assertDbError(DUPLICATE, "INSERT INTO Member (campus_number, email, first_name, last_name, "
                           "member_type, registration_date, phone_number) "
                           "VALUES ('S3900101', 'new@myuwc.ac.za', 'A', 'B', 'Student', '2026-10-01', '0820000000')")

    def test_B09_invalid_member_type_rejected(self):
        """ENUM: member_type must be Student, Lecturer or Staff."""
        self.assertDbError(BAD_ENUM, "INSERT INTO Member (campus_number, email, first_name, last_name, "
                           "member_type, registration_date, phone_number) "
                           "VALUES ('S9', 'a@b.com', 'A', 'B', 'Visitor', '2026-10-01', '0820000000')")

    def test_B10_missing_required_value_rejected(self):
        """NOT NULL: a member must have a first name."""
        self.assertDbError(NOT_NULL, "INSERT INTO Member (campus_number, email, first_name, last_name, "
                           "member_type, registration_date, phone_number) "
                           "VALUES ('S9', 'a@b.com', NULL, 'B', 'Student', '2026-10-01', '0820000000')")

    def test_B11_copy_number_zero_rejected(self):
        """CHECK: copy numbers start at 1."""
        self.assertDbError(CHECK_FAILED, "INSERT INTO Book_Copy (book_id, copy_no) VALUES (1, 0)")

    def test_B12_duplicate_copy_number_for_a_book_rejected(self):
        """UNIQUE (book_id, copy_no): a book cannot have two copy number 1s."""
        self.assertDbError(DUPLICATE, "INSERT INTO Book_Copy (book_id, copy_no) VALUES (1, 1)")

    def test_B13_return_date_without_receiver_rejected(self):
        """CHECK: a returned loan must record the librarian who received it."""
        self.assertDbError(CHECK_FAILED, "UPDATE Loan SET return_date = '2026-10-10' WHERE loan_id = 11")

    def test_B14_return_date_before_loan_date_rejected(self):
        """CHECK: a loan cannot be returned before it was issued."""
        self.assertDbError(CHECK_FAILED, "UPDATE Loan SET return_date = '2026-09-01', received_by = 1 "
                           "WHERE loan_id = 11")

    def test_B15_category_with_books_cannot_be_deleted(self):
        """RESTRICT: deleting a category that still has books is refused."""
        self.assertDbError(FK_PARENT, "DELETE FROM Category WHERE category_id = 1")

    def test_B16_member_with_loans_cannot_be_deleted(self):
        """FOREIGN KEY: loan history keeps a member from being deleted."""
        self.assertDbError(FK_PARENT, "DELETE FROM Member WHERE member_id = 1")

    def test_B17_author_cannot_be_linked_to_a_book_twice(self):
        """Composite PRIMARY KEY of Author_Book blocks duplicate links."""
        self.assertDbError(DUPLICATE, "INSERT INTO Author_Book (book_id, author_id) VALUES (1, 1)")

    def test_B18_on_delete_cascade_removes_author_links(self):
        """ON DELETE CASCADE: deleting a book also deletes its Author_Book rows."""
        self.execute("INSERT INTO Book (book_id, category_id, publisher_id, isbn, title, publication_year) "
                     "VALUES (50, 1, 1, '9780000000050', 'Temp', 2020)")
        self.execute("INSERT INTO Author_Book (book_id, author_id) VALUES (50, 1), (50, 2)")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Author_Book WHERE book_id = 50"), 2)
        self.execute("DELETE FROM Book WHERE book_id = 50")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Author_Book WHERE book_id = 50"), 0)

    def test_B19_on_update_cascade_follows_publisher_id(self):
        """ON UPDATE CASCADE: changing a publisher id updates its books."""
        self.execute("UPDATE Publisher SET publisher_id = 70 WHERE publisher_id = 7")
        self.assertEqual(self.scalar("SELECT publisher_id FROM Book WHERE book_id = 9"), 70)

    def test_B20_default_values_are_applied(self):
        """DEFAULTs: new copy = Good/Available, new fine = Unpaid, new member = Active."""
        self.execute("INSERT INTO Book_Copy (book_id, copy_no) VALUES (1, 4)")
        self.execute("INSERT INTO Fine (loan_id, fine_amount, reason, fine_date) "
                     "VALUES (1, 10, 'Overdue', '2026-10-10')")
        self.execute("INSERT INTO Member (campus_number, email, first_name, last_name, member_type, "
                     "registration_date, phone_number) "
                     "VALUES ('S9', 'a@b.com', 'A', 'B', 'Student', '2026-10-01', '0820000000')")
        self.assertEqual(self.rows("SELECT condition_status, availability_status FROM Book_Copy "
                                   "WHERE book_id = 1 AND copy_no = 4"), [("Good", "Available")])
        self.assertEqual(self.scalar("SELECT payment_status FROM Fine WHERE loan_id = 1"), "Unpaid")
        self.assertEqual(self.scalar("SELECT status FROM Member WHERE campus_number = 'S9'"), "Active")

    def test_B21_valid_rows_are_accepted(self):
        """Positive control: correct data is accepted (the checks are not over-strict)."""
        self.execute("INSERT INTO Fine (loan_id, fine_amount, reason, fine_date) "
                     "VALUES (1, 0.00, 'Overdue', '2026-10-10')")
        self.execute("INSERT INTO Loan (member_id, copy_id, issued_by, loan_date, due_date) "
                     "VALUES (11, 2, 1, '2026-10-11', '2026-10-11')")
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Loan"), 16)


# =====================================================================
# C. Queries
# =====================================================================
class TestC_Queries(DBTestCase):

    def run_q(self, number):
        result = app.run_query(self.conn, queries.get_query(number))
        return list(result.columns), [tuple(app.format_value(v) for v in r) for r in result.rows]

    def check_golden(self, number):
        columns, rows = self.run_q(number)
        self.assertEqual((columns, rows), (GOLDEN[number][0], GOLDEN[number][1]))

    def test_C01_q1_outstanding_fines(self):
        """Q1 (simple) returns the three unpaid fines, largest first."""
        self.check_golden(1)

    def test_C02_q2_collection_per_category(self):
        """Q2 (medium) returns copies and availability for the six categories."""
        self.check_golden(2)

    def test_C03_q3_member_activity_and_fines(self):
        """Q3 (medium) returns all 11 members, including the one with no loans."""
        self.check_golden(3)

    def test_C04_q4_titles_in_above_average_demand(self):
        """Q4 (complex) returns the four titles borrowed more than the 1.5 average."""
        self.check_golden(4)

    def test_C05_q5_fine_income_by_category(self):
        """Q5 (complex) returns the three categories passing the HAVING filter."""
        self.check_golden(5)

    def test_C06_q6_catalogue_search(self):
        """Q6 (simple) finds the three 'Database' titles, newest first."""
        self.check_golden(6)

    def test_C07_q7_overdue_loans(self):
        """Q7 (medium) lists the two members with overdue loans on 2026-10-11 and their R5/day fines."""
        self.check_golden(7)

    def test_C08_q8_monthly_activity(self):
        """Q8 (medium) summarises loans per month and member type, with each share of all loans."""
        self.check_golden(8)

    def test_C09_q9_members_flagged(self):
        """Q9 (complex) flags the repeat late returner and the high-fine member."""
        self.check_golden(9)

    def test_C10_q10_worn_copies_in_demand(self):
        """Q10 (complex) lists the three worn copies loaned at least the average."""
        self.check_golden(10)

    def test_C11_script_queries_match_the_sql_file(self):
        """The SQL in queries.py is identical to the queries in library_db.sql."""
        text = (HERE / "library_db.sql").read_text(encoding="utf8")
        section = text[text.index("-- 6.x  SQL QUERIES"):]
        selects = [s for s in app.split_sql_statements(section) if s.upper().startswith("SELECT")]
        norm = lambda s: re.sub(r"\s+", " ", s).strip().rstrip(";").strip()
        self.assertEqual(len(selects), 10)
        for statement, query in zip(selects, queries.QUERIES):
            self.assertEqual(norm(statement), norm(query.sql), f"Q{query.number} differs")

    def test_C12_query_mix_meets_the_assignment(self):
        """Ten queries: 2 simple, 4 medium, 4 complex; each uses the required features."""
        levels = [q.level for q in queries.QUERIES]
        self.assertEqual((levels.count("SIMPLE"), levels.count("MEDIUM"), levels.count("COMPLEX")), (2, 4, 4))
        for query in queries.QUERIES:
            sql = query.sql.upper()
            if query.level != "SIMPLE":
                self.assertIn("JOIN", sql, f"Q{query.number}")
            if query.level == "COMPLEX":
                self.assertTrue("HAVING" in sql or sql.count("(SELECT") >= 1, f"Q{query.number}")

    def test_C13_cross_checks_against_independent_counts(self):
        """Totals in the query results agree with simple counts on the base tables."""
        _, q2 = self.run_q(2)
        self.assertEqual(sum(int(r[2]) for r in q2), self.scalar("SELECT COUNT(*) FROM Book_Copy"))
        self.assertEqual(sum(int(r[3]) for r in q2),
                         self.scalar("SELECT COUNT(*) FROM Book_Copy WHERE availability_status='Available'"))
        _, q3 = self.run_q(3)
        self.assertEqual(sum(int(r[2]) for r in q3), self.scalar("SELECT COUNT(*) FROM Loan"))
        self.assertEqual(sum(Decimal(r[3]) for r in q3), self.scalar("SELECT SUM(fine_amount) FROM Fine"))
        _, q8 = self.run_q(8)
        self.assertEqual(sum(int(r[2]) for r in q8), self.scalar("SELECT COUNT(*) FROM Loan"))
        self.assertEqual(sum(int(r[3]) for r in q8),
                         self.scalar("SELECT COUNT(*) FROM Loan WHERE return_date IS NOT NULL"))
        _, q5 = self.run_q(5)
        self.assertEqual(sum(Decimal(r[2]) for r in q5), Decimal("295.00"))   # 315 minus Biography's 20

    def test_C14_q7_uses_the_reference_date(self):
        """Q7 changes with @as_of: 4 members overdue on 2026-10-20, none on 2026-09-01."""
        app.set_clock(self.conn, date(2026, 10, 20))
        _, rows = self.run_q(7)
        self.assertEqual([r[0] for r in rows],
                         ["Lwazi Dlamini", "Nomsa Zulu", "Pieter Botha", "Ruan van der Merwe"])
        self.assertEqual([r[4] for r in rows], ["16", "11", "8", "1"])      # max_days_overdue
        self.assertEqual([r[5] for r in rows], ["80.00", "55.00", "40.00", "5.00"])
        app.set_clock(self.conn, date(2026, 9, 1))
        self.assertEqual(self.run_q(7)[1], [])          # an empty result is handled normally

    def test_C15_q7_falls_back_to_curdate_when_as_of_is_unset(self):
        """If @as_of is NULL, Q7 uses CURDATE() instead of returning nothing or failing."""
        self.execute("SET @as_of = NULL")
        _, rows = self.run_q(7)
        expected = self.scalar("SELECT COUNT(DISTINCT member_id) FROM Loan WHERE return_date IS NULL AND due_date < CURDATE()")
        self.assertEqual(len(rows), expected)


    def test_C16_q7_leaves_out_lost_copies(self):
        """Q7 ignores a copy already recorded as Lost (handled with a lost-book fine instead)."""
        self.execute("UPDATE Book_Copy SET availability_status = 'Lost' WHERE copy_id = 20")
        self.addCleanup(self.execute, "UPDATE Book_Copy SET availability_status = 'On Loan' WHERE copy_id = 20")
        _, rows = self.run_q(7)
        self.assertEqual([r[0] for r in rows], ["Nomsa Zulu"])

# =====================================================================
# D. Application behaviour (search, borrow, return, fines)
# =====================================================================
INVARIANTS = {
    "On Loan copy has no open loan":
        "SELECT COUNT(*) FROM Book_Copy bc WHERE bc.availability_status = 'On Loan' AND NOT EXISTS "
        "(SELECT 1 FROM Loan l WHERE l.copy_id = bc.copy_id AND l.return_date IS NULL)",
    "Open loan but copy not marked On Loan":
        "SELECT COUNT(*) FROM Loan l INNER JOIN Book_Copy bc ON bc.copy_id = l.copy_id "
        "WHERE l.return_date IS NULL AND bc.availability_status <> 'On Loan'",
    "Copy with more than one open loan":
        "SELECT COUNT(*) FROM (SELECT copy_id FROM Loan WHERE return_date IS NULL "
        "GROUP BY copy_id HAVING COUNT(*) > 1) AS t",
    "Late return without a fine":
        "SELECT COUNT(*) FROM Loan l LEFT JOIN Fine f ON f.loan_id = l.loan_id "
        "WHERE l.return_date > l.due_date AND f.fine_id IS NULL",
    "Overdue fine is not R5.00 x days late":
        "SELECT COUNT(*) FROM Fine f INNER JOIN Loan l ON l.loan_id = f.loan_id WHERE f.reason = 'Overdue' "
        "AND (l.return_date IS NULL OR f.fine_amount <> DATEDIFF(l.return_date, l.due_date) * 5)",
    "Damage fine is not R150.00":
        "SELECT COUNT(*) FROM Fine WHERE reason = 'Damaged' AND fine_amount <> 150",
    "Fine on a loan that is still open":
        "SELECT COUNT(*) FROM Fine f INNER JOIN Loan l ON l.loan_id = f.loan_id WHERE l.return_date IS NULL",
    "Returned loan without receiving librarian":
        "SELECT COUNT(*) FROM Loan WHERE return_date IS NOT NULL AND received_by IS NULL",
}


class TestD_Application(DBTestCase):
    rebuild_each_test = True

    def assert_consistent(self):
        for name, sql in INVARIANTS.items():
            self.assertEqual(self.scalar(sql), 0, f"invariant broken: {name}")

    def loan_count(self):
        return self.scalar("SELECT COUNT(*) FROM Loan")

    def copy_state(self, copy_id):
        return self.rows("SELECT availability_status, condition_status FROM Book_Copy WHERE copy_id = %s",
                         (copy_id,))[0]

    # -- search -------------------------------------------------------
    def test_D01_search_by_title_keyword(self):
        """Searching 'algor' finds Introduction to Algorithms with 1 free copy."""
        rows = app.search_catalogue(self.conn, "algor").rows
        self.assertEqual([(r[2], r[5]) for r in rows], [("Introduction to Algorithms", 1)])

    def test_D02_search_by_author_name(self):
        """Searching an author's name ('Mandela') finds that author's book."""
        rows = app.search_catalogue(self.conn, "Mandela").rows
        self.assertEqual([r[2] for r in rows], ["Long Walk to Freedom"])

    def test_D03_search_is_case_insensitive(self):
        """'DATABASE' and 'database' return the same three books."""
        upper = app.search_catalogue(self.conn, "DATABASE").rows
        lower = app.search_catalogue(self.conn, "database").rows
        self.assertEqual(upper, lower)
        self.assertEqual(len(upper), 3)

    def test_D04_search_without_match_returns_no_rows(self):
        """A keyword that matches nothing gives an empty result, not an error."""
        self.assertEqual(app.search_catalogue(self.conn, "zzzz").rows, [])

    def test_D05_empty_search_is_rejected(self):
        """An empty search word gives a clear message."""
        with self.assertRaises(app.LibraryError):
            app.search_catalogue(self.conn, "   ")

    def test_D06_sql_injection_attempt_is_harmless(self):
        """A malicious keyword is treated as plain text: no rows, all tables intact."""
        before = self.loan_count()
        result = app.search_catalogue(self.conn, "x'; DROP TABLE Loan; --")
        self.assertEqual(result.rows, [])
        self.assertEqual(self.loan_count(), before)
        result = app.search_catalogue(self.conn, "' OR '1'='1")
        self.assertEqual(result.rows, [])

    def test_D07_like_wildcards_typed_by_user_are_literal(self):
        """Typing % or _ does not match every title."""
        self.assertEqual(app.search_catalogue(self.conn, "%").rows, [])
        self.assertEqual(app.search_catalogue(self.conn, "_").rows, [])

    def test_D08_member_loans_show_status(self):
        """Thabo's 3 loans show two Returned and one On loan; Lwazi's open loan is Overdue."""
        thabo = app.member_loans(self.conn, "S3900101").rows
        self.assertEqual(sorted(r[6] for r in thabo), ["On loan", "Returned", "Returned"])
        lwazi = app.member_loans(self.conn, "S3900103").rows
        self.assertIn("Overdue", [r[6] for r in lwazi])

    def test_D09_unknown_member_is_reported(self):
        """Asking for loans of a campus number that does not exist gives a clear message."""
        with self.assertRaises(app.LibraryError):
            app.member_loans(self.conn, "S0000000")

    # -- borrowing ----------------------------------------------------
    def test_D10_borrow_available_copy(self):
        """Borrowing creates a 14-day loan and marks the copy On Loan."""
        receipt = app.borrow_copy(self.conn, "S3900101", 1, "LIB001", TODAY)
        self.assertEqual(receipt.due_date, TODAY + timedelta(days=14))
        row = self.rows("SELECT member_id, copy_id, issued_by, loan_date, due_date, return_date "
                        "FROM Loan WHERE loan_id = %s", (receipt.loan_id,))[0]
        self.assertEqual(row, (1, 1, 1, TODAY, TODAY + timedelta(days=14), None))
        self.assertEqual(self.copy_state(1)[0], "On Loan")
        self.assert_consistent()

    def test_D11_borrow_copy_already_on_loan_is_refused(self):
        """A copy that is On Loan cannot be lent again; nothing changes."""
        before = self.loan_count()
        with self.assertRaises(app.LibraryError):
            app.borrow_copy(self.conn, "S3900101", 3, "LIB001", TODAY)
        self.assertEqual(self.loan_count(), before)

    def test_D12_suspended_member_cannot_borrow(self):
        """A Suspended member (Sipho) is refused."""
        before = self.loan_count()
        with self.assertRaises(app.LibraryError):
            app.borrow_copy(self.conn, "S3900108", 1, "LIB001", TODAY)
        self.assertEqual(self.loan_count(), before)
        self.assertEqual(self.copy_state(1)[0], "Available")

    def test_D13_unknown_member_copy_or_librarian_is_refused(self):
        """Unknown member, copy or librarian each give a clear message and no change."""
        before = self.loan_count()
        for args in [("S0000000", 1, "LIB001"), ("S3900101", 999, "LIB001"), ("S3900101", 1, "LIB999")]:
            with self.assertRaises(app.LibraryError, msg=str(args)):
                app.borrow_copy(self.conn, args[0], args[1], args[2], TODAY)
        self.assertEqual(self.loan_count(), before)

    def test_D14_under_repair_copy_cannot_be_borrowed(self):
        """Copy 18 (Damaged, Under Repair) cannot be lent."""
        with self.assertRaises(app.LibraryError):
            app.borrow_copy(self.conn, "S3900101", 18, "LIB001", TODAY)

    def test_D15_inconsistent_record_is_caught(self):
        """A copy wrongly marked Available while it has an open loan is refused."""
        self.execute("UPDATE Book_Copy SET availability_status = 'Available' WHERE copy_id = 3")
        with self.assertRaises(app.LibraryError):
            app.borrow_copy(self.conn, "S3900101", 3, "LIB001", TODAY)

    def test_D16_failed_borrow_is_rolled_back(self):
        """If the copy update fails after the loan was inserted, the loan is rolled back."""
        try:
            self.execute("CREATE TRIGGER trg_fail BEFORE UPDATE ON Book_Copy FOR EACH ROW "
                         "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'simulated failure'")
        except MySQLError as err:
            self.skipTest(f"this MySQL user cannot create triggers ({err.msg})")
        before = self.loan_count()
        with self.assertRaises(MySQLError):
            app.borrow_copy(self.conn, "S3900101", 1, "LIB001", TODAY)
        self.assertEqual(self.loan_count(), before)          # no half-finished loan
        self.assertEqual(self.copy_state(1)[0], "Available")

    def test_D17_second_borrower_waits_then_is_refused(self):
        """Two librarians lend copy 1 at once: the second waits for the lock, then is refused."""
        first = app.connect(self.cfg, as_of=TODAY)
        self.addCleanup(first.close)
        first.start_transaction()
        cur = first.cursor()
        cur.execute("SELECT copy_id FROM Book_Copy WHERE copy_id = 1 FOR UPDATE")   # librarian 1 holds the copy
        cur.fetchall()
        outcome = {}

        def second_librarian():
            conn2 = app.connect(self.cfg, as_of=TODAY)
            try:
                app.borrow_copy(conn2, "S3900102", 1, "LIB002", TODAY)
                outcome["result"] = "borrowed"
            except app.LibraryError:
                outcome["result"] = "refused"
            except Exception as err:                       # pragma: no cover - reported by the assert
                outcome["result"] = repr(err)
            finally:
                conn2.close()

        worker = threading.Thread(target=second_librarian)
        worker.start()
        time.sleep(1.0)
        self.assertTrue(worker.is_alive(), "the second librarian should be waiting for the lock")
        # librarian 1 now finishes lending the copy
        cur.execute(q.INSERT_LOAN_SQL, (1, 1, 1, TODAY, TODAY + timedelta(days=14)))
        cur.execute(q.MARK_COPY_ON_LOAN_SQL, (1,))
        first.commit()
        worker.join(20)
        self.assertEqual(outcome.get("result"), "refused")
        self.assert_consistent()                           # still only one open loan for copy 1

    # -- returning ----------------------------------------------------
    def test_D18_return_on_time_has_no_fine(self):
        """Returning before the due date closes the loan, frees the copy, creates no fine."""
        receipt = app.return_copy(self.conn, 5, "LIB001", TODAY)         # loan 15 due 2026-10-21
        self.assertIsNone(receipt.fine_amount)
        self.assertEqual(self.copy_state(5), ("Available", "Good"))
        self.assertEqual(self.rows("SELECT return_date, received_by FROM Loan WHERE loan_id = 15"),
                         [(TODAY, 1)])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM Fine"), 5)
        self.assert_consistent()

    def test_D19_late_return_creates_overdue_fine(self):
        """Loan 12 (due 10-04) returned 10-11 is 7 days late: R35.00 Overdue, Unpaid."""
        receipt = app.return_copy(self.conn, 20, "LIB002", TODAY)
        self.assertEqual((receipt.days_late, receipt.fine_amount, receipt.fine_reason),
                         (7, Decimal("35.00"), "Overdue"))
        self.assertEqual(self.rows("SELECT fine_amount, reason, payment_status, fine_date "
                                   "FROM Fine WHERE loan_id = 12"),
                         [(Decimal("35.00"), "Overdue", "Unpaid", TODAY)])
        self.assertEqual(self.copy_state(20)[0], "Available")
        self.assert_consistent()

    def test_D20_damaged_return_creates_flat_fine_and_repair_status(self):
        """A copy returned Damaged gets the R150.00 fine and goes Under Repair."""
        receipt = app.return_copy(self.conn, 5, "LIB001", TODAY, condition="Damaged")
        self.assertEqual((receipt.fine_amount, receipt.fine_reason), (Decimal("150.00"), "Damaged"))
        self.assertEqual(self.copy_state(5), ("Under Repair", "Damaged"))
        self.assert_consistent()

    def test_D21_damaged_and_late_gets_one_fine_only(self):
        """A copy that is both late and damaged still gets a single (damage) fine."""
        app.return_copy(self.conn, 20, "LIB002", TODAY, condition="Damaged")
        self.assertEqual(self.rows("SELECT reason, fine_amount FROM Fine WHERE loan_id = 12"),
                         [("Damaged", Decimal("150.00"))])

    def test_D22_return_of_copy_not_on_loan_is_refused(self):
        """Returning a copy that is Available is refused."""
        with self.assertRaises(app.LibraryError):
            app.return_copy(self.conn, 1, "LIB001", TODAY)

    def test_D23_return_with_unknown_librarian_changes_nothing(self):
        """An unknown librarian is refused and the loan stays open."""
        with self.assertRaises(app.LibraryError):
            app.return_copy(self.conn, 20, "LIB999", TODAY)
        self.assertIsNone(self.scalar("SELECT return_date FROM Loan WHERE loan_id = 12"))

    def test_D24_return_before_loan_date_is_refused(self):
        """A return date earlier than the loan date is refused with a clear message."""
        with self.assertRaises(app.LibraryError):
            app.return_copy(self.conn, 5, "LIB001", date(2026, 10, 1))   # loan 15 issued 10-07

    def test_D25_invalid_condition_is_refused(self):
        """Only New, Good, Fair or Damaged are accepted as the return condition."""
        with self.assertRaises(app.LibraryError):
            app.return_copy(self.conn, 5, "LIB001", TODAY, condition="Broken")

    def test_D26_borrow_then_return_round_trip(self):
        """Borrow + return leaves the copy Available and adds exactly one closed loan."""
        before = self.loan_count()
        app.borrow_copy(self.conn, "S3900107", 2, "LIB003", TODAY)
        later = TODAY + timedelta(days=10)
        receipt = app.return_copy(self.conn, 2, "LIB003", later)
        self.assertIsNone(receipt.fine_amount)
        self.assertEqual(self.loan_count(), before + 1)
        self.assertEqual(self.copy_state(2)[0], "Available")
        self.assert_consistent()

    def test_D27_late_round_trip_fine_matches_rate(self):
        """Borrowed 10-11, returned 11-01 (due 10-25): 7 days late = R35.00."""
        app.borrow_copy(self.conn, "S3900107", 2, "LIB003", TODAY)
        receipt = app.return_copy(self.conn, 2, "LIB003", date(2026, 11, 1))
        self.assertEqual((receipt.days_late, receipt.fine_amount), (7, Decimal("35.00")))
        self.assert_consistent()

    def test_D28_lock_wait_timeout_is_a_database_error(self):
        """If the lock is not released in time, the borrow fails with error 1205 and changes nothing."""
        other = app.connect(self.cfg, as_of=TODAY)
        self.addCleanup(other.close)
        other.start_transaction()
        cur = other.cursor()
        cur.execute("SELECT copy_id FROM Book_Copy WHERE copy_id = 1 FOR UPDATE")
        cur.fetchall()
        self.execute("SET SESSION innodb_lock_wait_timeout = 1")
        with self.assertRaises(MySQLError) as ctx:
            app.borrow_copy(self.conn, "S3900101", 1, "LIB001", TODAY)
        self.assertEqual(ctx.exception.errno, 1205)          # lock wait timeout
        self.assertEqual(self.loan_count(), 15)               # nothing was added
        other.rollback()
        cur.close()
        app.borrow_copy(self.conn, "S3900101", 1, "LIB001", TODAY)    # after the lock is freed it works
        self.assert_consistent()


# =====================================================================
# E. Data consistency of the supplied sample data
# =====================================================================
class TestE_Consistency(DBTestCase):

    def test_E01_all_business_rule_invariants_hold(self):
        """Eight data-quality rules have zero violations in the sample data."""
        for name, sql in INVARIANTS.items():
            with self.subTest(rule=name):
                self.assertEqual(self.scalar(sql), 0)

    def test_E02_loan_period_is_fourteen_days(self):
        """Every sample loan has a due date exactly 14 days after the loan date."""
        n = self.scalar("SELECT COUNT(*) FROM Loan WHERE DATEDIFF(due_date, loan_date) <> 14")
        self.assertEqual(n, 0)

    def test_E03_every_book_has_a_category_publisher_author_and_copy(self):
        """No book is missing a required relationship."""
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM Book b WHERE NOT EXISTS (SELECT 1 FROM Author_Book ab WHERE ab.book_id = b.book_id) "
            "OR NOT EXISTS (SELECT 1 FROM Book_Copy bc WHERE bc.book_id = b.book_id)"), 0)


# =====================================================================
# F. Application plumbing
# =====================================================================
class TestF_Plumbing(DBTestCase):

    def test_F01_sql_splitter_handles_comments_and_quotes(self):
        """';' inside a string and comment text do not split statements."""
        script = "-- comment; with semicolon\nINSERT INTO t VALUES ('a;b', \"c;d\"); /* x; y */ SELECT 1;\n# note\nSELECT 'it''s';"
        self.assertEqual(app.split_sql_statements(script),
                         ["INSERT INTO t VALUES ('a;b', \"c;d\")", "SELECT 1", "SELECT 'it''s'"])

    def test_F02_the_real_sql_file_splits_into_expected_statements(self):
        """library_db.sql yields 11 DDL + 1 DB statements, inserts and the 10 queries."""
        text = (HERE / "library_db.sql").read_text(encoding="utf8")
        statements = app.split_sql_statements(text)
        words = [s.split(None, 1)[0].upper() for s in statements]
        self.assertEqual(words.count("CREATE"), 11)       # database + 10 tables
        self.assertEqual(words.count("SELECT"), 10)

    def test_F03_table_formatter(self):
        """NULL, decimals and dates print as expected; numbers are right-aligned."""
        table = app.format_table(["n", "name", "d"], [(1, "ab", date(2026, 1, 2)), (None, "c", None)])
        self.assertIn("NULL", table)
        self.assertIn("|    1 | ab   | 2026-01-02 |", table)        # number right-aligned
        self.assertEqual(app.format_value(Decimal("5.00")), "5.00")

    def test_F04_like_pattern_escapes_wildcards(self):
        """% and _ typed by a user are escaped before they reach LIKE."""
        self.assertEqual(app.like_pattern("a%b_c"), "%a\\%b\\_c%")

    def test_F05_as_of_parsing(self):
        """--as-of accepts ISO dates and 'today' and rejects anything else."""
        self.assertEqual(app.parse_as_of("2026-10-11"), date(2026, 10, 11))
        self.assertEqual(app.parse_as_of("today"), date.today())
        with self.assertRaises(argparse.ArgumentTypeError):
            app.parse_as_of("11/10/2026")

    def test_F06_config_precedence(self):
        """Command-line options beat environment variables, which beat defaults."""
        env = {"DB_HOST": "envhost", "DB_USER": "envuser", "DB_PASSWORD": "pw", "DB_PORT": "3310"}
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = app.load_config(argparse.Namespace(host="clihost", user=None, port=None, database=None),
                                  prompt=False)
        self.assertEqual((cfg.host, cfg.user, cfg.port, cfg.password, cfg.database),
                         ("clihost", "envuser", 3310, "pw", "university_library"))
        with mock.patch.dict(os.environ, {"DB_PORT": "abc"}, clear=True):
            with self.assertRaises(app.AppError):
                app.load_config(prompt=False)

    def test_F07_wrong_credentials_give_friendly_message(self):
        """A wrong user/password raises DatabaseConnectionError that names the fix."""
        bad = dataclasses.replace(self.cfg, user="no_such_user_xyz", password="wrong")
        with self.assertRaises(app.DatabaseConnectionError) as ctx:
            app.connect(bad)
        self.assertIn("DB_PASSWORD", str(ctx.exception))

    def test_F08_unreachable_server_gives_friendly_message(self):
        """A closed port raises DatabaseConnectionError mentioning host and port."""
        bad = dataclasses.replace(self.cfg, port=1)
        with self.assertRaises(app.DatabaseConnectionError) as ctx:
            app.connect(bad)
        self.assertIn("127.0.0.1:1", str(ctx.exception).replace("localhost", "127.0.0.1"))

    def test_F09_missing_database_suggests_setup(self):
        """Connecting to a database that does not exist suggests --setup."""
        bad = dataclasses.replace(self.cfg, database="no_such_database_xyz")
        with self.assertRaises(app.DatabaseConnectionError) as ctx:
            app.connect(bad)
        self.assertIn("--setup", str(ctx.exception))

    def test_F10_error_message_table(self):
        """describe_connection_error covers the common MySQL error numbers."""
        for errno, word in [(1045, "Access denied"), (1049, "does not exist"), (2003, "Cannot connect"),
                            (2005, "Unknown MySQL host"), (9999, "9999")]:
            err = ConnectorError(msg="boom", errno=errno)
            self.assertIn(word, app.describe_connection_error(err, self.cfg))

    def test_F11_setup_rejects_unsafe_database_names(self):
        """A database name with quotes or spaces is refused before any SQL is built."""
        with self.assertRaises(app.AppError):
            app.setup_database(dataclasses.replace(self.cfg, database="x`; DROP DATABASE mysql; --"))

    def _cli(self, *args):
        env = dict(os.environ, DB_NAME=TEST_DB)
        env.setdefault("DB_PASSWORD", "")
        return subprocess.run([sys.executable, str(HERE / "app.py"), *args], capture_output=True,
                              text=True, env=env, stdin=subprocess.DEVNULL, timeout=60)

    def test_F12_command_line_runs_all_ten_queries(self):
        """`python app.py` executes Q1-Q10 and reports 10/10 with exit code 0."""
        result = self._cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SUMMARY: 10/10 queries executed successfully", result.stdout)

    def test_F13_command_line_single_query_and_bad_number(self):
        """`--query 7` runs one query; `--query 11` is rejected with exit code 2."""
        ok = self._cli("--query", "7")
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("Lwazi Dlamini", ok.stdout)
        bad = self._cli("--query", "11")
        self.assertEqual(bad.returncode, 2)

    def test_F14_menu_session_reads_input_and_exits(self):
        """The interactive menu handles a short scripted session without crashing."""
        env = dict(os.environ, DB_NAME=TEST_DB)
        env.setdefault("DB_PASSWORD", "")
        script = "3\nalgor\n2\n99\n5\nS3900108\n1\nLIB001\n0\n"
        result = subprocess.run([sys.executable, str(HERE / "app.py"), "--menu"], input=script,
                                capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Introduction to Algorithms", result.stdout)
        self.assertIn("Query number must be between 1 and 10", result.stdout)
        self.assertIn("is Suspended", result.stdout)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
