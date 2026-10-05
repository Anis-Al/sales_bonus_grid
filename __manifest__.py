# -*- coding: utf-8 -*-
{
    'name': "Sales Bonus Tracker",
    'summary': "Monthly revenue bonus grid, tier tracking and live commission visibility for sales teams",
    'description': """
    """,
    'version': '19.0.1.0.0',
    'category': 'Sales/Sales',
    'author': "Anis Alim",
    'license': 'LGPL-3',
    'depends': [
        'base',
        'sale',
        'sales_team',
        'account',
        'mail',
        'year_month_widget',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/sales_bonus_security.xml',
        'data/ir_cron_data.xml',
        'wizard/sales_bonus_unlock_wizard_views.xml',
        'views/sales_bonus_grid_views.xml',
        'views/sales_bonus_statement_views.xml',
        'views/res_config_settings_views.xml',
        'views/sales_bonus_menus.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'sales_bonus_grid/static/src/**/*',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
