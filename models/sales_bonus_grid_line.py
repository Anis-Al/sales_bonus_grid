# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class SalesBonusGridLine(models.Model):
    _name = 'sales.bonus.grid.line'
    _description = 'Sales Bonus Grid Tier Line'
    _order = 'revenue_from asc, sequence asc, id asc'

    grid_id = fields.Many2one(
        'sales.bonus.grid',
        string="Bonus Grid",
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        related='grid_id.company_id',
        string="Company",
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='grid_id.currency_id',
        string="Currency",
        store=True,
        readonly=True,
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )
    name = fields.Char(
        string="Tier Label",
        required=True,
    )
    revenue_from = fields.Monetary(
        string="Revenue Threshold",
        default=0.0,
        required=True,
        currency_field='currency_id',
    )
    revenue_to = fields.Monetary(
        string="Upper Bound",
        compute='_compute_revenue_to',
        currency_field='currency_id',
    )
    bonus_type = fields.Selection(
        [
            ('fixed', 'Fixed Amount'),
            ('percent', 'Percentage (%)'),
        ],
        string="Bonus Type",
        default='fixed',
        required=True,
    )
    bonus_value = fields.Monetary(
        string="Bonus Amount",
        default=0.0,
        required=True,
        currency_field='currency_id',
    )

    @api.depends('revenue_from', 'grid_id.line_ids.revenue_from')
    def _compute_revenue_to(self):
        for line in self:
            if not line.grid_id:
                line.revenue_to = 0.0
                continue
            all_lines = line.grid_id.line_ids.sorted(key=lambda l: l.revenue_from)
            higher_lines = all_lines.filtered(lambda l: l.revenue_from > line.revenue_from)
            if higher_lines:
                line.revenue_to = higher_lines[0].revenue_from
            else:
                line.revenue_to = 0.0



    @api.constrains('bonus_value')
    def _check_bonus_value(self):
        for line in self:
            if line.bonus_value < 0.0:
                raise ValidationError(_("Bonus value cannot be negative."))
            if line.bonus_type == 'percent' and line.bonus_value > 100.0:
                raise ValidationError(_("Bonus percentage cannot exceed 100%."))

    @api.constrains('revenue_from')
    def _check_revenue_from(self):
        for line in self:
            if line.revenue_from < 0.0:
                raise ValidationError(_("Revenue threshold cannot be negative."))

    def write(self, vals):
        for line in self:
            if line.grid_id and line.grid_id.is_locked and not self.env.context.get('bypass_lock_check'):
                raise UserError(_(
                    "Cannot modify tier lines of locked bonus grid '%(grid)s'.",
                    grid=line.grid_id.name
                ))
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_if_not_locked(self):
        for line in self:
            if line.grid_id and line.grid_id.is_locked and not self.env.context.get('bypass_lock_check'):
                raise UserError(_(
                    "Cannot delete tier lines from locked bonus grid '%(grid)s'.",
                    grid=line.grid_id.name
                ))
