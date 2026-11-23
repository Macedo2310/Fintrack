"""Deterministic tests for progress isolation, replay and wall-clock checks."""
import sqlite3
from contextlib import contextmanager
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi import FastAPI, HTTPException
import video_lessons as v

class GuardTest(unittest.TestCase):
    def setUp(self):
        (Path(__file__).resolve().parents[1]/'.work').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'.work')
        @contextmanager
        def conn():
            c=sqlite3.connect(str(Path(self.tmp.name)/'test.db'));c.row_factory=sqlite3.Row
            try:
                with c: yield c
            finally:c.close()
        self.conn=conn;v.migrate(conn)
        app=FastAPI();v.register(app,conn,lambda request:{'id':request})
        endpoints={r.path.rsplit('/',1)[-1]:r.endpoint for r in app.routes if r.path.startswith('/api/intro')}
        self.start=endpoints['start'];self.tick=endpoints['tick']
        self.clock=patch.object(v.time,'time',return_value=1000);self.now=self.clock.start()
    def tearDown(self):
        self.clock.stop();self.tmp.cleanup()
    def test_guard(self):
        s=self.start('poupanca','alice');token=s['token']
        with self.assertRaises(HTTPException):v.require_intro(self.conn,'alice','poupanca')
        r=self.tick('poupanca',v.Tick(token=token,position=s['duration']),'alice')
        self.assertFalse(r['accepted']);self.assertFalse(r['completed'])
        # Real-time, contiguous playback reaches the end.
        for pos in list(range(1,int(s['duration'])+1))+[s['duration']]:
            self.now.return_value=1000+pos
            r=self.tick('poupanca',v.Tick(token=token,position=pos),'alice')
            self.assertTrue(r['accepted'])
        self.assertTrue(r['completed']);v.require_intro(self.conn,'alice','poupanca')
        self.assertFalse(v.status(self.conn,'bob','poupanca')['completed'])
        self.assertFalse(v.status(self.conn,'alice','controle')['completed'])
        with self.assertRaises(HTTPException):self.tick('poupanca',v.Tick(token=token,position=1),'bob')
        self.assertTrue(self.start('poupanca','alice')['completed'])
        with self.assertRaises(HTTPException):self.tick('poupanca',v.Tick(token=token,position=1),'alice')
    def test_speed_and_resume(self):
        s=self.start('controle','alice');token=s['token']
        self.now.return_value=1002
        self.assertTrue(self.tick('controle',v.Tick(token=token,position=2),'alice')['accepted'])
        self.assertFalse(self.tick('controle',v.Tick(token=token,position=4),'alice')['accepted'])
        self.assertEqual(self.start('controle','alice')['watched'],2)

if __name__=='__main__':unittest.main()
