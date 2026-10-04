# CLAUDE.md - Sales Bonus Tracker (`sales_bonus_grid`)

Module Technical Name: `sales_bonus_grid`  
Target Odoo Version: `19.0` (Community & Enterprise compatible)  
Technical Standard: Built according to the official Odoo 19 development reference (`odoo19skill`).

---

## 1. Module Overview & Architecture

`sales_bonus_grid` provides a transparent, automated, and live sales commission tracker for sales reps and management.

### Architectural Blueprint
- **`sales.bonus.grid`**: Master grid per company and month declaring calculation mode (`cliff` or `progressive`), revenue recognition basis (`invoiced` or `paid`), and ordered tier lines.
- **`sales.bonus.grid.line`**: Individual tier definition specifying lower revenue threshold (`revenue_from`), upper bound (`revenue_to`), and bonus value (fixed monetary amount or percentage).
- **`sales.bonus.statement`**: Monthly statement snapshotting recognized revenue, earned bonus, tier progression, late credit note warnings, and freeze status.
- **`sales.bonus.unlock.wizard`**: Security wizard prompting managers for mandatory audit justification when reopening closed monthly statements.
- **`res.company` / `res.config.settings`**: Company-level configuration for closing lock day, hourly cron refresh toggle, and default calculation rules.

---

## 2. Done vs Undone Log

### Completed Tasks (Done)

- [x] **Module Foundation & Manifest**
  - Configured `__manifest__.py` with dependencies (`base`, `sale`, `sales_team`, `account`, `mail`).
  - Standard module structure: `models/`, `views/`, `wizard/`, `security/`, `data/`, `static/`, `tests/`, `i18n/`.

- [x] **Data Models (Odoo 19 Compliant)**
  - `sales.bonus.grid`:
    - Auto-derived name, unique constraint `(company_id, date_month)` using `models.Constraint`.
    - Python constraints enforcing first threshold at `0.0`, strictly ascending values, and percentage rule for progressive mode.
    - Write/unlink protection on locked months using `@api.ondelete(at_uninstall=False)`.
    - Auto-inheritance logic (`get_or_create_grid`) copying previous month's tiers without altering past records.
  - `sales.bonus.grid.line`:
    - Sequence ordering, computed upper bounds (`revenue_to`), formatted bonus displays (`bonus_display`).
    - Negative and percentage boundary validations.
  - `sales.bonus.statement`:
    - Unique constraint `(user_id, company_id, date_month)`.
    - Batch-friendly revenue computation via `_read_group` on `account.move` (`out_invoice`, `out_refund`, `amount_untaxed_signed`).
    - Accurate bonus computation for both **Cliff** and **Progressive** calculation modes.
    - Dynamic metrics: `current_line_id`, `next_line_id`, `remaining_to_next`, `next_bonus`, `progress`.
    - Late credit note detection logic comparing refund creation dates against past statement lock dates.
    - Immutability on locked statements: figures are frozen and preserved.
  - `res.company` & `res.config.settings`:
    - Configuration fields for lock day (1-28), auto-refresh toggle, default calculation mode, and default basis.

- [x] **Security & Access Control**
  - Reused native Sales security groups (`sales_team.group_sale_salesman`, `sales_team.group_sale_salesman_all_leads`, `sales_team.group_sale_manager`) with zero custom security groups.
  - Configured `ir.model.access.csv`: read-only for salespeople, full CRUD for managers.
  - Configured `ir.rule`:
    - Multi-company isolation on grids, lines, and statements.
    - Personal statement isolation: salespeople only see statements where `user_id == user.id`.
    - Manager rule: full visibility across all team statements. *(Note: Odoo evaluates rules with OR for the same group set. Managers match both the personal rule and manager rule because `group_sale_manager` implies the salesman groups. This implicit group inheritance is required for managers to see other salespeople's statements.)*

- [x] **Scheduled Actions (ir.cron)**
  - Hourly job: `cron_refresh_open_statements` to refresh live figures and ensure all active salespeople have statements.
  - Daily job: `cron_lock_closed_months` to auto-lock past month statements once the company's lock day has passed.
  - Monthly job: `cron_ensure_monthly_grids` to pre-generate grids via inheritance on the 1st of each month.

- [x] **User Interface & Views**
  - Personal "My Bonus" dashboard (`view_sales_bonus_statement_my_bonus_form`):
    - Top metric stat cards: Month-to-date Revenue, Earned Bonus, Current Tier, Target Tier.
    - Dynamic progress bar with live caption ("X more to reach Tier Y — bonus goes from A to B").
    - Embedded tier table with active tier row highlighting (`decoration-success`, `decoration-bf`, `decoration-info`).
    - Late credit note alert banners and locked status banners.
    - Header action buttons: "Refresh Figures", "View Counted Invoices", "Lock Statement", "Unlock Statement".
  - Manager List view with column totals (`sum="Total Revenue"`, `sum="Total Bonus"`), badges, and status indicators.
  - Reporting views: Pivot analysis (`sales.bonus.statement.pivot`) and Graph analysis (`sales.bonus.statement.graph`).
  - Search view with rich filters (My Statements, Open, Locked, Current Month) and Group By options (Salesperson, Month, Company, Status, Tier).
  - Grid management form/list views with bottom-editable lines.
  - Sales Settings integration (`res_config_settings_views.xml`).
  - Menus:
    - `Sales → My Bonus` (sequence 2)
    - `Sales → Reporting → Team Bonuses` (sequence 15)
    - `Sales → Configuration → Bonus Grids` (sequence 45)

- [x] **Wizards**
  - `sales.bonus.unlock.wizard` with validation and chatter audit posting.

- [x] **Translations & Assets**
  - French translation dictionary (`i18n/fr.po`).
  - SCSS stylesheets (`static/src/scss/sales_bonus.scss`) declared in `web.assets_backend`.

- [x] **Automated Test Suite**
  - `tests/test_sales_bonus_grid.py` covering:
    - Constraint validation (0 threshold, ascending order, duplicates, progressive percent requirement).
    - Cliff mode bonus calculations at exact boundary values.
    - Progressive mode multi-slice percentage mathematics.
    - Credit note subtraction via `amount_untaxed_signed`.
    - Grid inheritance from previous months.
    - Lock immutability and manager unlock workflows.
    - Record rules security isolation between salespeople and managers.

- [x] **Bug Fixes**
  - Fixed Odoo Server Error in `res_config_settings_views.xml` by correcting the XPath from `//app[@name='sale']` to `//app[@name='sale_management']`.
  - Removed redundancy in bonus values: deleted `bonus_display` and converted `bonus_value` to a `Monetary` field.
  - Hid the calculation `mode` field from views since it is always treated as a fixed amount.
  - Fixed UI warnings for FontAwesome icons (`fa-lock` and `fa-exclamation-circle`) missing `title` attributes.
  - Fixed `currency_id` appearing as a visible column in the Bonus Tiers one-to-many list (`line_ids`) on the grid form. In Odoo 17+/19, `invisible="1"` on a `<list>` column hides the cell value but still renders the column header; replaced with `column_invisible="1"` in `sales_bonus_grid_views.xml` to fully remove the column from the DOM while keeping the field available to the `monetary` widget on `bonus_value`.

- [x] **UI & UX Improvements**
  - Integrated `year_month_widget` (using the `month_picker` widget) across grid and statement views for intuitive month selection. Added it as a dependency in `__manifest__.py`.
  - Removed the "Revenue Basis" and "Last Refresh" footer section from the "My Bonus" dashboard for a cleaner interface.
  - Fixed missing `widget="monetary"` on `bonus_value` in the grid tiers inline list; added `currency_id` as an invisible column so the currency symbol renders correctly.
  - Restricted the "Refresh Figures" button to `sales_team.group_sale_manager` only — regular salespeople can no longer trigger a refresh (which was causing an access-denied error).
  - Disabled row-click navigation on the **Monthly Bonus Grid Tiers** table in the "My Bonus" dashboard: added `no_open="True"` directly on the `<list>` element inside `grid_line_ids` (complementing the existing `options="{'no_open': True}"` on the field). Tier rows are now purely informational and cannot be clicked to open the underlying grid line record.
  - Removed "New" button from the Team Bonuses list and My Bonus form: added `create="0"` to the `<list>` and `<form>` view tags, plus `{'create': False}` to the `action_sales_bonus_statement_manager` action context. Statements are system-generated and must never be manually created.

- [x] **Translations (fr.po)**
  - Regenerated `i18n/fr.po` from a full Odoo-extracted `.pot` (1248 lines vs. the original 20-line stub).
  - Completed all French translations with simple, clear business vocabulary. All previously empty `msgstr ""` entries are now filled.

---

### Future Roadmap / Optional Backlog (Undone / v2)

- [ ] **Phase 2 OWL Component / Systray Indicator (FR-10)**
  - Systray quick widget displaying the salesperson's current month bonus in the top navbar with a direct link to My Bonus.
- [ ] **Enterprise Payroll Bridge Module (`sales_bonus_grid_payroll`, FR-12)**
  - Optional bridge module depending on `hr_payroll` (Enterprise) adding a "Push to Payslip" action for locked statements.
- [ ] **Multi-Currency Conversion (v2)**
  - Auto-converting foreign currency invoices to company currency on grids if non-company currencies are introduced.
- [ ] **Direct Commission per Product/Category (v2)**
  - Granular commission rules on specific product lines or categories.

---

## 3. Code Notes & Architectural Rationale

> The source Python files carry minimal inline comments: every architectural decision and "why" lives in this section instead. Keep this section updated with any future modifications.

### `models/sales_bonus_grid.py`

- **`date_month` normalization**: The field is constrained and automatically cast to the 1st day of the target month (`day=1`) in both `create()` and `write()` methods. This simplifies range queries, SQL UNIQUE indexing, and monthly comparisons.
- **SQL Constraint `_unique_company_month`**: Defined using Odoo 19's `models.Constraint('UNIQUE(company_id, date_month)', ...)` replacing the legacy `_sql_constraints` attribute.
- **`_check_lines()` constraint**:
  - Requires `sorted_lines[0].revenue_from == 0.0` so that any positive revenue (even from 0.01) is strictly covered by a tier.
  - Ensures strictly ascending thresholds: `line[i].revenue_from < line[i+1].revenue_from` (disallowing equal thresholds).
  - In `progressive` mode, enforces `bonus_type == 'percent'` across all lines, because applying fixed flat bonuses across slices would lead to ambiguous slice allocation.
- **`write()` & `_unlink_if_not_locked()` lock protection**: When a month has statements in `locked` state, modifications to `mode`, `revenue_basis`, `date_month`, `company_id`, or `line_ids` are rejected unless explicitly running in a bypass context. Unlinking uses `@api.ondelete(at_uninstall=False)` per Odoo 19 standards.
- **`get_or_create_grid(company, target_date)`**: Checks if a grid already exists for `(company, month_start)`. If missing, it locates the most recent previous grid (`date_month < month_start`) and deep-copies its configuration and lines into a new grid instance linked via `source_grid_id`. This guarantees isolation: future changes to the new month never alter prior months.

---

### `models/sales_bonus_grid_line.py`

- **`revenue_to` (computed)**: The upper revenue bound is dynamically computed from the next tier line's `revenue_from`. It is not stored in the database, eliminating data synchronization anomalies when tier thresholds are adjusted.
- **`bonus_display` (computed)**: Pre-formats the display string with company currency symbol or percentage mark for clean presentation in list views and tooltips.
- **Cascading lock guard**: Modifications or deletions of line items check whether parent `grid_id.is_locked` is active, preventing inadvertent line changes on closed periods.

---

### `models/sales_bonus_statement.py`

- **Revenue Recognition (`_get_invoices_domain` & `_read_group`)**:
  - Filtered by `move_type in ('out_invoice', 'out_refund')`, `state == 'posted'`, `invoice_user_id == user.id`, `company_id == company.id`, and `invoice_date` falling within the 1st and last day of `date_month`.
  - In `paid` basis, additionally filters by `payment_state in ('paid', 'in_payment')`.
  - Aggregates `amount_untaxed_signed:sum` directly in the database. Customer invoices have positive signed untaxed amounts, while credit notes have negative signed untaxed amounts, naturally computing Net Invoiced Revenue in company currency without looping Python records.
- **Bonus Calculation Engine (`_calculate_bonus`)**:
  - **Cliff Mode**: Identifies the single active tier line $T_i$ where `revenue_from <= revenue` and `revenue < next_line.revenue_from`. Bonus is evaluated either as `line.bonus_value` (fixed) or `revenue * (line.bonus_value / 100.0)` (percentage).
  - **Progressive Mode**: Iterates over all tier intervals $[L_k, U_k]$. For each tier where $\text{revenue} > L_k$, the slice amount $S_k = \min(\text{revenue}, U_k) - L_k$ is calculated, and the bonus slice $S_k \times (\text{rate}_k / 100.0)$ is accumulated.
  - **Next Tier & Progress**:
    - `remaining_to_next`: $\max(0, \text{next\_line.revenue\_from} - \text{revenue})$.
    - `next_bonus`: The projected bonus if revenue were to reach `next_line.revenue_from`.
    - `progress`: Percentage completion within the current tier span $[L_{\text{curr}}, L_{\text{next}}]$, clamped between $0.0\%$ and $100.0\%$. At top tier, progress is set to $100.0\%$.
- **Snapshot Immutability**:
  - When `state == 'locked'`, `_compute_revenue_and_bonus()` immediately exits unless `context.get('force_recompute')` is set. This protects historical payroll/financial snapshots against post-close database changes.
- **Late Credit Note Detection (`_compute_late_credit_notes`)**:
  - Detects credit notes posted with `invoice_date` inside a past *locked* month, but whose `create_date` is later than that statement's `locked_on` timestamp.
  - Banners a notice on the salesperson's current open statement so that finance can manually review and adjust if appropriate.
- **`action_open_my_bonus()`**:
  - Server action invoked by the "Sales → My Bonus" menu item.
  - Automatically fetches or instantiates the statement for `self.env.user` for the current month (creating or inheriting the company grid if necessary), and returns a form view window action.

---

### `wizard/sales_bonus_unlock_wizard.py`

- **Auditability**: Unlocking a frozen statement is restricted to `sales_team.group_sale_manager`. A non-empty reason is mandatory and posted directly to the statement's chatter alongside the user and timestamp.

---

## 4. How to Run Tests

Run the test suite using Odoo's test runner:
```bash
odoo-bin -c odoo.conf -d <database_name> -u sales_bonus_grid --test-tags sales_bonus_grid --stop-after-init
```

---

## 5. Changelog

### 2026-10-04

- **i18n — `fr.po` completed**:
  - Filled in all empty `msgstr ""` entries for French translations with simple, natural French terminology (*Grille de primes*, *Palier*, *Relevé de primes*, *Commercial*, *Verrouiller/Déverrouiller*, *Chiffre d'affaires (CA)*).
  - Preserved existing translations unchanged.
- **action-1056 (`sales.bonus.grid` list view)**:
  - Changed `mode` and `is_locked` to `optional="hide"` in `views/sales_bonus_grid_views.xml`.
  - Both columns are hidden by default from the grid list view, but can be toggled via the optional column picker.
- **action-1058 (`sales.bonus.statement` list view)**:
  - Added `optional="hide"` to `currency_id` alongside `invisible="1"` in `views/sales_bonus_statement_views.xml` to fully remove it from the column picker.
  - Changed `state` badge from always visible to `optional="hide"` (hidden by default, toggleable).
- **Bonus Dashboard (`view_sales_bonus_statement_my_bonus_form`) — Monetary Format for Bonus & Revenue Tiers**:
  - `models/sales_bonus_grid_line.py`: Added `store=True` to `currency_id`.
  - `views/sales_bonus_statement_views.xml`: Added `<field name="currency_id" column_invisible="1"/>` in the `grid_line_ids` `<list>` so the web client fetches the currency on each tier record.
  - Added `options="{'currency_field': 'currency_id'}"` and `widget="monetary"` to `bonus_value`, `revenue_from`, and `revenue_to` so values render in proper monetary format with currency symbols.
- **Repository Hygiene**:
  - Added [`.gitignore`](file:///c:/Program%20Files/Odoo%2019.0.20260724/server/odoo/mnt/sales_bonus_grid/.gitignore) ignoring Python bytecode (`__pycache__/`, `*.pyc`), IDEs (`.vscode/`, `.idea/`), OS metadata (`Thumbs.db`, `.DS_Store`), and log/temp files.


- **Bonus Dashboard -- Hide Salesperson / Company / Month header**:
  - `views/sales_bonus_statement_views.xml`: Removed the subtitle div containing `user_id`, `company_id`, and `date_month` from the "My Bonus" form view. The statement title (<h2>) already conveys full context, making the repeated metadata redundant.
