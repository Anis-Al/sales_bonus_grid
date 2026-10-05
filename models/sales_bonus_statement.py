# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class SalesBonusStatement(models.Model):
    _name = 'sales.bonus.statement'
    _description = 'Sales Bonus Statement'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_month desc, user_id asc, id desc'

    name = fields.Char(
        string="Statement Reference",
        compute='_compute_name',
        store=True,
        tracking=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string="Salesperson",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string="Company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string="Currency",
        readonly=True,
    )
    date_month = fields.Date(
        string="Statement Month",
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
        index=True,
        tracking=True,
    )
    grid_id = fields.Many2one(
        'sales.bonus.grid',
        string="Bonus Grid",
        required=True,
        ondelete='restrict',
        index=True,
        domain="[('company_id', '=', company_id), ('date_month', '=', date_month)]",
    )
    grid_line_ids = fields.One2many(
        related='grid_id.line_ids',
        string="Grid Tiers",
    )
    grid_mode = fields.Selection(
        related='grid_id.mode',
        string="Grid Mode",
        readonly=True,
    )
    grid_revenue_basis = fields.Selection(
        related='grid_id.revenue_basis',
        string="Revenue Basis",
        readonly=True,
    )
    state = fields.Selection(
        [
            ('open', 'Open'),
            ('locked', 'Locked'),
        ],
        string="Status",
        default='open',
        required=True,
        tracking=True,
        index=True,
    )
    revenue = fields.Monetary(
        string="Store Revenue",
        compute='_compute_revenue_and_bonus',
        store=True,
        tracking=True,
        currency_field='currency_id',
    )
    bonus = fields.Monetary(
        string="Earned Bonus",
        compute='_compute_revenue_and_bonus',
        store=True,
        tracking=True,
        currency_field='currency_id',
    )
    current_line_id = fields.Many2one(
        'sales.bonus.grid.line',
        string="Current Tier",
        compute='_compute_revenue_and_bonus',
        store=True,
    )
    next_line_id = fields.Many2one(
        'sales.bonus.grid.line',
        string="Next Tier",
        compute='_compute_revenue_and_bonus',
        store=True,
    )
    remaining_to_next = fields.Monetary(
        string="Remaining to Next Tier",
        compute='_compute_revenue_and_bonus',
        store=True,
        currency_field='currency_id',
    )
    next_bonus = fields.Monetary(
        string="Next Tier Bonus",
        compute='_compute_revenue_and_bonus',
        store=True,
        currency_field='currency_id',
    )
    progress = fields.Float(
        string="Progress to Next Tier (%)",
        compute='_compute_revenue_and_bonus',
        store=True,
        digits=(5, 2),
    )
    progress_caption = fields.Char(
        string="Progress Description",
        compute='_compute_progress_caption',
    )
    last_refresh = fields.Datetime(
        string="Last Refreshed",
        default=fields.Datetime.now,
        readonly=True,
    )
    locked_on = fields.Datetime(
        string="Locked On",
        readonly=True,
        copy=False,
    )
    locked_by = fields.Many2one(
        'res.users',
        string="Locked By",
        readonly=True,
        copy=False,
    )
    unlock_reason = fields.Text(
        string="Unlock Reason",
        readonly=True,
        copy=False,
    )
    late_credit_note_warning = fields.Text(
        string="Late Credit Notes Notice",
        compute='_compute_late_credit_notes',
    )
    invoice_count = fields.Integer(
        string="Invoices Count",
        compute='_compute_invoice_count',
    )
    is_manager = fields.Boolean(
        string="Is Sales Manager",
        compute='_compute_is_manager',
    )

    _unique_user_month_company = models.Constraint(
        'UNIQUE(user_id, company_id, date_month)',
        'A salesperson can only have one bonus statement per company per month!',
    )

    @api.depends('user_id.name', 'date_month')
    def _compute_name(self):
        for rec in self:
            if rec.user_id and rec.date_month:
                month_str = rec.date_month.strftime('%B %Y')
                rec.name = _("Bonus Statement - %(user)s - %(month)s", user=rec.user_id.name, month=month_str)
            else:
                rec.name = _("New Bonus Statement")

    @api.depends_context('uid')
    def _compute_is_manager(self):
        is_mgr = self.env.user.has_group('sales_team.group_sale_manager')
        for rec in self:
            rec.is_manager = is_mgr

    @api.depends('company_id', 'date_month', 'grid_id.revenue_basis')
    def _compute_invoice_count(self):
        for rec in self:
            if not rec.company_id or not rec.date_month:
                rec.invoice_count = 0
                continue
            domain = rec._get_invoices_domain()
            rec.invoice_count = self.env['account.move'].search_count(domain)

    def _get_invoices_domain(self):
        self.ensure_one()
        month_start = self.date_month.replace(day=1)
        month_end = month_start + relativedelta(months=1, days=-1)
        domain = [
            ('move_type', 'in', ('out_invoice', 'out_refund')),
            ('state', '=', 'posted'),
            ('company_id', '=', self.company_id.id),
            ('invoice_date', '>=', month_start),
            ('invoice_date', '<=', month_end),
        ]
        if self.grid_id and self.grid_id.revenue_basis == 'paid':
            domain.append(('payment_state', 'in', ('paid', 'in_payment')))
        return domain

    @api.depends('user_id', 'company_id', 'date_month', 'grid_id', 'grid_id.line_ids', 'grid_id.mode', 'grid_id.revenue_basis')
    def _compute_revenue_and_bonus(self):
        for rec in self:
            if rec.state == 'locked' and not self.env.context.get('force_recompute'):
                continue

            if not rec.user_id or not rec.date_month or not rec.grid_id or not rec.grid_id.line_ids:
                rec.revenue = 0.0
                rec.bonus = 0.0
                rec.current_line_id = False
                rec.next_line_id = False
                rec.remaining_to_next = 0.0
                rec.next_bonus = 0.0
                rec.progress = 0.0
                continue

            domain = rec._get_invoices_domain()
            res = self.env['account.move']._read_group(
                domain,
                groupby=[],
                aggregates=['amount_untaxed_signed:sum']
            )
            total_rev = res[0][0] if (res and res[0] and res[0][0] is not None) else 0.0

            bonus_data = rec._calculate_bonus(total_rev, rec.grid_id)

            rec.revenue = total_rev
            rec.bonus = bonus_data['bonus']
            rec.current_line_id = bonus_data['current_line_id']
            rec.next_line_id = bonus_data['next_line_id']
            rec.remaining_to_next = bonus_data['remaining_to_next']
            rec.next_bonus = bonus_data['next_bonus']
            rec.progress = bonus_data['progress']

    def _calculate_bonus(self, revenue, grid):
        lines = grid.line_ids.sorted(key=lambda l: (l.revenue_from, l.sequence, l.id or 0))
        if not lines:
            return {
                'bonus': 0.0,
                'current_line_id': False,
                'next_line_id': False,
                'remaining_to_next': 0.0,
                'next_bonus': 0.0,
                'progress': 0.0,
            }

        eff_rev = max(0.0, revenue)

        current_idx = max(
            (i for i, l in enumerate(lines) if l.revenue_from <= eff_rev),
            default=0
        )

        current_line = lines[current_idx]
        next_line = lines[current_idx + 1] if (current_idx + 1 < len(lines)) else False

        if grid.mode == 'cliff':
            if current_line.bonus_type == 'fixed':
                earned_bonus = current_line.bonus_value
            else:
                earned_bonus = eff_rev * (current_line.bonus_value / 100.0)

            if next_line:
                next_rev_target = next_line.revenue_from
                if next_line.bonus_type == 'fixed':
                    next_bonus_val = next_line.bonus_value
                else:
                    next_bonus_val = next_rev_target * (next_line.bonus_value / 100.0)
            else:
                next_bonus_val = earned_bonus

        else:
            earned_bonus = 0.0
            for i, line in enumerate(lines):
                lower = line.revenue_from
                upper = lines[i + 1].revenue_from if (i + 1 < len(lines)) else float('inf')

                if eff_rev > lower:
                    slice_amount = min(eff_rev, upper) - lower
                    if line.bonus_type == 'percent':
                        earned_bonus += slice_amount * (line.bonus_value / 100.0)
                    else:
                        earned_bonus += line.bonus_value

            if next_line:
                next_rev_target = next_line.revenue_from
                next_bonus_val = 0.0
                for i, line in enumerate(lines):
                    lower = line.revenue_from
                    upper = lines[i + 1].revenue_from if (i + 1 < len(lines)) else float('inf')
                    if next_rev_target > lower:
                        slice_amount = min(next_rev_target, upper) - lower
                        if line.bonus_type == 'percent':
                            next_bonus_val += slice_amount * (line.bonus_value / 100.0)
                        else:
                            next_bonus_val += line.bonus_value
            else:
                next_bonus_val = earned_bonus

        if next_line:
            remaining = max(0.0, next_line.revenue_from - eff_rev)
            span = next_line.revenue_from - current_line.revenue_from
            if span > 0:
                progress_val = min(100.0, max(0.0, ((eff_rev - current_line.revenue_from) / span) * 100.0))
            else:
                progress_val = 100.0
        else:
            remaining = 0.0
            progress_val = 100.0

        return {
            'bonus': earned_bonus,
            'current_line_id': current_line,
            'next_line_id': next_line,
            'remaining_to_next': remaining,
            'next_bonus': next_bonus_val,
            'progress': round(progress_val, 2),
        }

    @api.depends('next_line_id', 'remaining_to_next', 'bonus', 'next_bonus', 'currency_id.symbol', 'currency_id.position')
    def _compute_progress_caption(self):
        for rec in self:
            if not rec.next_line_id:
                rec.progress_caption = _("Top tier reached! Maximum bonus achieved.")
            else:
                curr = rec.currency_id
                def format_curr(amt):
                    formatted = f"{amt:,.2f}"
                    if curr and curr.position == 'before':
                        return f"{curr.symbol} {formatted}"
                    elif curr:
                        return f"{formatted} {curr.symbol}"
                    return formatted

                rem_str = format_curr(rec.remaining_to_next)
                curr_bonus_str = format_curr(rec.bonus)
                next_bonus_str = format_curr(rec.next_bonus)
                tier_name = rec.next_line_id.name

                rec.progress_caption = _(
                    "%(remaining)s more to reach %(tier)s — bonus goes from %(current_bonus)s to %(next_bonus)s",
                    remaining=rem_str,
                    tier=tier_name,
                    current_bonus=curr_bonus_str,
                    next_bonus=next_bonus_str,
                )

    @api.depends('user_id', 'company_id', 'date_month')
    def _compute_late_credit_notes(self):
        for rec in self:
            if not rec.user_id or not rec.company_id:
                rec.late_credit_note_warning = False
                continue

            past_locked = self.search([
                ('user_id', '=', rec.user_id.id),
                ('company_id', '=', rec.company_id.id),
                ('date_month', '<', rec.date_month),
                ('state', '=', 'locked'),
                ('locked_on', '!=', False),
            ])

            warnings = []
            if past_locked:
                min_start = min(s.date_month for s in past_locked)
                max_end = max(s.date_month + relativedelta(months=1, days=-1) for s in past_locked)
                all_refunds = self.env['account.move'].search_read(
                    [
                        ('move_type', '=', 'out_refund'),
                        ('state', '=', 'posted'),
                        ('company_id', '=', rec.company_id.id),
                        ('invoice_date', '>=', min_start),
                        ('invoice_date', '<=', max_end),
                    ],
                    fields=['invoice_date', 'amount_untaxed_signed', 'create_date'],
                )

                curr = rec.currency_id
                for stmt in past_locked:
                    m_start = stmt.date_month
                    m_end = m_start + relativedelta(months=1, days=-1)
                    late = [
                        r for r in all_refunds
                        if m_start <= r['invoice_date'] <= m_end
                        and r['create_date'] > stmt.locked_on
                    ]
                    if late:
                        refund_total = sum(abs(r['amount_untaxed_signed']) for r in late)
                        month_label = stmt.date_month.strftime('%B %Y')
                        total_str = f"{refund_total:,.2f} {curr.symbol if curr else ''}"
                        warnings.append(_(
                            "%(count)d late credit note(s) totaling %(total)s were posted for locked month %(month)s after lock date.",
                            count=len(late),
                            total=total_str,
                            month=month_label,
                        ))

            rec.late_credit_note_warning = "\n".join(warnings) if warnings else False

    @api.constrains('date_month')
    def _check_date_month(self):
        for rec in self:
            if rec.date_month and rec.date_month.day != 1:
                raise ValidationError(_("Statement date must always be the 1st day of the month."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'date_month' in vals and vals['date_month']:
                dt = fields.Date.to_date(vals['date_month'])
                vals['date_month'] = dt.replace(day=1)
            if not vals.get('grid_id') and vals.get('company_id') and vals.get('date_month'):
                company = self.env['res.company'].browse(vals['company_id'])
                grid = self.env['sales.bonus.grid'].get_or_create_grid(company, vals['date_month'])
                if grid:
                    vals['grid_id'] = grid.id
        return super().create(vals_list)

    def write(self, vals):
        if 'date_month' in vals and vals['date_month']:
            dt = fields.Date.to_date(vals['date_month'])
            vals['date_month'] = dt.replace(day=1)
        return super().write(vals)

    def action_refresh(self):
        self.ensure_one()
        if self.state == 'locked':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Statement Locked"),
                    'message': _("This statement is locked and cannot be refreshed automatically."),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        self.with_context(force_recompute=True)._compute_revenue_and_bonus()
        self.last_refresh = fields.Datetime.now()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Refreshed"),
                'message': _("Bonus statement updated with latest invoice figures."),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_lock(self):
        for rec in self:
            if not self.env.user.has_group('sales_team.group_sale_manager'):
                raise UserError(_("Only sales managers can lock bonus statements."))
            rec.write({
                'state': 'locked',
                'locked_on': fields.Datetime.now(),
                'locked_by': self.env.user.id,
            })
            rec.message_post(
                body=_("Statement locked by %(user)s on %(date)s. Revenue: %(rev)s, Bonus: %(bonus)s",
                       user=self.env.user.name,
                       date=fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                       rev=f"{rec.revenue:,.2f} {rec.currency_id.symbol or ''}",
                       bonus=f"{rec.bonus:,.2f} {rec.currency_id.symbol or ''}")
            )
        return True

    def action_unlock(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only sales managers can unlock bonus statements."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Unlock Bonus Statement"),
            'res_model': 'sales.bonus.unlock.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_statement_id': self.id,
            }
        }

    def action_view_invoices(self):
        self.ensure_one()
        domain = self._get_invoices_domain()
        action = {
            'name': _("Store Invoices (%(month)s)",
                      month=self.date_month.strftime('%B %Y')),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': domain,
            'context': {
                'default_move_type': 'out_invoice',
                'default_company_id': self.company_id.id,
            }
        }
        return action

    @api.model
    def action_open_my_bonus(self):
        today = fields.Date.today()
        current_month = today.replace(day=1)
        user = self.env.user
        company = self.env.company

        statement = self.search([
            ('user_id', '=', user.id),
            ('company_id', '=', company.id),
            ('date_month', '=', current_month),
        ], limit=1)

        if not statement:
            grid = not user._is_system() and self.env['sales.bonus.grid'].get_or_create_grid(company, current_month)
            if not grid:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _("My Bonus"),
                    'res_model': 'sales.bonus.statement',
                    'view_mode': 'list',
                    'views': [(self.env.ref('sales_bonus_grid.view_sales_bonus_statement_empty_list').id, 'list')],
                    'domain': [('id', '=', False)],
                    'target': 'current',
                    'help': '<p class="o_view_nocontent_empty_folder">%s</p>' % _("No bonus available yet"),
                }

            statement = self.sudo().create({
                'user_id': user.id,
                'company_id': company.id,
                'date_month': current_month,
                'grid_id': grid.id,
            })

        view_id = self.env.ref('sales_bonus_grid.view_sales_bonus_statement_my_bonus_form').id
        return {
            'type': 'ir.actions.act_window',
            'name': _("My Bonus"),
            'res_model': 'sales.bonus.statement',
            'view_mode': 'form',
            'res_id': statement.id,
            'views': [(view_id, 'form')],
            'target': 'current',
        }

    @api.model
    def cron_refresh_open_statements(self):
        today = fields.Date.today()
        current_month = today.replace(day=1)
        companies = self.env['res.company'].search([('bonus_auto_refresh', '=', True)])

        for company in companies:
            grid = self.env['sales.bonus.grid'].get_or_create_grid(company, current_month)
            if not grid:
                continue

            salespeople = self.env['res.users'].search([
                ('company_ids', 'in', company.id),
                ('active', '=', True),
                '|',
                ('sale_team_id', '!=', False),
                ('group_ids', 'in', self.env.ref('sales_team.group_sale_salesman').id)
            ])

            invoice_users = self.env['account.move']._read_group([
                ('move_type', 'in', ('out_invoice', 'out_refund')),
                ('state', '=', 'posted'),
                ('company_id', '=', company.id),
                ('invoice_date', '>=', current_month),
                ('invoice_date', '<=', current_month + relativedelta(months=1, days=-1)),
                ('invoice_user_id', '!=', False),
            ], groupby=['invoice_user_id'])
            inv_user_ids = [u[0].id for u in invoice_users if u[0]]
            all_users = (salespeople | self.env['res.users'].browse(inv_user_ids)).filtered(lambda u: u.active and not u._is_system())

            for user in all_users:
                stmt = self.search([
                    ('user_id', '=', user.id),
                    ('company_id', '=', company.id),
                    ('date_month', '=', current_month),
                ], limit=1)
                if not stmt:
                    stmt = self.sudo().create({
                        'user_id': user.id,
                        'company_id': company.id,
                        'date_month': current_month,
                        'grid_id': grid.id,
                    })
                elif stmt.state == 'open':
                    stmt.with_context(force_recompute=True)._compute_revenue_and_bonus()
                    stmt.last_refresh = fields.Datetime.now()

    @api.model
    def cron_lock_closed_months(self):
        today = fields.Date.today()
        current_month = today.replace(day=1)
        companies = self.env['res.company'].search([])

        for company in companies:
            lock_day = company.bonus_lock_day or 5
            if today.day >= lock_day:
                prev_month = current_month - relativedelta(months=1)
                open_stmts = self.search([
                    ('company_id', '=', company.id),
                    ('date_month', '<=', prev_month),
                    ('state', '=', 'open'),
                ])
                for stmt in open_stmts:
                    stmt.write({
                        'state': 'locked',
                        'locked_on': fields.Datetime.now(),
                        'locked_by': self.env.ref('base.user_root').id,
                    })
                    stmt.message_post(
                        body=_("Automatically locked by scheduled closing job on %(date)s.",
                               date=fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
                    )
