# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class SalesBonusUnlockWizard(models.TransientModel):
    _name = 'sales.bonus.unlock.wizard'
    _description = 'Unlock Bonus Statement Wizard'

    statement_id = fields.Many2one(
        'sales.bonus.statement',
        string="Statement",
        required=True,
        readonly=True,
    )
    salesperson_name = fields.Char(
        related='statement_id.user_id.name',
        string="Salesperson",
        readonly=True,
    )
    date_month = fields.Date(
        related='statement_id.date_month',
        string="Month",
        readonly=True,
    )
    reason = fields.Text(
        string="Mandatory Reason for Unlocking",
        required=True,
        help="Please explain why this locked monthly statement needs to be reopened."
    )

    def action_confirm_unlock(self):
        self.ensure_one()
        if not self.env.user.has_group('sales_team.group_sale_manager'):
            raise UserError(_("Only sales managers can unlock bonus statements."))

        if not self.reason or not self.reason.strip():
            raise ValidationError(_("A valid reason is required to unlock a closed bonus statement."))

        statement = self.statement_id
        statement.write({
            'state': 'open',
            'unlock_reason': self.reason.strip(),
        })

        statement.message_post(
            body=_(
                "<b>Statement Unlocked</b> by %(user)s on %(date)s.<br/><b>Reason:</b> %(reason)s",
                user=self.env.user.name,
                date=fields.Datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                reason=self.reason.strip()
            )
        )

        # Trigger recomputation to sync with any changes
        statement.with_context(force_recompute=True)._compute_revenue_and_bonus()
        statement.last_refresh = fields.Datetime.now()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Statement Unlocked"),
                'message': _("Statement reopened successfully and figures recomputed."),
                'type': 'success',
                'sticky': False,
            }
        }
