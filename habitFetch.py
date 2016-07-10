'''
The MIT License (MIT)

Copyright (c) 2015 Raymond Arnold, Nathan Hwang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
'''

# Uses sqlalchemy version 0.9.8

import argparse
import calendar
import datetime
import json
import requests
import settings
import sqlalchemy
import sqlite3
import sys
import time
import traceback

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import and_

from habitrpg_api import HabitApi
from models import Task, Tag, History, ChecklistItem, Base

'''
Notes
If you do multiple habits in a short timespan, 
    it saves the old timestamp and updates it with new graph data

'''

################################################################################
# Constants

engine = sqlalchemy.create_engine('sqlite:///habitrpg_data.db')
Base.metadata.create_all(engine)

parser = argparse.ArgumentParser()
parser.add_argument("-v", "--verbose", action="store_true")

VERBOSE = parser.parse_args().verbose
if VERBOSE:
    print 'Running in verbose mode'

################################################################################
# Utilities

def verbose_print(string):
    if VERBOSE:
        print string

def convert_date(old_timestamp):
    '''
    Convert a Javascript timestamp OR custom formatted time string to a
    UNIX timestamp.
    '''
    try:
        new_timestamp = float(old_timestamp)/1000
    except:
        new_timestamp = time.strptime(old_timestamp.split(".")[0],
                                      "%Y-%m-%dT%H:%M:%S")
        new_timestamp = calendar.timegm(new_timestamp)
    return new_timestamp

################################################################################
# HabitRPG processing

def find_or_add_tag(session, id, name):
    try:
        # Does the tag ID exist already?
        tag = session.query(Tag).filter_by(id=id).first()

        # If not, create it
        if tag == None:
            tag = Tag(id=id, name=name)
            session.add(tag)
            session.commit()
            return tag

        # If so, update the tag's name to latest data, then return it
        else:
            if name:
                if tag.name != name:
                    tag.name = name
                    session.commit()
            return session.query(Tag).filter_by(id=id).first()
    except:
        traceback.print_exc(file=sys.stderr)
        print >> sys.stderr, " "

def add_task(session, id, name, task_type, date_created, date_completed, tags):
    '''
    Try to add or update a task.
    '''
    try:
        task = session.query(Task).filter_by(id=id).first()
        if task == None:
            task = Task(id=id, name=name, task_type=task_type,
                        date_created=date_created, tags=[])
            session.add(task)
            output = "New Task Created: "
        else:
            output = "Task already exists: "

        # Removes all the tags and then re-adds them, to make sure
        # they're cleanly up to date
        while task.tags:
            task.tags.pop()

        for tag in tags:
            if tag != None:
                try:
                    task.tags.append(find_or_add_tag(session, tag.id, tag.name))
                    verbose_print(("Added tag", tag))
                except:
                    traceback.print_exc(file=sys.stderr)
                    print >> sys.stderr, "Failed to add tag", tag

        session.commit()
        verbose_print((output, task.name))
        return task
    except:
        traceback.print_exc(file=sys.stderr)
        print >> sys.stderr, " "

def add_history(session, date_created, task_id, value):
    try:
        history = session.query(History).filter_by(date_created=date_created).filter_by(task_id=task_id).filter_by(value=value).first()

        if history == None:

            # looks for the most recent history, and compare's it's
            # value to the current value to detect if the user checked
            # off the daily, or +/- checked a habit
            previous_history = session.query(History). \
                                   order_by(History.date_created.desc()). \
                                   filter_by(task_id=task_id).first()
            adjust = 0
            if previous_history:
                if previous_history.value < value:
                    adjust = 1
                if previous_history.value > value:
                    adjust = -1

            history = History(date_created=date_created,
                              task_id=task_id,
                              adjust=adjust,
                              value=value)
            session.add(history)
            output = "    New History Created:"
        else:
            output = "    History already exists:"
        verbose_print((output, history)) 
        session.commit()
        return history
    except:
        print >> sys.stderr, "Failed to add History"
        traceback.print_exc(file=sys.stderr)
        print >> sys.stderr, " "

def add_checklist_item(session, name, completed, history_id):
    try:
        checklist_item = session.query(ChecklistItem).filter_by(history_id=history_id).filter_by(name=name).first()
        if checklist_item == None:
            checklist_item = ChecklistItem(
                name=name, 
                completed=completed, 
                history_id=history_id
                )
            session.add(checklist_item)
            output = "    New ChecklistItem Created"
        else:
            output = "    ChecklistItem already exists"
        session.commit()
        verbose_print((output, checklist_item))
        return checklist_item
    except:
        print >> sys.stderr, "Error while adding checklist"
        traceback.print_exc(file=sys.stderr)
        print >> sys.stderr, " "

def process_task(session, task):
    try:
        # Warning: Tasks with old, deleted tags will not retain data
        # about those tagstag
        tags = [session.query(Tag).filter_by(id=x).first()
                for x in task['tags']]

        verbose_print(json.dumps(task, sort_keys=True,indent=4))

        # Todo tasks have a "date_completed" attribute, others do not
        try:
            date_completed = convert_date(task['dateCompleted'])
        except:
            date_completed = None

        add_task(session,
            id=task['id'],
            name=task['text'],
            task_type=task['type'],
            date_created=convert_date(task['createdAt']),
            date_completed=date_completed,
            tags=tags)

        # By default, it creates one history item with today's date.
        # If the task has at least one history of it's own, instead it
        # creates histories based on those
        year = time.gmtime(time.time()).tm_year
        month = time.gmtime(time.time()).tm_mon
        day = time.gmtime(time.time()).tm_mday
        date_created = time.mktime(datetime.datetime(year, month, day).timetuple())*1000
        histories = [{'date': date_created, 'value':0}]
        try:
            if len(task['history']) != 0:
                histories = task['history']
        except:
            pass


        for history in histories:
            new_history = add_history(
                session = session,
                date_created = convert_date(history['date']),
                task_id = task['id'],
                value = history['value']
                )

            try:
                for checklist_item in task['checklist']:
                    add_checklist_item(
                        session=session,
                        name = checklist_item['text'],
                        history_id = new_history.id,
                        completed = checklist_item['completed'],
                        )
            except:
                pass
            verbose_print("")
    except:
        traceback.print_exc(file=sys.stderr)
        print >> sys.stderr, " "

################################################################################
# Main

def store_latest():
    hrpg = HabitApi(user_id = settings.user_id,
                    api_key = settings.api_key)

    # Make sure the user is proper json.
    try:
        json.dumps(hrpg.user())
    except TypeError:
        print >> sys.stderr, "User profile is not valid JSON, giving up."
        sys.exit(1)

    # Gentlemen, start your sql engines.
    Session = sessionmaker(bind=engine)
    session = Session()

    # Dump out a bunch of aggregate diagnostic information.
    if VERBOSE:
        print "DATABASE, BEFORE:"
        print "tag count:", session.query(Tag).count()
        print "task count:", session.query(Task).count()
        print "history count:", session.query(History).count()
        print "checklist_item count:", session.query(ChecklistItem).count()

    # Add new tags and tasks if necessary.
    verbose_print("----                 Checking Tags                     ----")
    for tag in hrpg.user()['data']['tags']:
        verbose_print(find_or_add_tag(session, id=tag['id'], name=tag['name']))

    verbose_print("----                 Checking Tasks                    ----")
    for task in hrpg.tasks()['data']:
        verbose_print(process_task(session, task))

    # Check separately for completed tasks.
    verbose_print("----             Checking Completed Tasks              ----")
    for task in hrpg.completed_tasks()['data']:
        verbose_print(process_task(session, task))

    # Dump out specific diagnostic information.
    if VERBOSE:
        print "---------------------TAGS IN DATABASE---------------------"
        for item in session.query(Tag).all():
            print item
        print "---------------------TASKS IN DATABASE--------------------"
        for task in session.query(Task).all():
            print task
            for history in session.query(History).filter_by(task_id=task.id).all():
                print "    ", history
                for checklist_item in session.query(ChecklistItem).filter_by(history_id=history.id).all():
                    print "        ", checklist_item

    # Dump out a bunch more aggregate diagnostic information.
    if VERBOSE:
        print "DATABASE, AFTER:"
        print "tag count:", session.query(Tag).count()
        print "task count:", session.query(Task).count()
        print "history count:", session.query(History).count()
        print "checklist_item count:", session.query(ChecklistItem).count()

    session.close()

# Turn off urllib3 warnings; very bad, I know.
requests.packages.urllib3.disable_warnings()

store_latest()
