from odoo import api, fields, models, _
import math
from datetime import datetime, time, timedelta


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    response_delay_hours = fields.Integer(compute="_compute_response_delay")
    response_delay_days = fields.Integer(compute="_compute_response_delay")
    first_response = fields.Datetime(readonly=False)

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, **kwargs):
        print(kwargs)
        if kwargs.get("subtype_id") == 1 and kwargs.get("message_type") == "comment" and not self.first_response:
            self.first_response = datetime.now()
        return super().message_post(**kwargs)

    @classmethod
    def __float_to_time(cls, hours_float):
        hours, remainder = divmod(hours_float, 1)
        minutes = int(remainder * 60)

        return time(int(hours), minutes)

    def __get_workday_periods(self, dt=None, weekday=1):
        default_working_hours = self.env.company.resource_calendar_id.attendance_ids
        while str(dt.weekday()) not in default_working_hours.mapped("dayofweek"):
            dt += timedelta(days=1)
        
        workday_morning = default_working_hours.filtered(lambda obj: obj.dayofweek == str(dt.weekday() or weekday) and obj.day_period == "morning")
        workday_afternoon = default_working_hours.filtered(lambda obj: obj.dayofweek == str(dt.weekday() or weekday) and obj.day_period == "afternoon")
        
        return workday_morning, workday_afternoon

    def __get_datetime_in_working_hours(self, dt, workday_morning, workday_afternoon):
        default_working_hours = self.env.company.resource_calendar_id.attendance_ids
        while str(dt.weekday()) not in default_working_hours.mapped("dayofweek"):
            dt += timedelta(days=1)

        time_morning_hour_from = self.__float_to_time(workday_morning.hour_from)
        time_morning_hour_to = self.__float_to_time(workday_morning.hour_to)
        time_afternoon_hour_from = self.__float_to_time(workday_afternoon.hour_from)
        time_afternoon_hour_to = self.__float_to_time(workday_afternoon.hour_to)
        utc_offset = 3

        dt_time = (dt + timedelta(hours=utc_offset)).time()

        # case: in working hours
        if time_morning_hour_from <= dt_time <= time_morning_hour_to:
            return datetime.combine(dt.date(), dt_time), "morning"
        elif time_afternoon_hour_from <= dt_time <= time_afternoon_hour_to:
            return datetime.combine(dt.date(), dt_time), "afternoon"
        # case: before day start working hour
        elif dt_time <= time_morning_hour_from:
            return datetime.combine(dt.date(), time_morning_hour_from), "morning"
        # case: after day end working hour
        elif dt_time >= time_afternoon_hour_to:
            return datetime.combine(dt.date(), time_morning_hour_from), "morning"
        # case: between two periods break
        elif dt_time >= time_morning_hour_to:
            return datetime.combine(dt.date(), time_afternoon_hour_from), "afternoon"

    def __get_delta_to_period(self, periods, dt, period_str, is_response=False):
        period = periods[0] if period_str == "morning" else periods[1]
        if is_response:
            end_time = self.__float_to_time(period.hour_from)
            return dt - datetime.combine(dt.date(), end_time)
        end_time = self.__float_to_time(period.hour_to)
        return datetime.combine(dt.date(), end_time) - dt

    def __get_delta_to_2_periods(self, periods, dt, period_str, is_response=False):
        hours = self.__get_delta_to_period(periods, dt, period_str, is_response)
        if period_str == "morning":
            start_time = self.__float_to_time(periods[1].hour_from)
            period_2nd_date = datetime.combine(dt.date(), start_time)
            hours += self.__get_delta_to_period(periods, period_2nd_date, "afternoon", is_response)

        return hours

    def __count_working_hours_per_period(self, period):
        period_hour_from = datetime.combine(datetime.today(), self.__float_to_time(period.hour_from))
        period_hour_to = datetime.combine(datetime.today(), self.__float_to_time(period.hour_to))
        time_delta = period_hour_to - period_hour_from
        return time_delta

    def __count_working_hours_per_day(self, dt):
        morning, afternoon = self.__get_workday_periods(dt=dt)
        if morning and afternoon:
            return (self.__count_working_hours_per_period(morning) +
                    self.__count_working_hours_per_period(afternoon))
        elif morning:
            return self.__count_working_hours_per_period(morning)
        elif afternoon:
            return self.__count_working_hours_per_period(afternoon)
        else:
            return timedelta(hours=0)

    def __count_working_hours_per_middle_days(self, create_dt, first_response_dt):
        create_date = create_dt.date()
        first_response_date = first_response_dt.date()
        days = (first_response_date - create_date).days - 1
        hours = timedelta(hours=0)
        for num in range(days):
            create_date += timedelta(days=1)
            hours += self.__count_working_hours_per_day(create_date)

        return hours

    def __get_response_delay_hours(self):
        workday_create_datetime_periods = self.__get_workday_periods(self.create_date)
        # working_hours_per_day = self.__count_working_hours_per_day()
        workday_first_response_datetime_periods = self.__get_workday_periods(self.first_response)
        create_datetime = self.__get_datetime_in_working_hours(self.create_date, *workday_create_datetime_periods)
        first_response_datetime = self.__get_datetime_in_working_hours(self.first_response, *workday_first_response_datetime_periods)

        is_same_day = first_response_datetime[0].date() == create_datetime[0].date()
        is_same_period = first_response_datetime[1] == create_datetime[1]

        print(first_response_datetime[0] , create_datetime[0])

        time_delta = None

        if is_same_day and is_same_period:
            time_delta = first_response_datetime[0] - create_datetime[0]
        elif is_same_day:
            create_datetime_hours = self.__get_delta_to_period(workday_create_datetime_periods, *create_datetime)
            first_response_datetime_hours = self.__get_delta_to_period(workday_first_response_datetime_periods, is_response=True, *first_response_datetime)
            time_delta = create_datetime_hours + first_response_datetime_hours
        else:
            create_datetime_hours = self.__get_delta_to_2_periods(workday_create_datetime_periods, *create_datetime)
            first_response_datetime_hours = self.__get_delta_to_2_periods(workday_first_response_datetime_periods, is_response=True, *first_response_datetime)
            time_delta = create_datetime_hours + first_response_datetime_hours
            time_delta_middle_days = self.__count_working_hours_per_middle_days(create_datetime[0], first_response_datetime[0])
            time_delta += time_delta_middle_days

        if not time_delta:
            return 0
        return math.ceil(time_delta.total_seconds() / 3600)

    @api.depends("create_date", "first_response")
    def _compute_response_delay(self):
        # self.ensure_one()
        for order in self:
            if order.first_response:
                response_delay_hours = self.__get_response_delay_hours()
                order.response_delay_hours = response_delay_hours
                order.response_delay_days = math.ceil(response_delay_hours / 24)
            else:
                order.response_delay_hours = 0
                order.response_delay_days = 0
            