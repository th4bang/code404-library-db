-- =====================================================================
-- CSC312 Practical Assignment 2 - University Library Lending System
-- Team Name : Code 404

-- =====================================================================

DROP DATABASE IF EXISTS university_library;
CREATE DATABASE university_library CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE university_library;

-- =====================================================================
-- 5.1  TABLE DEFINITIONS (created parents first, children last)
-- =====================================================================

CREATE TABLE Category (
    category_id    INT AUTO_INCREMENT PRIMARY KEY,
    category_name  VARCHAR(60)  NOT NULL,
    description    VARCHAR(255) NULL,
    CONSTRAINT uq_category_name UNIQUE (category_name)
) ENGINE=InnoDB;

CREATE TABLE Publisher (
    publisher_id    INT AUTO_INCREMENT PRIMARY KEY,
    publisher_name  VARCHAR(100) NOT NULL,
    city            VARCHAR(60)  NULL,
    email           VARCHAR(100) NULL,
    CONSTRAINT uq_publisher_name UNIQUE (publisher_name)
) ENGINE=InnoDB;

CREATE TABLE Author (
    author_id    INT AUTO_INCREMENT PRIMARY KEY,
    first_name   VARCHAR(50) NOT NULL,
    last_name    VARCHAR(50) NOT NULL,
    nationality  VARCHAR(50) NULL
) ENGINE=InnoDB;

CREATE TABLE Librarian (
    librarian_id  INT AUTO_INCREMENT PRIMARY KEY,
    staff_number  VARCHAR(15)  NOT NULL,
    email         VARCHAR(100) NOT NULL,
    first_name    VARCHAR(50)  NOT NULL,
    last_name     VARCHAR(50)  NOT NULL,
    hire_date     DATE         NOT NULL,
    CONSTRAINT uq_librarian_staff_no UNIQUE (staff_number),
    CONSTRAINT uq_librarian_email    UNIQUE (email),
    CONSTRAINT ck_librarian_email    CHECK (email LIKE '%_@_%')
) ENGINE=InnoDB;

CREATE TABLE Member (
    member_id          INT AUTO_INCREMENT PRIMARY KEY,
    campus_number      VARCHAR(15)  NOT NULL,
    email              VARCHAR(100) NOT NULL,
    first_name         VARCHAR(50)  NOT NULL,
    last_name          VARCHAR(50)  NOT NULL,
    member_type        ENUM('Student','Lecturer','Staff') NOT NULL,
    registration_date  DATE         NOT NULL,
    status             ENUM('Active','Suspended','Expired') NOT NULL DEFAULT 'Active',
    phone_number       VARCHAR(15)  NOT NULL,
    CONSTRAINT uq_member_campus_no UNIQUE (campus_number),
    CONSTRAINT uq_member_email     UNIQUE (email),
    CONSTRAINT ck_member_email     CHECK (email LIKE '%_@_%')
) ENGINE=InnoDB;

CREATE TABLE Book (
    book_id           INT AUTO_INCREMENT PRIMARY KEY,
    category_id       INT          NOT NULL,
    publisher_id      INT          NOT NULL,
    isbn              CHAR(13)     NOT NULL,
    title             VARCHAR(200) NOT NULL,
    publication_year  SMALLINT     NOT NULL,
    CONSTRAINT uq_book_isbn UNIQUE (isbn),
    CONSTRAINT ck_book_year CHECK (publication_year BETWEEN 1000 AND 2100),
    CONSTRAINT fk_book_category  FOREIGN KEY (category_id)
        REFERENCES Category (category_id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_book_publisher FOREIGN KEY (publisher_id)
        REFERENCES Publisher (publisher_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- Bridge entity for the Author <-> Book many-to-many relationship
CREATE TABLE Author_Book (
    book_id    INT NOT NULL,
    author_id  INT NOT NULL,
    PRIMARY KEY (book_id, author_id),
    CONSTRAINT fk_ab_book   FOREIGN KEY (book_id)
        REFERENCES Book (book_id)     ON DELETE CASCADE  ON UPDATE CASCADE,
    CONSTRAINT fk_ab_author FOREIGN KEY (author_id)
        REFERENCES Author (author_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

CREATE TABLE Book_Copy (
    copy_id             INT AUTO_INCREMENT PRIMARY KEY,
    book_id             INT NOT NULL,
    copy_no             INT NOT NULL,
    condition_status    ENUM('New','Good','Fair','Damaged') NOT NULL DEFAULT 'Good',
    availability_status ENUM('Available','On Loan','Under Repair','Lost') NOT NULL DEFAULT 'Available',
    CONSTRAINT uq_copy_book_no UNIQUE (book_id, copy_no),
    CONSTRAINT ck_copy_no CHECK (copy_no > 0),
    CONSTRAINT fk_copy_book FOREIGN KEY (book_id)
        REFERENCES Book (book_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- Loan: return_date and received_by are NULL while the book is still out
CREATE TABLE Loan (
    loan_id      INT AUTO_INCREMENT PRIMARY KEY,
    member_id    INT  NOT NULL,
    copy_id      INT  NOT NULL,
    issued_by    INT  NOT NULL,
    received_by  INT  NULL,
    loan_date    DATE NOT NULL,
    due_date     DATE NOT NULL,
    return_date  DATE NULL,
    CONSTRAINT ck_loan_due_after_loan   CHECK (due_date >= loan_date),
    CONSTRAINT ck_loan_return_after_loan CHECK (return_date IS NULL OR return_date >= loan_date),
    CONSTRAINT ck_loan_return_receiver  CHECK (
        (return_date IS NULL AND received_by IS NULL) OR
        (return_date IS NOT NULL AND received_by IS NOT NULL)),
    CONSTRAINT fk_loan_member   FOREIGN KEY (member_id)   REFERENCES Member (member_id),
    CONSTRAINT fk_loan_copy     FOREIGN KEY (copy_id)     REFERENCES Book_Copy (copy_id),
    CONSTRAINT fk_loan_issuer   FOREIGN KEY (issued_by)   REFERENCES Librarian (librarian_id),
    CONSTRAINT fk_loan_receiver FOREIGN KEY (received_by) REFERENCES Librarian (librarian_id)
) ENGINE=InnoDB;

-- Fine: loan_id is UNIQUE so a loan has at most one fine (1:0..1)
CREATE TABLE Fine (
    fine_id         INT AUTO_INCREMENT PRIMARY KEY,
    loan_id         INT           NOT NULL,
    fine_amount     DECIMAL(8,2)  NOT NULL,
    reason          ENUM('Overdue','Damaged','Lost') NOT NULL,
    payment_status  ENUM('Paid','Unpaid') NOT NULL DEFAULT 'Unpaid',
    fine_date       DATE          NOT NULL,
    CONSTRAINT uq_fine_loan UNIQUE (loan_id),
    CONSTRAINT ck_fine_amount CHECK (fine_amount >= 0),
    CONSTRAINT fk_fine_loan FOREIGN KEY (loan_id)
        REFERENCES Loan (loan_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- =====================================================================
-- 5.2  SAMPLE DATA  (ISBNs are illustrative sample values)
-- =====================================================================

INSERT INTO Category (category_id, category_name, description) VALUES
(1, 'Databases',           'Database design, SQL and data management'),
(2, 'Algorithms',          'Algorithm design and analysis'),
(3, 'Operating Systems',   'Operating system principles and design'),
(4, 'Artificial Intelligence', NULL),
(5, 'Biography',           'Autobiographies and biographies'),
(6, 'Literature',          'Fiction and literary classics');

INSERT INTO Publisher (publisher_id, publisher_name, city, email) VALUES
(1, 'Pearson',        'London',        'info@pearson.example'),
(2, 'McGraw-Hill',    'New York',      'info@mcgraw-hill.example'),
(3, 'MIT Press',      'Cambridge',     NULL),
(4, 'Wiley',          'Hoboken',       'support@wiley.example'),
(5, 'Little, Brown',  'London',        NULL),
(6, 'Pan Macmillan',  'Johannesburg',  'books@panmacmillan.example'),
(7, 'Heinemann',      NULL,            NULL);

INSERT INTO Author (author_id, first_name, last_name, nationality) VALUES
(1,  'Ramez',     'Elmasri',      NULL),
(2,  'Shamkant',  'Navathe',      NULL),
(3,  'Abraham',   'Silberschatz', 'American'),
(4,  'Henry',     'Korth',        NULL),
(5,  'S.',        'Sudarshan',    NULL),
(6,  'Thomas',    'Connolly',     'British'),
(7,  'Carolyn',   'Begg',         'British'),
(8,  'Thomas',    'Cormen',       'American'),
(9,  'Charles',   'Leiserson',    'American'),
(10, 'Ronald',    'Rivest',       'American'),
(11, 'Clifford',  'Stein',        'American'),
(12, 'Andrew',    'Tanenbaum',    'American'),
(13, 'Herbert',   'Bos',          'Dutch'),
(14, 'Stuart',    'Russell',      'British'),
(15, 'Peter',     'Norvig',       'American'),
(16, 'Nelson',    'Mandela',      'South African'),
(17, 'Trevor',    'Noah',         'South African'),
(18, 'Chinua',    'Achebe',       'Nigerian'),
(19, 'Peter',     'Galvin',       NULL),
(20, 'Greg',      'Gagne',        NULL);

INSERT INTO Book (book_id, category_id, publisher_id, isbn, title, publication_year) VALUES
(1,  1, 1, '9780133970777', 'Fundamentals of Database Systems',                   2016),
(2,  1, 2, '9780078022159', 'Database System Concepts',                           2019),
(3,  1, 1, '9780132943260', 'Database Systems: A Practical Approach',             2014),
(4,  2, 3, '9780262046305', 'Introduction to Algorithms',                         2022),
(5,  3, 1, '9780133591620', 'Modern Operating Systems',                           2014),
(6,  4, 1, '9780134610993', 'Artificial Intelligence: A Modern Approach',         2020),
(7,  5, 5, '9780316548182', 'Long Walk to Freedom',                               1994),
(8,  5, 6, '9781447299684', 'Born a Crime',                                       2016),
(9,  6, 7, '9780385474542', 'Things Fall Apart',                                  1958),
(10, 3, 4, '9781119456339', 'Operating System Concepts',                          2018);

INSERT INTO Author_Book (book_id, author_id) VALUES
(1,1),(1,2),
(2,3),(2,4),(2,5),
(3,6),(3,7),
(4,8),(4,9),(4,10),(4,11),
(5,12),(5,13),
(6,14),(6,15),
(7,16),
(8,17),
(9,18),
(10,3),(10,19),(10,20);

INSERT INTO Book_Copy (copy_id, book_id, copy_no, condition_status, availability_status) VALUES
(1,  1, 1, 'Good', 'Available'),
(2,  1, 2, 'Good', 'Available'),
(3,  1, 3, 'New',  'On Loan'),
(4,  2, 1, 'Good', 'Available'),
(5,  2, 2, 'Good', 'On Loan'),
(6,  3, 1, 'Fair', 'Available'),
(7,  3, 2, 'Good', 'Available'),
(8,  4, 1, 'Good', 'Available'),
(9,  4, 2, 'New',  'On Loan'),
(10, 5, 1, 'Good', 'Available'),
(11, 5, 2, 'Fair', 'Available'),
(12, 6, 1, 'Good', 'Available'),
(13, 6, 2, 'Good', 'On Loan'),
(14, 7, 1, 'Fair', 'Available'),
(15, 7, 2, 'Good', 'Available'),
(16, 8, 1, 'Good', 'Available'),
(17, 8, 2, 'New',  'Available'),
(18, 9, 1, 'Damaged', 'Under Repair'),
(19, 9, 2, 'Fair', 'Available'),
(20, 10, 1, 'Good', 'On Loan'),
(21, 10, 2, 'Good', 'Available');

INSERT INTO Librarian (librarian_id, staff_number, email, first_name, last_name, hire_date) VALUES
(1, 'LIB001', 'karen.jacobs@uwc.ac.za',    'Karen',    'Jacobs',   '2015-02-01'),
(2, 'LIB002', 'michael.adams@uwc.ac.za',   'Michael',  'Adams',    '2018-07-15'),
(3, 'LIB003', 'busisiwe.mthembu@uwc.ac.za','Busisiwe', 'Mthembu',  '2021-01-11');

INSERT INTO Member (member_id, campus_number, email, first_name, last_name, member_type, registration_date, status, phone_number) VALUES
(1,  'S3900101', 'thabo.mokoena@myuwc.ac.za',   'Thabo',   'Mokoena',      'Student',  '2024-02-05', 'Active', '0821234501'),
(2,  'S3900102', 'aisha.patel@myuwc.ac.za',     'Aisha',   'Patel',        'Student',  '2024-02-05', 'Active', '0821234502'),
(3,  'S3900103', 'lwazi.dlamini@myuwc.ac.za',   'Lwazi',   'Dlamini',      'Student',  '2025-02-03', 'Active', '0821234503'),
(4,  'S3900104', 'naledi.khumalo@myuwc.ac.za',  'Naledi',  'Khumalo',      'Student',  '2025-02-03', 'Active', '0821234504'),
(5,  'S3900105', 'ruan.vdmerwe@myuwc.ac.za',    'Ruan',    'van der Merwe','Student',  '2023-02-06', 'Active', '0821234505'),
(6,  'S3900106', 'zanele.nkosi@myuwc.ac.za',    'Zanele',  'Nkosi',        'Student',  '2023-02-06', 'Active', '0821234506'),
(7,  'S3900107', 'fatima.abrahams@myuwc.ac.za', 'Fatima',  'Abrahams',     'Student',  '2026-02-02', 'Active', '0821234507'),
(8,  'S3900108', 'sipho.ndlovu@myuwc.ac.za',    'Sipho',   'Ndlovu',       'Student',  '2022-02-07', 'Suspended', '0821234508'),
(9,  'E1000201', 'pieter.botha@uwc.ac.za',      'Pieter',  'Botha',        'Lecturer', '2019-03-01', 'Active', '0821234509'),
(10, 'E1000202', 'nomsa.zulu@uwc.ac.za',        'Nomsa',   'Zulu',         'Staff',    '2020-06-01', 'Active', '0821234510'),
(11, 'S3900111', 'lerato.mahlangu@myuwc.ac.za', 'Lerato',  'Mahlangu',     'Student',  '2026-10-01', 'Active', '0821234511');

-- Loan period = 14 days. Loans 11-15 are still active (return_date NULL).
INSERT INTO Loan (loan_id, member_id, copy_id, issued_by, received_by, loan_date, due_date, return_date) VALUES
(1,  1, 1,  1, 1,    '2026-08-03', '2026-08-17', '2026-08-15'),
(2,  2, 4,  2, 2,    '2026-08-05', '2026-08-19', '2026-08-30'),
(3,  3, 8,  1, 3,    '2026-08-10', '2026-08-24', '2026-08-24'),
(4,  4, 12, 3, 3,    '2026-08-12', '2026-08-26', '2026-09-05'),
(5,  5, 6,  2, 2,    '2026-08-20', '2026-09-03', '2026-09-01'),
(6,  1, 10, 1, 1,    '2026-09-01', '2026-09-15', '2026-09-14'),
(7,  6, 14, 2, 2,    '2026-09-02', '2026-09-16', '2026-09-20'),
(8,  7, 16, 3, 1,    '2026-09-08', '2026-09-22', '2026-09-21'),
(9,  2, 2,  1, 1,    '2026-09-10', '2026-09-24', '2026-10-02'),
(10, 8, 18, 2, 2,    '2026-09-15', '2026-09-29', '2026-09-28'),
(11, 9, 3,  1, NULL, '2026-09-28', '2026-10-12', NULL),
(12, 3, 20, 2, NULL, '2026-09-20', '2026-10-04', NULL),
(13, 10,13, 3, NULL, '2026-09-25', '2026-10-09', NULL),
(14, 5, 9,  1, NULL, '2026-10-05', '2026-10-19', NULL),
(15, 1, 5,  2, NULL, '2026-10-07', '2026-10-21', NULL);

-- Overdue fine rate used: R5.00 per day late; damaged book = flat R150.00
INSERT INTO Fine (fine_id, loan_id, fine_amount, reason, payment_status, fine_date) VALUES
(1, 2,  55.00,  'Overdue', 'Paid',   '2026-08-30'),
(2, 4,  50.00,  'Overdue', 'Paid',   '2026-09-05'),
(3, 7,  20.00,  'Overdue', 'Unpaid', '2026-09-20'),
(4, 9,  40.00,  'Overdue', 'Unpaid', '2026-10-02'),
(5, 10, 150.00, 'Damaged', 'Unpaid', '2026-09-28');

-- =====================================================================
-- 5.3  VERIFICATION (use for screenshots)
-- =====================================================================
-- SHOW TABLES;
-- DESCRIBE Loan;
-- SELECT * FROM Category;    SELECT * FROM Publisher;   SELECT * FROM Author;
-- SELECT * FROM Librarian;   SELECT * FROM Member;
-- SELECT * FROM Book;        SELECT * FROM Author_Book; SELECT * FROM Book_Copy;
-- SELECT * FROM Loan;        SELECT * FROM Fine;

-- Constraint tests (each should FAIL with an error - useful for Testing section):
-- INSERT INTO Fine (loan_id, fine_amount, reason, fine_date) VALUES (1, -5, 'Overdue', '2026-10-10');      -- negative fine
-- INSERT INTO Fine (loan_id, fine_amount, reason, fine_date) VALUES (2, 10, 'Overdue', '2026-10-10');      -- 2nd fine for loan 2 (UNIQUE)
-- INSERT INTO Loan (member_id, copy_id, issued_by, loan_date, due_date) VALUES (1, 1, 1, '2026-10-10', '2026-10-01'); -- due before loan
-- INSERT INTO Book (category_id, publisher_id, isbn, title, publication_year) VALUES (99, 1, '9780000000000', 'X', 2020); -- bad FK
-- INSERT INTO Book (category_id, publisher_id, isbn, title, publication_year) VALUES (1, 1, '9780133970777', 'X', 2020);  -- duplicate ISBN

-- =====================================================================
-- 6.x  SQL QUERIES (Member 4: Queries 1-5)
-- =====================================================================

-- Q1 (SIMPLE) Outstanding fines, largest first
-- Purpose: lets librarians see which fines still need to be collected.
SELECT fine_id, loan_id, fine_amount, reason, fine_date
FROM Fine
WHERE payment_status = 'Unpaid'
ORDER BY fine_amount DESC;

-- Q2 (MEDIUM) Collection size and availability per category
-- Purpose: shows which subject areas have few free copies so the library
-- can decide where to buy more copies. (INNER JOIN, COUNT, SUM, GROUP BY)
SELECT c.category_name,
       COUNT(DISTINCT b.book_id)                          AS titles,
       COUNT(bc.copy_id)                                  AS total_copies,
       SUM(bc.availability_status = 'Available')          AS available_copies
FROM Category c
INNER JOIN Book b       ON b.category_id = c.category_id
INNER JOIN Book_Copy bc ON bc.book_id    = b.book_id
GROUP BY c.category_id, c.category_name
ORDER BY total_copies DESC, c.category_name;

-- Q3 (MEDIUM) Borrowing activity and fines per member
-- Purpose: identifies heavy borrowers and members who owe money, including
-- members who have never borrowed (LEFT JOIN). (LEFT JOIN, CONCAT, COUNT, SUM, GROUP BY)
SELECT CONCAT(m.first_name, ' ', m.last_name)  AS member_name,
       m.member_type,
       COUNT(l.loan_id)                        AS total_loans,
       COALESCE(SUM(f.fine_amount), 0)         AS total_fines
FROM Member m
LEFT JOIN Loan l ON l.member_id = m.member_id
LEFT JOIN Fine f ON f.loan_id   = l.loan_id
GROUP BY m.member_id, m.first_name, m.last_name, m.member_type
ORDER BY total_fines DESC, total_loans DESC, member_name;

-- Q4 (COMPLEX) Most popular titles (borrowed more than the average title) with authors
-- Purpose: supports purchasing decisions by showing which titles are in
-- above-average demand. (6 tables, nested subquery, GROUP_CONCAT, HAVING)
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
ORDER BY times_borrowed DESC, b.title;

-- Q5 (COMPLEX) Fine income by category (HAVING with AND/OR, conditional SUM)
-- Purpose: shows which subject areas generate most fines and how much is
-- still unpaid, helping target reminders and loan-period policy.
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
ORDER BY total_fines DESC;

-- =====================================================================
-- 6.y  SQL QUERIES (Member 5: Queries 6-10)
-- =====================================================================

-- Q6 (SIMPLE) Catalogue search by title keyword
-- Purpose: supports the "members can search for books" workflow; shows
-- the newest matching titles first. (WHERE with LIKE, ORDER BY)
SELECT book_id, isbn, title, publication_year
FROM Book
WHERE title LIKE '%Database%'
ORDER BY publication_year DESC, title;

-- Q7 (MEDIUM) Members with overdue loans, with estimated fines
-- Purpose: gives librarians a contact list of members who still hold copies
-- past their due date: how many copies, which titles, the longest delay and
-- the fine that will be charged if everything is returned today (R5.00 per
-- day late). Copies already recorded as Lost are left out because they are
-- handled with a lost-book fine. The reference date comes from @as_of and
-- falls back to CURDATE() if it is not set. (4-table INNER JOIN, derived
-- table, subquery, CONCAT, DATEDIFF, COUNT, MAX, SUM, GROUP BY)
SET @as_of = '2026-10-11';
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
ORDER BY max_days_overdue DESC, member_name;

-- Q8 (MEDIUM) Monthly lending activity by member type
-- Purpose: shows how many loans were issued each month, how many have
-- come back, how many came back late, how long copies are kept and each
-- group's share of all loans, so the library can review loan periods and
-- staffing. (INNER JOIN, DATE_FORMAT, COUNT, SUM, AVG, subquery, GROUP BY)
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
ORDER BY loan_month, m.member_type;

-- Q9 (COMPLEX) Members flagged for review: repeat late returners or high fines
-- Purpose: helps the library decide whom to warn or suspend. A member is
-- flagged if they returned at least two loans late AND their late-return
-- rate is above the library-wide rate (nested subquery), OR their fines
-- total R100 or more. (3 tables, LEFT JOIN, subquery, HAVING with AND/OR)
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
ORDER BY total_fines DESC, late_rate_pct DESC;

-- Q10 (COMPLEX) Worn or withdrawn copies that are still in demand
-- Purpose: tells the library which poor-condition copies to repair or
-- replace first: copies that are Fair/Damaged, or Under Repair/Lost, and
-- whose number of loans is at least the library-wide average per copy.
-- (5 tables, LEFT JOIN, AND/OR, scalar subqueries in HAVING, MAX)
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
ORDER BY times_loaned DESC, last_loaned DESC;
