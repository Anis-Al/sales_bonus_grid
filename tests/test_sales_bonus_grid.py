# -*- coding: utf-8 -*-
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError, UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'sales_bonus_grid')
class TestSalesBonusGrid(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id

        cls.group_salesman = cls.env.ref('sales_team.group_sale_salesman')
        cls.group_manager = cls.env.ref('sales_team.group_sale_manager')

        cls.salesperson_1 = cls.env['res.users'].create({
            'name': 'Seller Alice',
            'login': 'seller_alice',
            'email': 'alice@example.com',
            'group_ids': [(6, 0, [cls.group_salesman.id])],
            'company_ids': [(6, 0, [cls.company.id])],
            'company_id': cls.company.id,
        })
        cls.salesperson_2 = cls.env['res.users'].create({
            'name': 'Seller Bob',
            'login': 'seller_bob',
            'email': 'bob@example.com',
            'group_ids': [(6, 0, [cls.group_salesman.id])],
            'company_ids': [(6, 0, [cls.company.id])],
            'company_id': cls.company.id,
        })
        cls.manager_user = cls.env['res.users'].create({
            'name': 'Manager Charlie',
            'login': 'manager_charlie',
            'email': 'charlie@example.com',
            'group_ids': [(6, 0, [cls.group_manager.id])],
            'company_ids': [(6, 0, [cls.company.id])],
            'company_id': cls.company.id,
        })

        cls.customer = cls.env['res.partner'].create({
            'name': 'Acme Corp',
            'company_id': cls.company.id,
        })

        cls.october_month = date(2029, 10, 1)
        cls.november_month = date(2029, 11, 1)
        cls.december_month = date(2029, 12, 1)
        cls.january_month = date(2030, 1, 1)
        cls.february_month = date(2030, 2, 1)
        cls.march_month = date(2030, 3, 1)

    def _create_sample_grid_cliff(self, month=None):
        """Creates a Cliff grid: 0..10k -> 0; 10k..20k -> 50; 20k+ -> 100.
        Idempotent: returns an existing grid if one already exists for the given
        company+month, preventing UNIQUE constraint collisions within a test method.
        """
        month = month or self.october_month
        existing = self.env['sales.bonus.grid'].search([
            ('company_id', '=', self.company.id),
            ('date_month', '=', month),
        ], limit=1)
        if existing:
            return existing
        grid = self.env['sales.bonus.grid'].create({
            'company_id': self.company.id,
            'date_month': month,
            'mode': 'cliff',
            'revenue_basis': 'invoiced',
            'line_ids': [
                (0, 0, {'sequence': 1, 'name': 'Tier 1 (Under 10k)', 'revenue_from': 0.0, 'bonus_type': 'fixed', 'bonus_value': 0.0}),
                (0, 0, {'sequence': 2, 'name': 'Tier 2 (10k-20k)', 'revenue_from': 10000.0, 'bonus_type': 'fixed', 'bonus_value': 50.0}),
                (0, 0, {'sequence': 3, 'name': 'Tier 3 (20k+)', 'revenue_from': 20000.0, 'bonus_type': 'fixed', 'bonus_value': 100.0}),
            ]
        })
        return grid

    def _create_posted_invoice(self, user, invoice_date, amount, move_type='out_invoice'):
        """Helper to create and post an invoice or refund for a user."""
        move = self.env['account.move'].create({
            'move_type': move_type,
            'partner_id': self.customer.id,
            'invoice_user_id': user.id,
            'company_id': self.company.id,
            'invoice_date': invoice_date,
            'date': invoice_date,
            'invoice_line_ids': [
                (0, 0, {
                    'name': 'Test Service',
                    'quantity': 1,
                    'price_unit': amount,
                    'tax_ids': [(5, 0, 0)],
                })
            ]
        })
        move.action_post()
        return move

    def test_01_grid_validation_constraints(self):
        """Verify grid constraint checks (first tier 0, ascending thresholds, unique month)."""
        MONTH_A = date(2029, 3, 1)
        MONTH_B = date(2029, 4, 1)
        MONTH_C = date(2029, 5, 1)

        with self.assertRaises(ValidationError):
            self.env['sales.bonus.grid'].create({
                'company_id': self.company.id,
                'date_month': MONTH_A,
                'line_ids': [
                    (0, 0, {'name': 'Tier 1', 'revenue_from': 500.0, 'bonus_type': 'fixed', 'bonus_value': 10.0}),
                ]
            })

        with self.assertRaises(ValidationError):
            self.env['sales.bonus.grid'].create({
                'company_id': self.company.id,
                'date_month': MONTH_B,
                'line_ids': [
                    (0, 0, {'name': 'Tier 1', 'revenue_from': 0.0, 'bonus_type': 'fixed', 'bonus_value': 0.0}),
                    (0, 0, {'name': 'Tier 2', 'revenue_from': 10000.0, 'bonus_type': 'fixed', 'bonus_value': 50.0}),
                    (0, 0, {'name': 'Tier 3', 'revenue_from': 10000.0, 'bonus_type': 'fixed', 'bonus_value': 100.0}),
                ]
            })

        with self.assertRaises(ValidationError):
            self.env['sales.bonus.grid'].create({
                'company_id': self.company.id,
                'date_month': MONTH_C,
                'mode': 'progressive',
                'line_ids': [
                    (0, 0, {'name': 'Tier 1', 'revenue_from': 0.0, 'bonus_type': 'fixed', 'bonus_value': 0.0}),
                    (0, 0, {'name': 'Tier 2', 'revenue_from': 10000.0, 'bonus_type': 'fixed', 'bonus_value': 50.0}),
                ]
            })

    def test_02_cliff_mode_fixed_bonus(self):
        """Test Cliff mode calculations with fixed amounts at boundary thresholds."""
        grid = self._create_sample_grid_cliff(self.october_month)
        lines = grid.line_ids.sorted('revenue_from')
        t1, t2, t3 = lines[0], lines[1], lines[2]

        stmt = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_1.id,
            'company_id': self.company.id,
            'date_month': self.october_month,
            'grid_id': grid.id,
        })

        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 5), 9999.0)
        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 9999.0)
        self.assertEqual(stmt.bonus, 0.0)
        self.assertEqual(stmt.current_line_id, t1)
        self.assertEqual(stmt.next_line_id, t2)
        self.assertEqual(stmt.remaining_to_next, 1.0)
        self.assertEqual(stmt.next_bonus, 50.0)
        self.assertAlmostEqual(stmt.progress, 99.99, places=2)

        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 10), 1.0)
        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 10000.0)
        self.assertEqual(stmt.bonus, 50.0)
        self.assertEqual(stmt.current_line_id, t2)
        self.assertEqual(stmt.next_line_id, t3)
        self.assertEqual(stmt.remaining_to_next, 10000.0)
        self.assertEqual(stmt.next_bonus, 100.0)
        self.assertEqual(stmt.progress, 0.0)

        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 15), 10000.0)
        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 20000.0)
        self.assertEqual(stmt.bonus, 100.0)
        self.assertEqual(stmt.current_line_id, t3)
        self.assertFalse(stmt.next_line_id)
        self.assertEqual(stmt.remaining_to_next, 0.0)
        self.assertEqual(stmt.progress, 100.0)

    def test_03_credit_note_subtraction(self):
        """Test that credit notes posted in the month decrease revenue and adjust bonus."""
        grid = self._create_sample_grid_cliff(self.october_month)
        stmt = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_1.id,
            'company_id': self.company.id,
            'date_month': self.october_month,
            'grid_id': grid.id,
        })

        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 10), 10000.0, 'out_invoice')
        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 15), 1000.0, 'out_refund')

        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 9000.0)
        self.assertEqual(stmt.bonus, 0.0)

    def test_04_progressive_mode_calculation(self):
        """Test Progressive bonus calculations across multiple revenue slices.
        Uses december_month to avoid UNIQUE conflict with test_02's cliff grid on october_month.
        """
        grid = self.env['sales.bonus.grid'].create({
            'company_id': self.company.id,
            'date_month': self.december_month,
            'mode': 'progressive',
            'revenue_basis': 'invoiced',
            'line_ids': [
                (0, 0, {'sequence': 1, 'name': 'Tier 1 (0 to 10k)', 'revenue_from': 0.0, 'bonus_type': 'percent', 'bonus_value': 0.0}),
                (0, 0, {'sequence': 2, 'name': 'Tier 2 (10k to 20k)', 'revenue_from': 10000.0, 'bonus_type': 'percent', 'bonus_value': 5.0}),
                (0, 0, {'sequence': 3, 'name': 'Tier 3 (20k+)', 'revenue_from': 20000.0, 'bonus_type': 'percent', 'bonus_value': 10.0}),
            ]
        })

        stmt = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_1.id,
            'company_id': self.company.id,
            'date_month': self.december_month,
            'grid_id': grid.id,
        })

        self._create_posted_invoice(self.salesperson_1, date(2029, 12, 10), 15000.0)
        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 15000.0)
        self.assertEqual(stmt.bonus, 250.0)

        self._create_posted_invoice(self.salesperson_1, date(2029, 12, 20), 10000.0)
        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 25000.0)
        self.assertEqual(stmt.bonus, 1000.0)

    def test_05_grid_automatic_inheritance(self):
        """Test that November inherits October grid when no grid exists for November."""
        oct_grid = self._create_sample_grid_cliff(self.october_month)

        nov_grid = self.env['sales.bonus.grid'].get_or_create_grid(self.company, self.november_month)

        self.assertTrue(nov_grid)
        self.assertEqual(nov_grid.date_month, self.november_month)
        self.assertEqual(nov_grid.source_grid_id, oct_grid)
        self.assertEqual(len(nov_grid.line_ids), 3)
        self.assertEqual(nov_grid.line_ids[1].bonus_value, 50.0)

        nov_grid.line_ids[1].write({'bonus_value': 75.0})
        self.assertEqual(oct_grid.line_ids[1].bonus_value, 50.0)
        self.assertEqual(nov_grid.line_ids[1].bonus_value, 75.0)

    def test_06_locked_statement_immutability(self):
        """Test that locking a statement freezes figures and prevents auto-recalculation."""
        grid = self._create_sample_grid_cliff(self.october_month)
        stmt = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_1.id,
            'company_id': self.company.id,
            'date_month': self.october_month,
            'grid_id': grid.id,
        })

        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 10), 10000.0)
        stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 10000.0)
        self.assertEqual(stmt.bonus, 50.0)

        stmt.with_user(self.manager_user).action_lock()
        self.assertEqual(stmt.state, 'locked')
        self.assertTrue(stmt.locked_on)
        self.assertEqual(stmt.locked_by, self.manager_user)

        self._create_posted_invoice(self.salesperson_1, date(2029, 10, 25), 10000.0)

        stmt._compute_revenue_and_bonus()
        self.assertEqual(stmt.revenue, 10000.0)
        self.assertEqual(stmt.bonus, 50.0)

    def test_07_security_record_rules(self):
        """Test that salespeople can only see their own statement and managers see all."""
        grid = self._create_sample_grid_cliff(self.october_month)

        stmt_alice = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_1.id,
            'company_id': self.company.id,
            'date_month': self.october_month,
            'grid_id': grid.id,
        })
        stmt_bob = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_2.id,
            'company_id': self.company.id,
            'date_month': self.october_month,
            'grid_id': grid.id,
        })

        alice_stmts = self.env['sales.bonus.statement'].with_user(self.salesperson_1).search([])
        self.assertIn(stmt_alice, alice_stmts)
        self.assertNotIn(stmt_bob, alice_stmts)

        bob_stmts = self.env['sales.bonus.statement'].with_user(self.salesperson_2).search([])
        self.assertIn(stmt_bob, bob_stmts)
        self.assertNotIn(stmt_alice, bob_stmts)

        self.assertTrue(self.manager_user.has_group('sales_team.group_sale_salesman'))

        mgr_stmts = self.env['sales.bonus.statement'].with_user(self.manager_user).search([])
        self.assertIn(stmt_alice, mgr_stmts)
        self.assertIn(stmt_bob, mgr_stmts)

    def test_08_unlock_wizard(self):
        """Test unlocking workflow with mandatory reason logged to chatter."""
        grid = self._create_sample_grid_cliff(self.october_month)
        stmt = self.env['sales.bonus.statement'].create({
            'user_id': self.salesperson_1.id,
            'company_id': self.company.id,
            'date_month': self.october_month,
            'grid_id': grid.id,
        })
        stmt.with_user(self.manager_user).action_lock()
        self.assertEqual(stmt.state, 'locked')

        with self.assertRaises(UserError):
            stmt.with_user(self.salesperson_1).action_unlock()

        wizard = self.env['sales.bonus.unlock.wizard'].with_user(self.manager_user).create({
            'statement_id': stmt.id,
            'reason': 'Customer billing adjustment approved by management.',
        })
        wizard.action_confirm_unlock()

        self.assertEqual(stmt.state, 'open')
        self.assertEqual(stmt.unlock_reason, 'Customer billing adjustment approved by management.')

    def test_09_admin_excluded(self):
        """System administrators never get a bonus statement."""
        current_month = fields.Date.today().replace(day=1)
        self._create_sample_grid_cliff(current_month)
        admin = self.env.ref('base.user_admin')
        Statement = self.env['sales.bonus.statement']

        action = Statement.with_user(admin).action_open_my_bonus()
        self.assertEqual(action['view_mode'], 'list')

        self.company.bonus_auto_refresh = True
        Statement.cron_refresh_open_statements()
        stmts = Statement.search([('company_id', '=', self.company.id), ('date_month', '=', current_month)])
        self.assertNotIn(admin, stmts.user_id)
        self.assertIn(self.salesperson_1, stmts.user_id)
