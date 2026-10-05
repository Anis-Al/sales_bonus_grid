# -*- coding: utf-8 -*-
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class SalesBonusGrid(models.Model):
    _name = 'sales.bonus.grid'
    _description = 'Sales Bonus Grid'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_month desc, id desc'

    name = fields.Char(
        string="Grid Name",
        compute='_compute_name',
        store=True,
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
    active = fields.Boolean(
        string="Active",
        default=True,
    )
    date_month = fields.Date(
        string="Month",
        required=True,
        tracking=True,
        default=lambda self: fields.Date.today().replace(day=1),
        index=True,
    )
    source_grid_id = fields.Many2one(
        'sales.bonus.grid',
        string="Inherited From",
        readonly=True,
        tracking=True,
    )
    mode = fields.Selection(
        [
            ('cliff', 'Cliff'),
            ('progressive', 'Progressive'),
        ],
        string="Calculation Mode",
        default='cliff',
        required=True,
        tracking=True,
    )
    revenue_basis = fields.Selection(
        [
            ('invoiced', 'Invoiced (Posted Invoices)'),
            ('paid', 'Paid (Collected Invoices)'),
        ],
        string="Revenue Basis",
        default=lambda self: self.env.company.bonus_default_revenue_basis or 'invoiced',
        required=True,
        tracking=True,
    )
    line_ids = fields.One2many(
        'sales.bonus.grid.line',
        'grid_id',
        string="Bonus Tiers",
        copy=True,
    )
    statement_ids = fields.One2many(
        'sales.bonus.statement',
        'grid_id',
        string="Statements",
    )
    statement_count = fields.Integer(
        string="Statements Count",
        compute='_compute_statement_count',
    )
    is_locked = fields.Boolean(
        string="Is Month Locked",
        compute='_compute_is_locked',
        store=False,
    )

    _unique_company_month = models.Constraint(
        'UNIQUE(company_id, date_month)',
        'Only one bonus grid is allowed per company per month!',
    )

    @api.depends('date_month', 'company_id.name')
    def _compute_name(self):
        for grid in self:
            if grid.date_month:
                month_str = grid.date_month.strftime('%B %Y')
                grid.name = _("Bonus Grid - %(month)s", month=month_str)
            else:
                grid.name = _("New Bonus Grid")

    @api.depends('statement_ids.state')
    def _compute_is_locked(self):
        for grid in self:
            grid.is_locked = bool(grid.statement_ids and any(s.state == 'locked' for s in grid.statement_ids))

    def _is_any_statement_locked(self):
        """Real-time DB check used in write() and unlink() guards.

        _compute_is_locked() drives the UI reactively but may be stale inside the
        same transaction when a statement was just locked and not yet flushed.
        This method always issues a fresh search_count, making it safe to call
        immediately after any ORM write to sales.bonus.statement.
        """
        self.ensure_one()
        return bool(self.env['sales.bonus.statement'].sudo().search_count([
            ('grid_id', '=', self.id),
            ('state', '=', 'locked'),
        ]))

    @api.depends('statement_ids')
    def _compute_statement_count(self):
        for grid in self:
            grid.statement_count = len(grid.statement_ids)

    @api.constrains('date_month')
    def _check_date_month(self):
        for grid in self:
            if grid.date_month and grid.date_month.day != 1:
                raise ValidationError(_("The grid date must always be the 1st day of the month."))

    @api.constrains('line_ids', 'mode')
    def _check_lines(self):
        for grid in self:
            if not grid.line_ids:
                raise ValidationError(_("A bonus grid must contain at least one tier line."))

            sorted_lines = grid.line_ids.sorted(key=lambda l: (l.revenue_from, l.sequence, l.id or 0))

            if sorted_lines[0].revenue_from != 0.0:
                raise ValidationError(_(
                    "The first bonus tier must start at 0.0 revenue (found %(val)s).",
                    val=sorted_lines[0].revenue_from
                ))

            for i in range(len(sorted_lines) - 1):
                curr_tier = sorted_lines[i]
                next_tier = sorted_lines[i + 1]
                if curr_tier.revenue_from >= next_tier.revenue_from:
                    raise ValidationError(_(
                        "Bonus tier thresholds must be strictly ascending with no duplicates. "
                        "Tier '%(curr)s' (%(curr_val)s) is not lower than '%(next)s' (%(next_val)s).",
                        curr=curr_tier.name,
                        curr_val=curr_tier.revenue_from,
                        next=next_tier.name,
                        next_val=next_tier.revenue_from,
                    ))

            if grid.mode == 'progressive':
                non_percent = sorted_lines.filtered(lambda l: l.bonus_type != 'percent')
                if non_percent:
                    raise ValidationError(_(
                        "In Progressive calculation mode, all bonus tiers must use 'Percentage (%%)' bonus type."
                    ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'date_month' in vals and vals['date_month']:
                dt = fields.Date.to_date(vals['date_month'])
                vals['date_month'] = dt.replace(day=1)
        return super().create(vals_list)

    def write(self, vals):
        for grid in self:
            if grid._is_any_statement_locked() and not self.env.context.get('bypass_lock_check'):
                restricted_fields = {'mode', 'revenue_basis', 'date_month', 'company_id', 'line_ids'}
                if any(f in vals for f in restricted_fields):
                    raise UserError(_(
                        "Cannot modify the bonus grid for %(month)s because it is locked. "
                        "An administrator must unlock the relevant statements first.",
                        month=grid.date_month.strftime('%B %Y')
                    ))
        if 'date_month' in vals and vals['date_month']:
            dt = fields.Date.to_date(vals['date_month'])
            vals['date_month'] = dt.replace(day=1)
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_locked(self):
        for grid in self:
            if grid._is_any_statement_locked():
                raise UserError(_(
                    "Cannot delete locked bonus grid for %(month)s.",
                    month=grid.date_month.strftime('%B %Y')
                ))

    def copy_grid_for_month(self, target_date, company_id=None):
        self.ensure_one()
        company = company_id or self.company_id
        target_month = fields.Date.to_date(target_date).replace(day=1)

        existing = self.search([
            ('company_id', '=', company.id),
            ('date_month', '=', target_month)
        ], limit=1)
        if existing:
            return existing

        lines_commands = []
        for line in self.line_ids.sorted(key=lambda l: l.revenue_from):
            lines_commands.append((0, 0, {
                'sequence': line.sequence,
                'name': line.name,
                'revenue_from': line.revenue_from,
                'bonus_type': line.bonus_type,
                'bonus_value': line.bonus_value,
            }))

        new_grid = self.create({
            'company_id': company.id,
            'date_month': target_month,
            'source_grid_id': self.id,
            'mode': self.mode,
            'revenue_basis': self.revenue_basis,
            'line_ids': lines_commands,
        })
        new_grid.message_post(
            body=_("Grid automatically created for %(month)s by copying previous grid '%(source)s'.",
                   month=target_month.strftime('%B %Y'),
                   source=self.name)
        )
        return new_grid

    @api.model
    def get_or_create_grid(self, company, target_date):
        month_start = fields.Date.to_date(target_date).replace(day=1)
        grid = self.search([
            ('company_id', '=', company.id),
            ('date_month', '=', month_start),
        ], limit=1)
        if grid:
            return grid

        previous_grid = self.search([
            ('company_id', '=', company.id),
            ('date_month', '<', month_start),
            ('active', '=', True),
        ], order='date_month desc', limit=1)

        if previous_grid:
            return previous_grid.copy_grid_for_month(month_start, company_id=company)

        return self.browse()

    @api.model
    def cron_ensure_monthly_grids(self):
        today = fields.Date.today().replace(day=1)
        companies = self.env['res.company'].search([])
        for company in companies:
            self.get_or_create_grid(company, today)

    def action_view_statements(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sales_bonus_grid.action_sales_bonus_statement_manager")
        action['domain'] = [('grid_id', '=', self.id)]
        action['context'] = {'default_grid_id': self.id, 'default_company_id': self.company_id.id}
        return action
