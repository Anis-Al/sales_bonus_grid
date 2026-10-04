# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    bonus_lock_day = fields.Integer(
        related='company_id.bonus_lock_day',
        readonly=False,
        string="Statement Lock Day",
        help="Day of month to freeze and lock statements from the previous month."
    )
    bonus_auto_refresh = fields.Boolean(
        related='company_id.bonus_auto_refresh',
        readonly=False,
        string="Auto Refresh Statements",
        help="Automatically recalculate open statements every hour."
    )
    bonus_default_revenue_basis = fields.Selection(
        related='company_id.bonus_default_revenue_basis',
        readonly=False,
        string="Default Revenue Basis",
        help="Default revenue basis for newly generated bonus grids."
    )
    bonus_default_mode = fields.Selection(
        related='company_id.bonus_default_mode',
        readonly=False,
        string="Default Calculation Mode",
        help="Default mode (Cliff or Progressive) for newly generated bonus grids."
    )
