#!/usr/bin/env python
# vim:ts=4:sw=4:ai:expandtab:filetype=python

import os,sys
import itertools
import MySQLdb

from pprint import pprint

sys.path.insert(0,os.path.join(os.path.dirname(os.path.abspath(__file__)), "gspread"))

import gspread

import conf

from oauth2client.service_account import ServiceAccountCredentials

class TableFromGoogle(object):
    SCOPE = "https://spreadsheets.google.com/feeds"

    def __init__(self, sheetkey, **kvdefs):
        self._keydef = self._mkkeydef(**kvdefs)
        self._sheetkey = sheetkey
        self.headers = []
        self.rows = []

    def _mkkeydef(self, project_id, private_key_id, private_key, client_id, **extra_args):
        keyref = {
                "type":  "service_account",
                "project_id": project_id,
                "private_key_id": private_key_id,
                "private_key": private_key,
                "client_email": "{}@appspot.gserviceaccount.com".format(project_id),
                "client_id": client_id,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://accounts.google.com/o/oauth2/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/{}%40appspot.gserviceaccount.com"\
                        .format(project_id)
        }
        keyref.update(dict(extra_args))

        return keyref

    def _entry_to_dict(self, headers, row):
        result = dict()
        for (h,v) in itertools.izip(self.headers, row):
            if h in result:
                if isinstance(result[h], list):
                    result[h].append(v)
                else:
                    result[h] = [ result[h], v ]
            else:
                result[h] = v
        return result


    def read(self):
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(self._keydef, scopes = self.SCOPE)
        gc = gspread.authorize(credentials)
        doc = gc.open_by_key(self._sheetkey)
        sheet = doc.sheet1
        table = sheet.get_all_values()
        self.headers = table.pop(0)
        self.rows = [ self._entry_to_dict(self.headers, row) for row in table if row[0] and row[1] and row[2]]

def break_out_patrols(table_entries):
    anmalningar = []
    for anmalan in table_entries:
        for (patrull,avd) in itertools.izip(anmalan["Patrull"], anmalan["Avdelning"]):
            if patrull:
                rec = anmalan.copy()
                rec["Patrull"] = patrull
                rec["Avdelning"] = avd
                anmalningar.append(rec)
    return anmalningar
class Transaction(object):
    def __init__(self, db):
        self._db = db
        self._cursor = None

    def __enter__(self):
        self._cursor = self._db.cursor()
        return self._cursor

    def __exit__(self, exc, value, tb):
        self._cursor.close()
        self._db.commit()
        return False

class DbTable(object):
    def __init__(self, user, passwd, db):
        self._db = MySQLdb.connect(user = user, passwd = passwd, db = db, use_unicode = True)

    def tuple2str(self, t):
        return '({})'.format(', '.join(t))


    def delete(self, table):
        with Transaction(self._db) as cursor:
            cursor.execute("DELETE FROM {table}".format(table = table))

    def select(self, table, fields):
        with Transaction(self._db) as cursor:
            cursor.execute('SELECT {fields} FROM {table}'.format(table = table, fields = ', '.join(fields)))
            return list(cursor.fetchall())


    def insert(self, table, fields, values):
        with Transaction(self._db) as cursor:
            cursor.executemany(
                """INSERT INTO {table} {fields} VALUES {values}"""\
                    .format(table = table, fields = self.tuple2str(fields), values = self.tuple2str(("%s" for i in fields))),
            values)


if __name__ == "__main__":
    t = TableFromGoogle(**(conf.google))

    d = DbTable(**(conf.db))

    t.read()


    patrols = break_out_patrols(t.rows)

    tracks = dict(d.select(table = "track", fields = ('trackname', 'trackid')))
    d.insert("track", ("trackname",), [(t,) for t in set(p["Avdelning"].capitalize() for p in patrols) if t not in tracks])
    tracks = dict(d.select(table = "track", fields = ('trackname', 'trackid')))
    d.insert(
        table = "patrol", 
        fields = ("patrolname", "fk_track", "troop", "status", "paid", "leadercontact"),
        values = [
            (p["Patrull"], tracks[p["Avdelning"]], p[u'K\xe5r'], "REGISTERED", 'ok' in p["Betalt"].lower(), u'{p[Namn]} {p[Mobilnummer]} {p[Epost]}'.format(p = p))
            for p in patrols
        ]
    )


