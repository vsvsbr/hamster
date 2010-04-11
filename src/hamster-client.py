#!/usr/bin/env python
# - coding: utf-8 -

# Copyright (C) 2010 Matías Ribecky <matias at mribecky.com.ar>
# Copyright (C) 2010 Toms Bauģis <toms.baugis@gmail.com>

# This file is part of Project Hamster.

# Project Hamster is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Project Hamster is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Project Hamster.  If not, see <http://www.gnu.org/licenses/>.

'''A script to control the applet from the command line.'''

import sys, os
import optparse
import re
import locale, gettext
import time
import datetime as dt

import dbus
import dbus.mainloop.glib

from hamster import defs, stuff

HAMSTER_SERVICE = 'org.gnome.Hamster'
HAMSTER_PATH = '/org/gnome/Hamster'
HAMSTER_INTERFACE = 'org.gnome.Hamster'

class ConfigurationError(Exception):
    '''An error of configuration.'''
    pass

class HamsterClient(object):
    '''The main application.'''

    def __init__(self):
        try:
            connection = dbus.SessionBus()
            hamster_conn = dbus.Interface(connection.get_object(HAMSTER_SERVICE,
                                                                HAMSTER_PATH),
                                          dbus_interface=HAMSTER_INTERFACE)
            self.conn = hamster_conn
        except dbus.DBusException:
            sys.exit("Hamster appears to be down (can't connect via D-Bus)") # TODO - can't just sys.exit in constructor


    def start_tracking(self, activity, start_time = None, end_time = None):
        '''Start a new activity.'''

        start_stamp = timestamp_from_datetime(start_time)
        end_stamp = timestamp_from_datetime(end_time)

        self.conn.AddFact(activity, dbus.UInt32(start_stamp), dbus.UInt32(end_stamp))


    def stop_tracking(self):
        '''Stop tracking the current activity.'''
        self.conn.StopTracking()



    def list(self, start_time = None, end_time = None):
        '''Print a listing of activities.'''

        start_time = start_time or dt.datetime.combine(dt.date.today(), dt.time())
        end_time = end_time or start_time.replace(hour=23, minute=59, second=59)


        headers = {'activity': _("Activity"),
                   'category': _("Category"),
                   'tags': _("Tags"),
                   'start': _("Start"),
                   'end': _("End"),
                   'duration': _("Duration")}
        line_fmt = ' %*s - %*s (%*s) | %s@%s %s'


        start_stamp = timestamp_from_datetime(start_time)
        end_stamp = timestamp_from_datetime(end_time)

        print_with_date = start_time.date() != start_time.date()
        if print_with_date:
            dates_align_width = len('xxxx-xx-xx xx:xx')
        else:
            dates_align_width = len('xx:xx')

        column_width = {'start': max(len(headers['start']), dates_align_width),
                        'end':   max(len(headers['end']), dates_align_width),
                        'duration': max(len(headers['duration']), 7)}

        print line_fmt % (column_width['start'], headers['start'],
                          column_width['end'], headers['end'],
                          column_width['duration'], headers['duration'],
                          headers['activity'],
                          headers['category'],
                          headers['tags'])
        first_column_width = (8 + sum(column_width.values()))
        second_column_width = 4 + len(headers['activity']) + \
                              len(headers['category']) + \
                              len(headers['tags'])

        print "%s+%s" % ('-' * first_column_width, '-' * second_column_width)
        for fact in self.conn.GetFacts(start_stamp, end_stamp):
            if fact['start_time'] < start_stamp or fact['start_time'] > end_stamp:
                # Hamster returns activities for the whole day, not just the
                # time range we sent
                # TODO - why should that be a problem? /toms/
                continue

            fact_data = fact_dict(fact, print_with_date)
            print line_fmt % (column_width['start'], fact_data['start'],
                              column_width['end'], fact_data['end'],
                              column_width['duration'], fact_data['duration'],
                              fact_data['activity'],
                              fact_data['category'],
                              fact_data['tags'])

    def list_activities(self):
        '''Print the names of all the activities.'''
        for activity, category in self.conn.GetActivities():
            print '%s@%s' % (activity.encode('utf8'), category.encode('utf8'))

    def list_categories(self):
        '''Print the names of all the categories.'''
        for category in self.conn.GetCategories():
            print category.encode('utf8')


def timestamp_from_datetime(date):
    '''Convert a local time datetime into an utc timestamp.'''
    if date:
        tz_offset =  dt.timedelta(seconds=time.timezone)
        return time.mktime((date-tz_offset).timetuple())
    else:
        return 0

def datetime_from_timestamp(timestamp):
    '''Convert an utc timestamp into a local time datetime.'''
    return dt.datetime.utcfromtimestamp(timestamp)

def parse_datetime_range(time):
    '''Parse starting and ending datetime separated by a '-'.'''
    start_time, remainder = parse_datetime(time)

    end_time = None
    if remainder and remainder.startswith("-"):
        end_time, remainder = parse_datetime(remainder[1:])

    return start_time, end_time

_DATETIME_PATTERN = ('^((?P<relative>-)?|'
                       '(?P<year>\d{4})'
                       '(-(?P<month>\d{1,2})'
                        '(-(?P<day>\d{1,2}))?)? )?'
                     '((?P<hour>\d{1,2}):)?'
                     '(?P<minute>\d{1,2})'
                     '(:(?P<second>\d{1,2}))?'
                     '(?P<rest>\D.+)?$')
_DATETIME_REGEX = re.compile(_DATETIME_PATTERN)

def parse_datetime(arg):
    '''Parse a date and time.'''
    match = _DATETIME_REGEX.match(arg)
    if not match:
        return dt.datetime.now(), arg

    if match.groupdict()['relative']:
        hour = int(match.groupdict()['hour'] or 0)
        minute = int(match.groupdict()['minute'])
        second = int(match.groupdict()['second'] or 0)
        time_ago = dt.timedelta(hours=hour,
                                      minutes=minute,
                                      seconds=second)
        rest = (match.groupdict()['rest'] or '').strip()
        return dt.datetime.now() - time_ago, rest
    else:
        date = dt.datetime.now().date()
        try:
            if match.groupdict()['year']:
                date = date.replace(year=int(match.groupdict()['year']))
                if match.groupdict()['month']:
                    date = date.replace(month=int(match.groupdict()['month']))
                    if match.groupdict()['day']:
                        date = date.replace(day=int(match.groupdict()['day']))
            time = dt.time(hour=int(match.groupdict()['hour'] or 0),
                                 minute=int(match.groupdict()['minute']),
                                 second=int(match.groupdict()['second'] or 0))
        except ValueError, err:
            if match.groupdict()['rest']:
                date_str = arg[:-len(match.groupdict()['rest'])]
            else:
                date_str = arg

            raise ConfigurationError(_("invalid date/time '%s'" % date_str))
        rest = (match.groupdict()['rest'] or '').strip()
        return dt.datetime.combine(date, time), rest

def fact_dict(fact_data, with_date):
    fact = {}
    if with_date:
        fmt = '%Y-%m-%d %H:%M'
    else:
        fmt = '%H:%M'

    start_date = datetime_from_timestamp(fact_data['start_time'])
    fact['start'] = start_date.strftime(fmt)
    if fact_data['end_time']:
        end_date = datetime_from_timestamp(fact_data['end_time'])
        fact['end'] = end_date.strftime(fmt)
    else:
        end_date = dt.datetime.now()
        fact['end'] = ''

    fact['duration'] = stuff.format_duration(end_date - start_date)
    fact['duration'] = fact['duration']

    fact['activity'] = fact_data['name']
    fact['category'] = fact_data['category']
    if fact_data['tags']:
        fact['tags'] = ' '.join('#%s' % tag for tag in fact_data['tags'])
    else:
        fact['tags'] = ''
    return fact


if __name__ == '__main__':
    # Setup i18n
    gettext.install("hamster-applet", unicode=True)
    locale_dir = os.path.abspath(os.path.join(defs.DATA_DIR, "locale"))
    for module in (gettext, locale):
        module.bindtextdomain('hamster-applet', locale_dir)
        module.textdomain('hamster-applet')

        if hasattr(module, 'bind_textdomain_codeset'):
            module.bind_textdomain_codeset('hamster-applet','UTF-8')



    usage = _(
"""Client for controlling the hamster-applet. Usage:
  %(prog)s start ACTIVITY [START_TIME[-END_TIME]]
  %(prog)s stop
  %(prog)s list [START_TIME[-END_TIME]]

Actions:
    * start (default): Start tracking an activity.
    * stop: Stop tracking current activity.
    * list: List activities.
    * list-activities: List all the activities names, one per line.
    * list-categories: List all the categories names, one per line.

Time formats:
    * 'YYYY-MM-DD hh:mm:ss': Absolute time. Defaulting to 0 for the time
            values missing, and current day for date values.
            E.g. (considering 2010-03-09 16:30:20 as current date, time):
                2010-03 13:15:40 is 2010-03-09 13:15:40
                2010-03-09 13:15 is 2010-03-09 13:15:00
                2010-03-09 13    is 2010-03-09 00:13:00
                2010-02 13:15:40 is 2010-02-09 13:15:40
                13:20            is 2010-03-09 13:20:00
                20               is 2010-03-09 00:20:00
    * '-hh:mm:ss': Relative time. From the current date and time. Defaulting
            to 0 for the time values missing, same as in absolute time.

""")


    # CLI Structure: ./hamster-client.py <start|stop|list|...> <conditional_args>

    if len(sys.argv) < 2:
        sys.exit(usage % {'prog': sys.argv[0]})

    command, args = sys.argv[1], sys.argv[2:]


    if command not in ['start', 'stop', 'list', 'list-activities', 'list-categories']:
        # unknown command - print usage, go home
        sys.exit(usage % {'prog': sys.argv[0]})


    hamster_client = HamsterClient()

    if command == 'start':
        if not args: # mandatory is only the activity name
            sys.exit(usage % {'prog': sys.argv[0]})

        activity = args[0]

        start_time, end_time = None, None
        if len(args) > 1:
            start_time, end_time = parse_datetime_range(args[1])

            if start_time > dt.datetime.now() or (end_time and end_time > dt.datetime.now()):
                sys.exit("Activity must start and finish before current time")

        hamster_client.start_tracking(activity, start_time, end_time)

    elif command == 'stop':
        hamster_client.stop_tracking()

    elif command == 'list':
        start_time, end_time = None, None
        if args:
            start_time, end_time = parse_datetime_range(args[0])

        hamster_client.list(start_time, end_time)

    elif command == 'list-activities':
        hamster_client.list_activities()

    elif command == 'list-categories':
        hamster_client.list_categories()



