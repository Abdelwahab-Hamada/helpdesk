from odoo import api, fields, models, _
import math


class HelpTicket(models.Model):
    _inherit = 'help.ticket'

    response_delay_hours = fields.Integer(compute="_compute_response_delay")
    response_delay_days = fields.Integer(compute="_compute_response_delay")
    first_response = fields.Datetime(readonly=False)

    def __get_response_delay_hours(self):
        time_delta = self.first_response - self.create_date
        return time_delta.total_seconds() // 3600

    @api.depends("create_date", "first_response")
    def _compute_response_delay(self):
        # self.ensure_one()
        for ticket in self:
            if ticket.first_response:
                response_delay_hours = self.__get_response_delay_hours()
                ticket.response_delay_hours = response_delay_hours
                ticket.response_delay_days = math.ceil(response_delay_hours / 24)
            else:
                ticket.response_delay_hours = 0
                ticket.response_delay_days = 0
            