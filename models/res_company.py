# -*- coding: utf-8 -*-
from odoo import fields, models, api
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    bonus_lock_day = fields.Integer(
        string="Bonus Lock Day of Month",
        default=5,
        help="Day of the following month on which open bonus statements are automatically locked (1-28)."
    )
    bonus_auto_refresh = fields.Boolean(
        string="Auto Refresh Open Statements",
        default=True,
        help="Enable hourly background refresh for open monthly bonus statements."
    )
    bonus_default_revenue_basis = fields.Selection(
        [
            ('invoiced', 'Invoiced (Posted Invoices)'),
            ('paid', 'Paid (Collected Invoices)'),
        ],
        string="Default Revenue Basis",
        default='invoiced',
        required=True,
        help="Default revenue basis used when creating new monthly bonus grids."
    )
    bonus_default_mode = fields.Selection(
        [
            ('cliff', 'Cliff'),
            ('progressive', 'Progressive'),
        ],
        string="Default Calculation Mode",
        default='cliff',
        required=True,
        help="Default calculation mode used when creating new monthly bonus grids."
    )

    @api.constrains('bonus_lock_day')
    def _check_bonus_lock_day(self):
        for company in self:
            if company.bonus_lock_day < 1 or company.bonus_lock_day > 28:
                raise ValidationError("Bonus lock day must be between 1 and 28.")
