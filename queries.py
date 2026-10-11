"""
=====================================================================
Team Name       : Code 404
Student numbers : <STUDENT_NO_1>, <STUDENT_NO_2>, <STUDENT_NO_3>,
                  <STUDENT_NO_4>, <STUDENT_NO_5>
File name       : queries.py
Course          : CSC312 - Practical Assignment 2 (University of the Western Cape)
Project         : University Library Lending System (MySQL + Python)
=====================================================================

All SQL used by the application lives in this module.

* QUERIES holds the ten report queries (Section 6.0 of the report).
  Their text is identical to the queries at the bottom of library_db.sql
  (test_library.py checks this automatically).
* The *_SQL constants below are the parameterised statements used by the
  interactive menu in app.py.  Values are always passed as parameters
  (%s placeholders) and never concatenated into the SQL text, which
  prevents SQL injection.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Query:
    """One report query: its number, difficulty level, description and SQL."""

    number: int
    level: str      # SIMPLE, MEDIUM or COMPLEX
    title: str
    purpose: str    # the business reason for running the query
    sql: str


# ---------------------------------------------------------------------
# Section 6.0 queries.  Q1-Q5 were written by Member 4, Q6-Q10 by Member 5.
# ---------------------------------------------------------------------
QUERIES: tuple[Query, ...] = (
    Query(
        number=1,
        level="SIMPLE",
        title="Outstanding fines, largest first",
        purpose=(
            "lets librarians see which fines still need to be collected."
        ),
        sql="""\
SELECT fine_id, loan_id, fine_amount, reason, fine_date
FROM Fine
WHERE payment_status = 'Unpaid'
ORDER BY fine_amount DESC;""",
    ),
    Query(
        number=2,
        level="MEDIUM",
        title="Collection size and availability per category",
        purpose=(
            "shows which subject areas have few free copies so the library can "
            "decide where to buy more copies. (INNER JOIN, COUNT, SUM, GROUP BY)"
        ),
        sql="""\
SELECT c.category_name,
       COUNT(DISTINCT b.book_id)                          AS titles,
       COUNT(bc.copy_id)                                  AS total_copies,
       SUM(bc.availability_status = 'Available')          AS available_copies
FROM Category c
INNER JOIN Book b       ON b.category_id = c.category_id
INNER JOIN Book_Copy bc ON bc.book_id    = b.book_id
GROUP BY c.category_id, c.category_name
ORDER BY total_copies DESC, c.category_name;""",
    ),
    Query(
        number=3,
        level="MEDIUM",
        title="Borrowing activity and fines per member",
        purpose=(
            "identifies heavy borrowers and members who owe money, including "
            "members who have never borrowed (LEFT JOIN). (LEFT JOIN, CONCAT, "
            "COUNT, SUM, GROUP BY)"
        ),
        sql="""\
SELECT CONCAT(m.first_name, ' ', m.last_name)  AS member_name,
       m.member_type,
       COUNT(l.loan_id)                        AS total_loans,
       COALESCE(SUM(f.fine_amount), 0)         AS total_fines
FROM Member m
LEFT JOIN Loan l ON l.member_id = m.member_id
LEFT JOIN Fine f ON f.loan_id   = l.loan_id
GROUP BY m.member_id, m.first_name, m.last_name, m.member_type
ORDER BY total_fines DESC, total_loans DESC, member_name;""",
    ),
    Query(
        number=4,
        level="COMPLEX",
        title="Most popular titles (borrowed more than the average title) with authors",
        purpose=(
            "supports purchasing decisions by showing which titles are in above- "
            "average demand. (6 tables, nested subquery, GROUP_CONCAT, HAVING)"
        ),
        sql="""\
SELECT b.title,
       GROUP_CONCAT(DISTINCT CONCAT(a.first_name, ' ', a.last_name)
                    ORDER BY a.last_name SEPARATOR ', ')  AS authors,
       COUNT(DISTINCT l.loan_id)                          AS times_borrowed
FROM Book b
INNER JOIN Book_Copy bc   ON bc.book_id = b.book_id
INNER JOIN Loan l         ON l.copy_id  = bc.copy_id
INNER JOIN Author_Book ab ON ab.book_id = b.book_id
INNER JOIN Author a       ON a.author_id = ab.author_id
GROUP BY b.book_id, b.title
HAVING COUNT(DISTINCT l.loan_id) >
       (SELECT AVG(loans_per_book)
        FROM (SELECT COUNT(*) AS loans_per_book
              FROM Loan l2
              INNER JOIN Book_Copy bc2 ON bc2.copy_id = l2.copy_id
              GROUP BY bc2.book_id) AS book_counts)
ORDER BY times_borrowed DESC, b.title;""",
    ),
    Query(
        number=5,
        level="COMPLEX",
        title="Fine income by category (HAVING with AND/OR, conditional SUM)",
        purpose=(
            "shows which subject areas generate most fines and how much is still "
            "unpaid, helping target reminders and loan-period policy."
        ),
        sql="""\
SELECT c.category_name,
       COUNT(f.fine_id)                                                       AS fines_issued,
       SUM(f.fine_amount)                                                     AS total_fines,
       SUM(CASE WHEN f.payment_status = 'Unpaid' THEN f.fine_amount ELSE 0 END) AS outstanding
FROM Fine f
INNER JOIN Loan l       ON l.loan_id   = f.loan_id
INNER JOIN Book_Copy bc ON bc.copy_id  = l.copy_id
INNER JOIN Book b       ON b.book_id   = bc.book_id
INNER JOIN Category c   ON c.category_id = b.category_id
GROUP BY c.category_id, c.category_name
HAVING SUM(f.fine_amount) >= 50 OR COUNT(f.fine_id) >= 2
ORDER BY total_fines DESC;""",
    ),
    Query(
        number=6,
        level="SIMPLE",
        title="Catalogue search by title keyword",
        purpose=(
            "supports the 'members can search for books' workflow; shows the newest "
            "matching titles first. (WHERE with LIKE, ORDER BY)"
        ),
        sql="""\
SELECT book_id, isbn, title, publication_year
FROM Book
WHERE title LIKE '%Database%'
ORDER BY publication_year DESC, title;""",
    ),
    Query(
        number=7,
        level="MEDIUM",
        title="Members with overdue loans, with estimated fines",
        purpose=(
            "gives librarians a contact list of members who still hold copies past "
            "their due date: how many copies, which titles, the longest delay and "
            "the fine that will be charged if everything is returned today (R5.00 "
            "per day late). Copies already recorded as Lost are left out because "
            "they are handled with a lost-book fine. The reference date comes from "
            "@as_of and falls back to CURDATE() if it is not set. (4-table INNER "
            "JOIN, derived table, subquery, CONCAT, DATEDIFF, COUNT, MAX, SUM, "
            "GROUP BY)"
        ),
        sql="""\
SELECT CONCAT(m.first_name, ' ', m.last_name)                    AS member_name,
       m.email,
       COUNT(l.loan_id)                                          AS overdue_loans,
       GROUP_CONCAT(b.title ORDER BY b.title SEPARATOR '; ')     AS titles,
       MAX(DATEDIFF(d.today, l.due_date))                        AS max_days_overdue,
       SUM(DATEDIFF(d.today, l.due_date) * 5.00)                 AS estimated_fine
FROM Loan l
CROSS JOIN (SELECT COALESCE(@as_of, CURDATE()) AS today) AS d
INNER JOIN Member m     ON m.member_id = l.member_id
INNER JOIN Book_Copy bc ON bc.copy_id  = l.copy_id
INNER JOIN Book b       ON b.book_id   = bc.book_id
WHERE l.return_date IS NULL
  AND l.due_date < d.today
  AND l.copy_id NOT IN (SELECT copy_id
                        FROM Book_Copy
                        WHERE availability_status = 'Lost')
GROUP BY m.member_id, m.first_name, m.last_name, m.email
ORDER BY max_days_overdue DESC, member_name;""",
    ),
    Query(
        number=8,
        level="MEDIUM",
        title="Monthly lending activity by member type",
        purpose=(
            "shows how many loans were issued each month, how many have come back, "
            "how many came back late, how long copies are kept and each group's "
            "share of all loans, so the library can review loan periods and "
            "staffing. (INNER JOIN, DATE_FORMAT, COUNT, SUM, AVG, subquery, GROUP "
            "BY)"
        ),
        sql="""\
SELECT DATE_FORMAT(l.loan_date, '%Y-%m')                              AS loan_month,
       m.member_type,
       COUNT(*)                                                       AS loans_issued,
       COUNT(l.return_date)                                           AS returned,
       SUM(CASE WHEN l.return_date > l.due_date THEN 1 ELSE 0 END)    AS late_returns,
       ROUND(AVG(DATEDIFF(l.return_date, l.loan_date)), 1)            AS avg_days_kept,
       ROUND(100 * COUNT(*) / (SELECT COUNT(*) FROM Loan), 1)         AS pct_of_all_loans
FROM Loan l
INNER JOIN Member m ON m.member_id = l.member_id
GROUP BY DATE_FORMAT(l.loan_date, '%Y-%m'), m.member_type
ORDER BY loan_month, m.member_type;""",
    ),
    Query(
        number=9,
        level="COMPLEX",
        title="Members flagged for review: repeat late returners or high fines",
        purpose=(
            "helps the library decide whom to warn or suspend. A member is flagged "
            "if they returned at least two loans late AND their late-return rate is "
            "above the library-wide rate (nested subquery), OR their fines total "
            "R100 or more. (3 tables, LEFT JOIN, subquery, HAVING with AND/OR)"
        ),
        sql="""\
SELECT CONCAT(m.first_name, ' ', m.last_name)                              AS member_name,
       m.member_type,
       m.status,
       COUNT(l.loan_id)                                                    AS returned_loans,
       SUM(CASE WHEN l.return_date > l.due_date THEN 1 ELSE 0 END)         AS late_returns,
       ROUND(100 * SUM(CASE WHEN l.return_date > l.due_date THEN 1 ELSE 0 END)
                 / COUNT(l.loan_id), 1)                                    AS late_rate_pct,
       COALESCE(SUM(f.fine_amount), 0)                                     AS total_fines
FROM Member m
INNER JOIN Loan l ON l.member_id = m.member_id
LEFT JOIN Fine f  ON f.loan_id   = l.loan_id
WHERE l.return_date IS NOT NULL
GROUP BY m.member_id, m.first_name, m.last_name, m.member_type, m.status
HAVING (SUM(CASE WHEN l.return_date > l.due_date THEN 1 ELSE 0 END) >= 2
        AND 100 * SUM(CASE WHEN l.return_date > l.due_date THEN 1 ELSE 0 END) / COUNT(l.loan_id) >
            (SELECT 100 * SUM(CASE WHEN l2.return_date > l2.due_date THEN 1 ELSE 0 END)
                        / COUNT(l2.loan_id)
             FROM Loan l2
             WHERE l2.return_date IS NOT NULL))
    OR COALESCE(SUM(f.fine_amount), 0) >= 100
ORDER BY total_fines DESC, late_rate_pct DESC;""",
    ),
    Query(
        number=10,
        level="COMPLEX",
        title="Worn or withdrawn copies that are still in demand",
        purpose=(
            "tells the library which poor-condition copies to repair or replace "
            "first: copies that are Fair/Damaged, or Under Repair/Lost, and whose "
            "number of loans is at least the library-wide average per copy. (5 "
            "tables, LEFT JOIN, AND/OR, scalar subqueries in HAVING, MAX)"
        ),
        sql="""\
SELECT bc.copy_id,
       b.title,
       bc.copy_no,
       c.category_name,
       p.publisher_name,
       bc.condition_status,
       bc.availability_status,
       COUNT(l.loan_id)  AS times_loaned,
       MAX(l.loan_date)  AS last_loaned
FROM Book_Copy bc
INNER JOIN Book b      ON b.book_id      = bc.book_id
INNER JOIN Category c  ON c.category_id  = b.category_id
INNER JOIN Publisher p ON p.publisher_id = b.publisher_id
LEFT JOIN Loan l       ON l.copy_id      = bc.copy_id
WHERE bc.condition_status IN ('Fair', 'Damaged')
   OR bc.availability_status IN ('Under Repair', 'Lost')
GROUP BY bc.copy_id, b.title, bc.copy_no, c.category_name, p.publisher_name,
         bc.condition_status, bc.availability_status
HAVING COUNT(l.loan_id) >= (SELECT COUNT(*) FROM Loan) / (SELECT COUNT(*) FROM Book_Copy)
ORDER BY times_loaned DESC, last_loaned DESC;""",
    ),
)


def get_query(number: int) -> Query:
    """Return the report query with the given number (1-10)."""
    for query in QUERIES:
        if query.number == number:
            return query
    raise KeyError(f"There is no query number {number}; valid numbers are 1-{len(QUERIES)}.")


# ---------------------------------------------------------------------
# Parameterised statements used by the interactive menu (app.py)
# ---------------------------------------------------------------------

# Catalogue search by title or author name.  Both %s receive the same
# pattern, e.g. '%database%'.
SEARCH_CATALOGUE_SQL = """\
SELECT b.book_id,
       b.isbn,
       b.title,
       b.publication_year,
       (SELECT GROUP_CONCAT(CONCAT(a.first_name, ' ', a.last_name)
                            ORDER BY a.last_name SEPARATOR ', ')
        FROM Author_Book ab
        INNER JOIN Author a ON a.author_id = ab.author_id
        WHERE ab.book_id = b.book_id)                     AS authors,
       (SELECT COUNT(*)
        FROM Book_Copy bc
        WHERE bc.book_id = b.book_id
          AND bc.availability_status = 'Available')       AS available_copies
FROM Book b
WHERE b.title LIKE %s
   OR EXISTS (SELECT 1
              FROM Author_Book ab2
              INNER JOIN Author a2 ON a2.author_id = ab2.author_id
              WHERE ab2.book_id = b.book_id
                AND CONCAT(a2.first_name, ' ', a2.last_name) LIKE %s)
ORDER BY b.title"""

# All loans of one member (looked up by campus number), newest first.
MEMBER_LOANS_SQL = """\
SELECT l.loan_id,
       b.title,
       bc.copy_no,
       l.loan_date,
       l.due_date,
       l.return_date,
       CASE WHEN l.return_date IS NOT NULL THEN 'Returned'
            WHEN l.due_date < d.today      THEN 'Overdue'
            ELSE 'On loan' END                             AS loan_status
FROM Member m
CROSS JOIN (SELECT COALESCE(@as_of, CURDATE()) AS today) AS d
INNER JOIN Loan l       ON l.member_id = m.member_id
INNER JOIN Book_Copy bc ON bc.copy_id  = l.copy_id
INNER JOIN Book b       ON b.book_id   = bc.book_id
WHERE m.campus_number = %s
ORDER BY l.loan_date DESC, l.loan_id DESC"""

FIND_MEMBER_SQL = (
    "SELECT member_id, first_name, last_name, status "
    "FROM Member WHERE campus_number = %s"
)

FIND_LIBRARIAN_SQL = "SELECT librarian_id FROM Librarian WHERE staff_number = %s"

# FOR UPDATE locks the copy row so two librarians cannot lend the same copy.
FIND_COPY_FOR_UPDATE_SQL = (
    "SELECT bc.copy_id, bc.availability_status, bc.condition_status, b.title "
    "FROM Book_Copy bc INNER JOIN Book b ON b.book_id = bc.book_id "
    "WHERE bc.copy_id = %s FOR UPDATE"
)

COUNT_ACTIVE_LOANS_OF_COPY_SQL = (
    "SELECT COUNT(*) AS n FROM Loan WHERE copy_id = %s AND return_date IS NULL"
)

INSERT_LOAN_SQL = (
    "INSERT INTO Loan (member_id, copy_id, issued_by, loan_date, due_date) "
    "VALUES (%s, %s, %s, %s, %s)"
)

MARK_COPY_ON_LOAN_SQL = (
    "UPDATE Book_Copy SET availability_status = 'On Loan' WHERE copy_id = %s"
)

FIND_ACTIVE_LOAN_FOR_UPDATE_SQL = (
    "SELECT l.loan_id, l.loan_date, l.due_date, m.first_name, m.last_name, "
    "       b.title, bc.condition_status "
    "FROM Loan l "
    "INNER JOIN Member m     ON m.member_id = l.member_id "
    "INNER JOIN Book_Copy bc ON bc.copy_id  = l.copy_id "
    "INNER JOIN Book b       ON b.book_id   = bc.book_id "
    "WHERE l.copy_id = %s AND l.return_date IS NULL FOR UPDATE"
)

CLOSE_LOAN_SQL = "UPDATE Loan SET return_date = %s, received_by = %s WHERE loan_id = %s"

INSERT_FINE_SQL = (
    "INSERT INTO Fine (loan_id, fine_amount, reason, payment_status, fine_date) "
    "VALUES (%s, %s, %s, 'Unpaid', %s)"
)

RELEASE_COPY_SQL = (
    "UPDATE Book_Copy SET availability_status = %s, condition_status = %s "
    "WHERE copy_id = %s"
)
