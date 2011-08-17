#License#
#bitHopper by Colin Rice is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 3.0 Unported License.
#Based on a work at github.com.

import sqlite3
import os
import os.path
import sys

from twisted.internet.task import LoopingCall

try:
    # determine if application is a script file or frozen exe
    if hasattr(sys, 'frozen'):
        DB_DIR = os.path.dirname(sys.executable)
    else:
        DB_DIR = os.path.dirname(os.path.abspath(__file__))
except:
    DB_DIR = os.curdir()

VERSION_FN = os.path.join(DB_DIR, 'db-version')
DB_FN = os.path.join(DB_DIR, 'stats.db')

class Database():
    def __init__(self,bitHopper):
        self.curs = None
        self.bitHopper = bitHopper
        self.pool = bitHopper.pool
        self.check_database()
        self.shares = {}
        self.rejects = {}
        self.payout = {}

        call = LoopingCall(self.write_database)
        call.start(60)

    def close(self):
        self.curs.close()

    def sql_insert(self,server, shares=0, rejects=0, payout=0, user='',diff=None):
        if diff == None:
            difficulty = self.bitHopper.difficulty.get_difficulty()
        else:
            difficulty = diff
        sql = 'INSERT INTO ' + server + ' VALUES ( ' + str(difficulty) + ',' + str(shares) + ','+str(rejects) + ',' + str(payout)+',\'' + user + '\')'
        return sql

    def sql_update_add(self, server, value, amount, user):
        difficulty = self.bitHopper.difficulty.get_difficulty()
        sql = 'UPDATE '+ str(server) +' SET '+value+'= '+value+' + '+ str(amount) +' WHERE diff='+ str(difficulty) + ' and user= \'' + user + "\'"
        return sql


    def sql_update_set(self, server, value, amount, user, difficulty):
        sql = 'UPDATE '+ str(server) +' SET '+value+'= '+ str(amount) +' WHERE diff='+ str(difficulty) + ' and user= \'' + user + "\'"
        return sql

    def write_database(self):
        self.bitHopper.log_msg('writing to database')

        difficulty = self.bitHopper.difficulty.get_difficulty()
        for server in self.shares:
            for user in self.shares[server]:
                if self.shares[server][user] == 0:
                    continue
                shares = self.shares[server][user]
                sql = self.sql_update_add(server,'shares',shares,user)
                self.curs.execute(sql)
                if len(self.curs.execute('select * from ' + server + '  WHERE diff='+ str(difficulty) + ' and user= \'' + str(user) + "\'").fetchall()) == 0:
                    sql = self.sql_insert(server,shares=shares,user=user)
                    self.curs.execute(sql)
                self.shares[server][user] = 0

        for server in self.rejects:
            for user in self.rejects[server]:
                if self.rejects[server][user] == 0:
                    continue
                rejects = self.rejects[server][user]
                sql = self.sql_update_add(server,'rejects',rejects,user)
                self.curs.execute(sql)
                if len(self.curs.execute('select * from ' + server + '  WHERE diff='+ str(difficulty) + ' and user= \'' + str(user) + "\'").fetchall()) == 0:
                    sql = self.sql_insert(server,rejects=rejects,user=user)
                    self.curs.execute(sql)
                self.rejects[server][user] = 0

        for server in self.payout:
            if self.payout[server] == None:
                continue
            payout = self.payout[server]
            sql = self.sql_update_set(server,'stored_payout', payout,'',1)
            self.curs.execute(sql)
            if len(self.curs.execute('select * from ' + server + '  WHERE diff='+ str(1) + ' and user= \'\'').fetchall()) == 0:
                sql = self.sql_insert(server,payout=payout,diff=1)
                self.curs.execute(sql)
            self.payout[server] = None

        self.database.commit()

    def check_database(self):
        self.bitHopper.log_msg('Checking Database')
        if os.path.exists(DB_FN):
            try:
                versionfd = open(VERSION_FN, 'rb')
                version = versionfd.read()
                self.bitHopper.log_dbg("DB Verson: " + version)
                if version == "0.1":
                    self.bitHopper.log_msg('Old Database')
                versionfd.close()
            except:
                os.remove(DB_FN)

        version = open(VERSION_FN, 'wb')
        version.write("0.2")
        version.close()

        self.database = sqlite3.connect(DB_FN)
        self.curs = self.database.cursor()

        if version == "0.1":
            sql = "SELECT name FROM sqlite_master WHERE type='table'"
            self.curs.execute(sql)
            result = self.curs.fetchall()
            for item in result:
                sql = "ALTER TABLE " + item[0] + " ADD COLUMN user TEXT"
                self.curs.execute(sql)
        self.database.commit()

        for server_name in self.pool.get_servers():
            difficulty = self.bitHopper.difficulty.get_difficulty()
            sql = "CREATE TABLE IF NOT EXISTS "+server_name +" (diff REAL, shares INTEGER, rejects INTEGER, stored_payout REAL, user TEXT)"
            self.curs.execute(sql)

        self.database.commit()

        self.bitHopper.log_dbg('Database Setup')

    def get_users(self):
        #Get an dictionary of user information to seed data.py
        #This is a direct database lookup and should only be called once
        users = {}
        servers = self.bitHopper.pool.get_servers()
        for server in servers:
            sql = 'select user, shares, rejects from ' + server
            self.curs.execute(sql)
            result = self.curs.fetchall()
            for item in result:
                if item[0] not in users:
                    users[item[0]] = {'shares':0,'rejects':0}
                users[item[0]]['shares'] += item[1]
                users[item[0]]['rejects'] += item[2]
        return users

    def update_shares(self,server, shares, user, password):
        if server not in self.shares:
            self.shares[server] = {}
        if user not in self.shares[server]:
            self.shares[server][user] = 0
        self.shares[server][user] += shares

    def get_shares(self,server):
        sql = 'select shares from ' + str(server)
        self.curs.execute(sql)
        shares = 0
        for info in self.curs.fetchall():
            shares += int(info[0])
        return shares

    def get_expected_payout(self,server):
        sql = 'select shares, diff from ' + str(server)
        self.curs.execute(sql)
        result = self.curs.fetchall()
        expected = 0
        for item in result:
            shares = item[0]
            difficulty = item[1]
            expected += float(shares)/difficulty * 50
        return expected

    def update_rejects(self,server,shares, user, password):
        if server not in self.rejects:
            self.rejects[server] = {}
        if user not in self.rejects[server]:
            self.rejects[server][user] = 0
        self.rejects[server][user] += shares

    def get_rejects(self,server):
        sql = 'select rejects from ' + str(server)
        self.curs.execute(sql)
        shares = 0
        for info in self.curs.fetchall():
            shares += int(info[0])
        return shares

    def set_payout(self,server,payout):
        if server not in self.payout:
            self.payout[server] = None
        self.payout[server] = payout

    def get_payout(self,server):
        sql = 'select stored_payout from ' + server + ' where diff=1'
        self.curs.execute(sql)
        payout = 0
        for info in self.curs.fetchall():
            payout += float(info[0])
        return payout

