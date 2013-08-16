#!/usr/bin/env python
# To run only the tests in this file, use:
# python -m unittest test_mappers
# To run a single test,
# python -m unittest test_mappers.TestMappers.test_connectUsing

import os
import os.path
import unittest
import pyworkflow.mapper.postgresql
from pyworkflow.object import *


# @see test_object.TestPyworkflow.test_SqliteMapper
class TestMappers(unittest.TestCase):

    # !!!! add some asserts to the tests

    def getScipionHome(self):
        if "SCIPION_HOME" not in os.environ:
            raise Exception("SCIPION_HOME is not defined as environment variable")

        return os.environ["SCIPION_HOME"]


    def test_PostgresqlMapper(self):
        # Note: general-purpose exception-handling is handled by Pyunit
        mapper = pyworkflow.mapper.postgresql.PostgresqlMapper()

        i = Integer(4)

        mapper.insert(i)

        mapper.commit()

        objects = mapper.selectAll()
        self.assertEqual(len(objects),1)

    def test_connectUsing(self):
        db= pyworkflow.mapper.postgresql.PostgresqlDb()
        dbconfig= os.path.join(self.getScipionHome() , "postgresql.xml")
        db.connectUsing(dbconfig)
        return db

    def test_createTables(self):
        db=self.test_connectUsing()
        db.createTables()

    def test_insert(self):
       dbconfig= os.path.join(self.getScipionHome() , "postgresql.xml")
       mapper = pyworkflow.mapper.postgresql.PostgresqlMapper(dbconfig)
       i = Integer(4)
       mapper.insert(i)

    # !!!! insert a complex object
    def test_insertChildren(self):
        pass

    # !!!! actually select some object by its parent id
    def test_selectObjectsByParent(self):
        db=self.test_connectUsing()
        objects=db.selectObjectsByParent()
        print objects

    def test_selectById(self):
       dbconfig= os.path.join(self.getScipionHome() , "postgresql.xml")
       mapper = pyworkflow.mapper.postgresql.PostgresqlMapper(dbconfig)
       object = mapper.selectById(2)
       object.printAll()
        

    def test_selectAll(self):
       dbconfig= os.path.join(self.getScipionHome() , "postgresql.xml")
       mapper = pyworkflow.mapper.postgresql.PostgresqlMapper(dbconfig)
       for object in mapper.selectAll():
           object.printAll()
