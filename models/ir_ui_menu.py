# -*- coding: utf-8 -*-
from odoo import models


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _visible_menu_ids(self, debug=False):
        visible_ids = super()._visible_menu_ids(debug)
        if self.env.user._is_system():
            menu = self.env.ref('sales_bonus_grid.menu_sales_bonus_my_bonus', raise_if_not_found=False)
            if menu:
                return visible_ids - {menu.id}
        return visible_ids
