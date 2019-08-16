# danki - A personal Anki sync server
# Copyright (C) 2013 David Snopek
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import json
import logging
import os
import random
import re
import string
import sys
import time
import unicodedata
import zipfile
from configparser import ConfigParser
from sqlite3 import dbapi2 as sqlite
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.utils.decorators import decorator_from_middleware
from django.views.decorators.csrf import csrf_exempt

import anki.db
import anki.sync
import anki.utils
from anki.consts import SYNC_VER, SYNC_ZIP_SIZE, SYNC_ZIP_COUNT
from anki.consts import REM_CARD, REM_NOTE
from danki.danki_middleware import DankiMiddleware

from danki.full_sync import get_full_sync_manager

from django.http import HttpResponse, JsonResponse, HttpRequest, HttpResponseForbidden, HttpResponseBadRequest, \
    HttpResponseNotFound

danki = decorator_from_middleware(DankiMiddleware)


@danki
@csrf_exempt
def hostKey(request: HttpRequest):
    # authenticate user
    if 'u' not in request.danki_data or 'p' not in request.danki_data:
        return HttpResponseForbidden("must pass credentials in file")

    user: User = authenticate(username=request.danki_data['u'], password=request.danki_data['p'])
    if user is None:
        return HttpResponseForbidden("credentials didn't work")

    # generate and store host key
    import hashlib, time, random, string
    chars = string.ascii_letters + string.digits
    val = ':'.join([user.username, str(int(time.time())), ''.join(random.choice(chars) for x in range(8))]).encode()
    hostKey = hashlib.md5(val).hexdigest()
    request.session['k'] = hostKey

    # return the host key
    return JsonResponse({'key': hostKey})


@danki
class SyncCollectionHandler(anki.sync.Syncer):
    def __init__(self, col):
        # So that 'server' (the 3rd argument) can't get set
        anki.sync.Syncer.__init__(self, col)

    @staticmethod
    def _old_client(cv):
        if not cv:
            return False

        note = {"alpha": 0, "beta": 0, "rc": 0}
        client, version, platform = cv.split(',')

        for name in note.keys():
            if name in version:
                vs = version.split(name)
                version = vs[0]
                note[name] = int(vs[-1])

        # convert the version string, ignoring non-numeric suffixes like in beta versions of Anki
        version_nosuffix = re.sub(r'[^0-9.].*$', '', version)
        version_int = [int(x) for x in version_nosuffix.split('.')]

        if client == 'ankidesktop':
            return version_int < [2, 0, 27]
        elif client == 'ankidroid':
            if version_int == [2, 3]:
               if note["alpha"]:
                  return note["alpha"] < 4
            else:
               return version_int < [2, 2, 3]
        else:  # unknown client, assume current version
            return False

    @csrf_exempt
    def meta(self, request: HttpRequest):
        if 'c' not in request.danki_data or 'cv' not in request.danki_data:
            return HttpResponseBadRequest()

        v = request.danki_data['c']
        cv = request.danki_data['cv']


        if self._old_client(cv):
            return HttpResponse(status=501) # Client needs to be updated
        if v > SYNC_VER:
            return JsonResponse({"cont": False, "msg": "Your client is using unsupported sync protocol ({}, supported version: {})".format(v, SYNC_VER)})
        if v < 9 and self.col.schedVer() >= 2:
            return JsonResponse({"cont": False, "msg": "Your client doesn't support the v{} scheduler.".format(self.col.schedVer())})

        # Make sure the media database is open!
        if self.col.media.db is None:
            self.col.media.connect()

        return JsonResponse({
            'scm': self.col.scm,
            'ts': anki.utils.intTime(),
            'mod': self.col.mod,
            'usn': self.col._usn,
            'musn': self.col.media.lastUsn(),
            'msg': '',
            'cont': True,
        })

    def usnLim(self):
        return "usn >= %d" % self.minUsn

    # ankidesktop >=2.1rc2 sends graves in applyGraves, but still expects
    # server-side deletions to be returned by start
    def start(self, minUsn, lnewer, graves={"cards": [], "notes": [], "decks": []}):
        self.maxUsn = self.col._usn
        self.minUsn = minUsn
        self.lnewer = not lnewer
        lgraves = self.removed()
        self.remove(graves)
        return lgraves

    def applyGraves(self, chunk):
        self.remove(chunk)

    def applyChanges(self, changes):
        self.rchg = changes
        lchg = self.changes()
        # merge our side before returning
        self.mergeChanges(lchg, self.rchg)
        return lchg

    def sanityCheck2(self, client):
        server = self.sanityCheck()
        if client != server:
            return dict(status="bad", c=client, s=server)
        return dict(status="ok")

    def finish(self, mod=None):
        return anki.sync.Syncer.finish(self, anki.utils.intTime(1000))

    # Syncer.removed() doesn't use self.usnLim() in queries, so we have to
    # replace "usn=-1" by hand
    def removed(self):
        cards = []
        notes = []
        decks = []

        curs = self.col.db.execute(
            "select oid, type from graves where usn >= ?", self.minUsn)

        for oid, type in curs:
            if type == REM_CARD:
                cards.append(oid)
            elif type == REM_NOTE:
                notes.append(oid)
            else:
                decks.append(oid)

        return dict(cards=cards, notes=notes, decks=decks)

    def getModels(self):
        return [m for m in self.col.models.all() if m['usn'] >= self.minUsn]

    def getDecks(self):
        return [
            [g for g in self.col.decks.all() if g['usn'] >= self.minUsn],
            [g for g in self.col.decks.allConf() if g['usn'] >= self.minUsn]
        ]

    def getTags(self):
        return [t for t, usn in self.col.tags.allItems() if usn >= self.minUsn]