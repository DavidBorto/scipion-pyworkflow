# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (jmdelarosa@cnb.csic.es)
# *
# * Unidad de  Bioinformatica of Centro Nacional de Biotecnologia , CSIC
# *
# * This program is free software; you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation; either version 2 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program; if not, write to the Free Software
# * Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA
# * 02111-1307  USA
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'jmdelarosa@cnb.csic.es'
# *
# **************************************************************************

import sys
from collections import OrderedDict
from pyworkflow.utils.path import replaceExt, joinExt, exists
from pyworkflow.utils import trace
from mapper import Mapper


class SqliteMapper(Mapper):
    """Specific Mapper implementation using Sqlite database"""
    def __init__(self, dbName, dictClasses=None):
        Mapper.__init__(self, dictClasses)
        self.__initObjDict()
        self.__initUpdateDict()
        try:
            self.db = SqliteDb(dbName)
        except Exception, ex:
            raise Exception('Error creating SqliteMapper, dbName: %s\n error: %s' % (dbName, ex))
    
    def commit(self):
        self.db.commit()
        
    def __getObjectValue(self, obj):
        """ Get the value of the object to be stored.
        We need to handle the special case of pointer, where we should
        store as value the object id of the pointed object.
        """
        value = obj.getObjValue()

        if obj.isPointer() and obj.hasValue():
            if value.hasObjId(): # Check the object has been stored previously
                value = value.strId() # For pointers store the id of referenced object
            else:
                self.updatePendingPointers.append(obj)
                value = "Pending update" 
            
        return value
        
    def __insert(self, obj, namePrefix=None):
        obj._objId = self.db.insertObject(obj._objName, obj.getClassName(),
                                          self.__getObjectValue(obj), obj._objParentId,
                                          obj._objLabel, obj._objComment)
        sid = obj.strId()
        if namePrefix is None:
            namePrefix = sid
        else:
            namePrefix = joinExt(namePrefix, sid)
        self.insertChilds(obj, namePrefix)
        
    def insert(self, obj):
        """Insert a new object into the system, the id will be set"""
        self.__insert(obj)
        
    def insertChild(self, obj, key, attr, namePrefix=None):
        if namePrefix is None:
            namePrefix = self.__getNamePrefix(obj)
        attr._objName = joinExt(namePrefix, key)
        attr._objParentId = obj._objId
        self.__insert(attr, namePrefix)
        
    def insertChilds(self, obj, namePrefix=None):
        """ Insert childs of an object, if namePrefix is None,
        the it will be deduced from obj. """
        # This is also done in insertChild, but avoid 
        # doing the same for every child element
        if namePrefix is None:
            namePrefix = self.__getNamePrefix(obj)
        for key, attr in obj.getAttributesToStore():
            self.insertChild(obj, key, attr, namePrefix)
        
    def deleteChilds(self, obj):
        namePrefix = self.__getNamePrefix(obj)
        self.db.deleteChildObjects(namePrefix)
        
    def deleteAll(self):
        """ Delete all objects stored """
        self.db.deleteAll()
                
    def delete(self, obj):
        """Delete an object and all its childs"""
        self.deleteChilds(obj)
        self.db.deleteObject(obj.getObjId())
    
    def __getNamePrefix(self, obj):
        if len(obj._objName) > 0 and '.' in obj._objName:
            return replaceExt(obj._objName, obj.strId())
        return obj.strId()
    
    def __printObj(self, obj):
        print "obj._objId", obj._objId
        print "obj._objParentId", obj._objParentId
        print "obj._objName", obj._objName
        print "obj.getObjValue()", obj.getObjValue()
    
    def updateTo(self, obj, level=1):
        self.__initUpdateDict()
        self.__updateTo(obj, level)
        # Update pending pointers to objects
        for ptr in self.updatePendingPointers:
            self.db.updateObject(ptr._objId, ptr._objName, ptr.getClassName(),
                             self.__getObjectValue(obj), ptr._objParentId, 
                             ptr._objLabel, ptr._objComment)
        
    def __updateTo(self, obj, level):
        self.db.updateObject(obj._objId, obj._objName, obj.getClassName(),
                             self.__getObjectValue(obj), obj._objParentId, 
                             obj._objLabel, obj._objComment)
        if obj.getObjId() in self.updateDict:
            print "id: %d found already in dict. " % obj.getObjId()
            print "FULL DICT:"
#            for k, v in self.updateDict.iteritems():
#                print "%d -> %s" % (k, v.getName())
            raise Exception('Circular reference, object: %s found twice' % obj.getName())
        
        self.updateDict[obj._objId] = obj
        for key, attr in obj.getAttributesToStore():
            if attr._objId is None: # Insert new items from the previous state
                attr._objParentId = obj._objId
                #path = obj._objName[:obj._objName.rfind('.')] # remove from last .
                namePrefix = self.__getNamePrefix(obj)
                attr._objName = joinExt(namePrefix, key)
                self.__insert(attr, namePrefix)
            else:  
                self.__updateTo(attr, level + 2)
        
    def updateFrom(self, obj):
        objRow = self.db.selectObjectById(obj._objId)
        self.fillObject(obj, objRow)
            
    def selectById(self, objId):
        """Build the object which id is objId"""
        if objId in self.objDict:
            obj = self.objDict[objId]
        else:
            objRow = self.db.selectObjectById(objId)
            if objRow is None:
                obj = None
            else:
                obj = self._buildObject(objRow['classname'])
                self.fillObject(obj, objRow)
        return obj
    
    def getParent(self, obj):
        """ Retrieve the parent object of another. """
        return self.selectById(obj._objParentId)
        
    def fillObjectWithRow(self, obj, objRow):
        """Fill the object with row data"""
        obj._objId = objRow['id']
        self.objDict[obj._objId] = obj
        obj._objName = self._getStrValue(objRow['name'])
        obj._objLabel = self._getStrValue(objRow['label'])
        obj._objComment = self._getStrValue(objRow['comment'])
        objValue = objRow['value']
        obj._objParentId = objRow['parent_id']
        
        if obj.isPointer():
            if objValue is not None:
                objValue = self.selectById(int(objValue))
            else:
                objValue = None
        obj.set(objValue)
        
    def fillObject(self, obj, objRow):
        self.fillObjectWithRow(obj, objRow)
        namePrefix = self.__getNamePrefix(obj)
        childs = self.db.selectObjectsByAncestor(namePrefix)
        #childsDict = {obj._objId: obj}
        
        for childRow in childs:
            childParts = childRow['name'].split('.')
            childName = childParts[-1]
            parentId = int(childParts[-2])
            # Here we are assuming that always the parent have
            # been processed first, so it will be in the dictiorary
            parentObj = self.objDict.get(parentId, None)
            if parentObj is None: # Something went wrong
                raise Exception("Parent object (id=%d) was not found, object: %s" % (parentId, childRow['name']))
            
            childObj = getattr(parentObj, childName, None)
            if childObj is None:
                childObj = self._buildObject(childRow['classname'])
                setattr(parentObj, childName, childObj)
            self.fillObjectWithRow(childObj, childRow)  
            #childsDict[childObj._objId] = childObj  
              
    def __objFromRow(self, objRow):
        obj = self._buildObject(objRow['classname'])
        self.fillObject(obj, objRow)
        return obj
        
    def __iterObjectsFromRows(self, objRows, objectFilter=None):
        for objRow in objRows:
            obj = self.__objFromRow(objRow)
            if objectFilter is None or objectFilter(obj):
                yield obj
        
    def __objectsFromRows(self, objRows, iterate=False, objectFilter=None):
        """Create a set of object from a set of rows
        Params:
            objRows: rows result from a db select.
            iterate: if True, iterates over all elements, if False the whole list is returned
            objectFilter: function to filter some of the objects of the results. 
        """
        if not iterate:
            #return [self.__objFromRow(objRow) for objRow in objRows]
            return [obj for obj in self.__iterObjectsFromRows(objRows, objectFilter)]
        else:
            return self.__iterObjectsFromRows(objRows, objectFilter)
               
    def __initObjDict(self):
        """ Clear the objDict cache """        
        self.objDict = {}
        
    def __initUpdateDict(self):
        """ Clear the updateDict cache """        
        self.updateDict = {}
        # This is used to store pointers that pointed object are not stored yet
        self.updatePendingPointers = [] 
         
    def selectBy(self, iterate=False, objectFilter=None, **args):
        """Select object meetings some criterias"""
        self.__initObjDict()
        objRows = self.db.selectObjectsBy(**args)
        return self.__objectsFromRows(objRows, iterate, objectFilter)
    
    def selectByClass(self, className, includeSubclasses=True, iterate=False, objectFilter=None):
        self.__initObjDict()
        if includeSubclasses:
            from pyworkflow.utils.reflection import getSubclasses
            whereStr = "classname='%s'" % className
            base = self.dictClasses.get(className)
            subDict = getSubclasses(base, self.dictClasses)
            for k, v in subDict.iteritems():
                if issubclass(v, base):
                    whereStr += " OR classname='%s'" % k
            objRows = self.db.selectObjectsWhere(whereStr)
            return self.__objectsFromRows(objRows, iterate, objectFilter)
        else:
            return self.selectBy(iterate=iterate, classname=className)
            
    def selectAll(self, iterate=False, objectFilter=None):
        self.__initObjDict()
        objRows = self.db.selectObjectsByParent(parent_id=None)
        return self.__objectsFromRows(objRows, iterate, objectFilter)    
    
    def insertRelation(self, relName, creatorObj, parentObj, childObj):
        """ This function will add a new relation between two objects.
        Params:
            relName: the name of the relation to be added.
            creatorObj: this object will be the one who register the relation.
            parentObj: this is "parent" in the relation
            childObj: this is "child" in the relation
        """
        for o in [creatorObj, parentObj, childObj]:
            if not o.hasObjId():
                raise Exception("Before adding a relation, the object should be stored in mapper")
        self.db.insertRelation(relName, creatorObj.getObjId(), parentObj.getObjId(), childObj.getObjId())
    
    def __objectsFromIds(self, objIds):
        """Return a list of objects, given a list of id's
        """
        return [self.selectById(rowId['id']) for rowId in objIds]
        
    def getRelationChilds(self, relName, parentObj):
        """ Return all "child" objects for a given relation.
        Params:
            relName: the name of the relation.
            parentObj: this is "parent" in the relation
        Returns: 
            a list of "child" objects.
        """
        childIds = self.db.selectRelationChilds(relName, parentObj.getObjId())
        
        return self.__objectsFromIds(childIds)  
            
    def getRelationParents(self, relName, childObj):
        """ Return all "parent" objects for a given relation.
        Params:
            relName: the name of the relation.
            childObj: this is "child" in the relation
        Returns: 
            a list of "parent" objects.
        """
        parentIds = self.db.selectRelationParents(relName, childObj.getObjId())
        
        return self.__objectsFromIds(parentIds)  

    def getRelationsByCreator(self, creatorObj):
        """ Return all relations created by creatorObj. """
        return self.db.selectRelationsByCreator(creatorObj.getObjId())
    
    def getRelationsByName(self, relationName):
        """ Return all relations stored of a given type. """
        return self.db.selectRelationsByName(relationName)

    def deleteRelations(self, creatorObj):
        """ Delete all relations created by object creatorObj """
        self.db.deleteRelationsByCreator(creatorObj.getObjId())
    
    def insertRelationData(self, relName, creatorId, parentId, childId):
        self.db.insertRelation(relName, creatorId, parentId, childId)
    
    
class SqliteDb():
    """Class to handle a Sqlite database.
    It will create connection, execute queries and commands"""
    
    SELECT = "SELECT id, parent_id, name, classname, value, label, comment FROM Objects WHERE "
    DELETE = "DELETE FROM Objects WHERE "
    
    SELECT_RELATION = "SELECT object_%s_id AS id FROM Relations WHERE name=? AND object_%s_id=?"
    SELECT_RELATIONS = "SELECT * FROM Relations WHERE "
    
    def selectCmd(self, whereStr, orderByStr=' ORDER BY id'):
        return self.SELECT + whereStr + orderByStr
    
    def __init__(self, dbName, timeout=1000):
        self.__createConnection(dbName, timeout)
        self.__createTables()

    def __createConnection(self, dbName, timeout):
        """Establish db connection"""
        from sqlite3 import dbapi2 as sqlite
        self.connection = sqlite.Connection(dbName, timeout, check_same_thread = False)
        self.connection.row_factory = sqlite.Row
        self.cursor = self.connection.cursor()
        # Define some shortcuts functions
        self.executeCommand = self.cursor.execute
        #self.executeCommand = self.__debugExecute
        self.commit = self.connection.commit
        
    def __debugExecute(self, *args):
        print args
        self.cursor.execute(*args)
        
    def __createTables(self):
        """Create required tables if don't exists"""
        # Enable foreings keys
        self.executeCommand("PRAGMA foreign_keys=ON")
        # Create the Objects table
        self.executeCommand("""CREATE TABLE IF NOT EXISTS Objects
                     (id        INTEGER PRIMARY KEY AUTOINCREMENT,
                      parent_id INTEGER REFERENCES Objects(id),
                      name      TEXT,                -- object name 
                      classname TEXT,                -- object's class name
                      value     TEXT DEFAULT NULL,   -- object value, used for Scalars
                      label     TEXT DEFAULT NULL,   -- object label, text used for display
                      comment   TEXT DEFAULT NULL    -- object comment, text used for annotations
                      )""")
        # Create the Relations table
        self.executeCommand("""CREATE TABLE IF NOT EXISTS Relations
                     (id        INTEGER PRIMARY KEY AUTOINCREMENT,
                      parent_id INTEGER REFERENCES Objects(id), -- object that created the relation
                      name      TEXT,               -- relation name 
                      classname TEXT DEFAULT NULL,  -- relation's class name
                      value     TEXT DEFAULT NULL,  -- relation value
                      label     TEXT DEFAULT NULL,  -- relation label, text used for display
                      comment   TEXT DEFAULT NULL,  -- relation comment, text used for annotations
                      object_parent_id  INTEGER REFERENCES Objects(id) ON DELETE CASCADE,
                      object_child_id  INTEGER REFERENCES Objects(id) ON DELETE CASCADE 
                      )""")
        self.commit()
        
    def insertObject(self, name, classname, value, parent_id, label, comment):
        """Execute command to insert a new object. Return the inserted object id"""
        try:
            self.executeCommand("INSERT INTO Objects (parent_id, name, classname, value, label, comment) VALUES (?, ?, ?, ?, ?, ?)",
                                (parent_id, name, classname, value, label, comment))
            return self.cursor.lastrowid
        except Exception, ex:
            print "insertObject: ERROR "
            print "INSERT INTO Objects (parent_id, name, classname, value, label, comment) VALUES (?, ?, ?, ?, ?, ?)", (parent_id, name, classname, value, label, comment)
            raise ex
        
    def insertRelation(self, relName, parent_id, object_parent_id, object_child_id, **args):
        """Execute command to insert a new object. Return the inserted object id"""
        self.executeCommand("INSERT INTO Relations (parent_id, name, object_parent_id, object_child_id) VALUES (?, ?, ?, ?)",
                            (parent_id, relName, object_parent_id, object_child_id))
        return self.cursor.lastrowid
    
    def insertRelationRow(self, row):
        """Execute command to insert a new object. Return the inserted object id"""
        return self.insertRelation(row['name'], row['parent_id'], 
                                   row['object_parent_id'], row['object_child_id'])
    
    def updateObject(self, objId, name, classname, value, parent_id, label, comment):
        """Update object data """
        self.executeCommand("UPDATE Objects SET parent_id=?, name=?,classname=?, value=?, label=?, comment=? WHERE id=?",
                            (parent_id, name, classname, value, label, comment, objId))
        
    def selectObjectById(self, objId):
        """Select an object give its id"""
        self.executeCommand(self.selectCmd("id=?"), (objId,))  
        return self.cursor.fetchone()
    
    def _iterResults(self):
        row = self.cursor.fetchone()
        while row is not None:
            yield row
            row = self.cursor.fetchone()
        
    def _results(self, iterate=False):
        """ Return the results to which cursor, point to. 
        If iterates=True, iterate yielding each result independenly"""
        if not iterate:
            return self.cursor.fetchall()
        else:
            return self._iterResults()
        
    def selectObjectsByParent(self, parent_id=None, iterate=False):
        """Select object with a given parent
        if the parent_id is None, all object with parent_id NULL
        will be returned"""
        if parent_id is None:
            self.executeCommand(self.selectCmd("parent_id is NULL"))
        else:
            self.executeCommand(self.selectCmd("parent_id=?"), (parent_id,))
        return self._results(iterate)  
    
    def selectObjectsByAncestor(self, ancestor_namePrefix, iterate=False):
        """Select all objects in the hierachy of ancestor_id"""
        self.executeCommand(self.selectCmd("name LIKE '%s.%%'" % ancestor_namePrefix))
        return self._results(iterate)          
    
    def selectObjectsBy(self, iterate=False, **args):     
        """More flexible select where the constrains can be passed
        as a dictionary, the concatenation is done by an AND"""
        whereList = ['%s=?' % k for k in args.keys()]
        whereStr = ' AND '.join(whereList)
        whereTuple = tuple(args.values())
        self.executeCommand(self.selectCmd(whereStr), whereTuple)
        return self._results(iterate)
    
    def selectObjectsWhere(self, whereStr, iterate=False):
        self.executeCommand(self.selectCmd(whereStr))
        return self._results(iterate)   
    
    def deleteObject(self, objId):
        """Delete an existing object"""
        self.executeCommand(self.DELETE + "id=?", (objId,))
        
    def deleteChildObjects(self, ancestor_namePrefix):
        """ Delete from db all objects that are childs 
        of an ancestor, now them will have the same starting prefix"""
        self.executeCommand(self.DELETE + "name LIKE '%s.%%'" % ancestor_namePrefix)
        
    def deleteAll(self):
        """ Delete all objects from the db. """
        self.executeCommand(self.DELETE + "1")
        
    def selectRelationChilds(self, relName, object_parent_id):
        self.executeCommand(self.SELECT_RELATION % ('child', 'parent'), 
                            (relName, object_parent_id))
        return self._results()
        
    def selectRelationParents(self, relName, object_child_id):
        self.executeCommand(self.SELECT_RELATION % ('parent', 'child'), 
                            (relName, object_child_id))
        return self._results()
    
    def selectRelationsByCreator(self, parent_id):
        self.executeCommand(self.SELECT_RELATIONS + "parent_id=?", (parent_id,))
        return self._results()
     
    def selectRelationsByName(self, relationName):
        self.executeCommand(self.SELECT_RELATIONS + "name=?", (relationName,))
        return self._results()
       
    def deleteRelationsByCreator(self, parent_id):
        self.executeCommand("DELETE FROM Relations where parent_id=?", (parent_id,))


class SqliteFlatMapper(Mapper):
    """Specific Flat Mapper implementation using Sqlite database"""
    def __init__(self, dbName, dictClasses=None, tablePrefix=''):
        Mapper.__init__(self, dictClasses)
        self._objTemplate = None
        try:
            self.db = SqliteFlatDb(dbName, tablePrefix)
            self.doCreateTables = self.db.missingTables()
            
            if not self.doCreateTables:
                self.__loadObjDict()
        except Exception, ex:
            raise Exception('Error creating SqliteFlatMapper, dbName: %s, tablePrefix: %s\n error: %s' % (dbName, tablePrefix, ex))
    
    def commit(self):
        self.db.commit()
        
    def close(self):
        self.db.close()
        
    def insert(self, obj):
        if self.doCreateTables:
            self.db.createTables(obj.getObjDict(includeClass=True))
            self.doCreateTables = False
        """Insert a new object into the system, the id will be set"""
        self.db.insertObject(obj.getObjId(), obj.getObjLabel(), obj.getObjComment(), 
                             *obj.getObjDict().values())
        
    def clear(self):
        self.db.clear()
        self.doCreateTables = True
    
    def deleteAll(self):
        """ Delete all objects stored """
        self.db.deleteAll()
                
    def delete(self, obj):
        """Delete an object and all its childs"""
        self.db.deleteObject(obj.getObjId())
    
    def updateTo(self, obj, level=1):
        """ Update database entry with new object values. """ 
        if self.db.INSERT_OBJECT is None:
            self.db.setupCommands(obj.getObjDict(includeClass=True))
        args = list(obj.getObjDict().values())
        args.append(obj.getObjId())
        self.db.updateObject(obj.getObjLabel(), obj.getObjComment(), *args)
            
    def selectById(self, objId):
        """Build the object which id is objId"""
        objRow = self.db.selectObjectById(objId)
        if objRow is None:
            obj = None
        else:
            obj = self.__objFromRow(objRow)
        return obj

    def __loadObjDict(self):
        """ Load object properties and classes from db. """
        # Create a template object for retrieving stored ones
        columnList = []
        rows = self.db.getClassRows()
        attrClasses = {}
        self._objBuildList = []
        
        for r in rows:
            label = r['label_property']

            if label == 'self':
                self._objClassName = r['class_name']
                self._objTemplate = self._buildObject(self._objClassName)
            else:
                columnList.append(label)
                attrClasses[label] = r['class_name']
                attrParts = label.split('.')
                attrJoin = ''
                o = self._objTemplate
                for a in attrParts:
                    attrJoin += a
                    attr = getattr(o, a, None)
                    if not attr:
                        className = attrClasses[attrJoin]
                        self._objBuildList.append((className, attrJoin.split('.')))
                        attr = self._buildObject(className)
                        setattr(o, a, attr)
                    o = attr
                    attrJoin += '.'
        n = len(rows) + 2
        self._objColumns = zip(range(3, n), columnList)  
         
    def __buildAndFillObj(self):
        obj = self._buildObject(self._objClassName)
        
        for className, attrParts in self._objBuildList:
            o = obj
            for a in attrParts:
                attr = getattr(o, a, None)
                if not attr:
                    setattr(o, a, self._buildObject(className))
                    break
                o = attr
        return obj
        
    def __objFromRow(self, objRow):
        if self._objTemplate is None:
            self.__loadObjDict()
            
        obj = self._objTemplate #self.__buildAndFillObj()
        obj.setObjId(objRow['id'])
        obj.setObjLabel(self._getStrValue(objRow['label']))
        obj.setObjComment(self._getStrValue(objRow['comment']))
        
        for c, attrName in self._objColumns:
            if attrName == '_mapperPath':
                #FIXME: this is a really dirty-dirty fix in order to 
                # continue with Ward protocol before fixing this bug
                obj._mapperPath.trace(obj.load)
                obj._mapperPath.set(objRow[c])
            else:
                obj.setAttributeValue(attrName, objRow[c])

        return obj
        
    def __iterObjectsFromRows(self, objRows, objectFilter=None):
        for objRow in objRows:
            obj = self.__objFromRow(objRow)
            if objectFilter is None or objectFilter(obj): 
                yield obj
        
    def __objectsFromRows(self, objRows, iterate=False, objectFilter=None):
        """Create a set of object from a set of rows
        Params:
            objRows: rows result from a db select.
            iterate: if True, iterates over all elements, if False the whole list is returned
            objectFilter: function to filter some of the objects of the results. 
        """
        if not iterate:
            return [obj.clone() for obj in self.__iterObjectsFromRows(objRows, objectFilter)]
        else:
            return self.__iterObjectsFromRows(objRows, objectFilter)
         
    def selectBy(self, iterate=False, objectFilter=None, **args):
        """Select object meetings some criterias"""
        objRows = self.db.selectObjectsBy(**args)
        return self.__objectsFromRows(objRows, iterate, objectFilter)
    
    def selectAll(self, iterate=True, objectFilter=None):        
        if self._objTemplate is None:
            self.__loadObjDict()
        objRows = self.db.selectAll()
        
        return self.__objectsFromRows(objRows, iterate, objectFilter)    
    
    def __objectsFromIds(self, objIds):
        """Return a list of objects, given a list of id's
        """
        return [self.selectById(rowId['id']) for rowId in objIds]
        

class SqliteFlatDb():
    """Class to handle a Sqlite database.
    It will create connection, execute queries and commands"""
    
    CLASS_MAP = {'Integer': 'INTEGER',
                 'Float': 'REAL',
                 'Boolean': 'INTEGER'
                 }
    OPEN_CONNECTIONS = {}
    
    def __init__(self, dbName, tablePrefix, timeout=1000):
        tablePrefix = tablePrefix.strip()
        if tablePrefix: # Avoid having _ for empty prefix
            tablePrefix += '_' 
        self.CHECK_TABLES = "SELECT name FROM sqlite_master WHERE type='table' AND name='%sObjects';" % tablePrefix
        self.SELECT = "SELECT * FROM %sObjects WHERE " % tablePrefix
        self.DELETE = "DELETE FROM %sObjects WHERE " % tablePrefix
        self.INSERT_CLASS = "INSERT INTO %sClasses (label_property, column_name, class_name) VALUES (?, ?, ?)" % tablePrefix
        self.SELECT_CLASS = "SELECT * FROM %sClasses;" % tablePrefix
        self.tablePrefix = tablePrefix
        self._dbName = dbName
        self.__createConnection(dbName, timeout)
        self.INSERT_OBJECT = None
        self.UPDATE_OBJECT = None 
        
    def close(self):
        self.connection.close()
        del self.OPEN_CONNECTIONS[self._dbName]
        
    def selectCmd(self, whereStr, orderByStr=' ORDER BY id'):
        return self.SELECT + whereStr + orderByStr
        
    def missingTables(self):
        """ Return True is the needed Objects and Classes table are not created yet. """
        self.executeCommand(self.CHECK_TABLES)
        result = self.cursor.fetchone()
        
        return result is None
        
    def __createConnection(self, dbName, timeout):
        """Establish db connection"""
        from sqlite3 import dbapi2 as sqlite
        if dbName in self.OPEN_CONNECTIONS:
            self.connection = self.OPEN_CONNECTIONS[dbName]
        else:
            self.connection = sqlite.Connection(dbName, timeout, check_same_thread=False)
            self.connection.row_factory = sqlite.Row
            self.OPEN_CONNECTIONS[dbName] = self.connection
        self.cursor = self.connection.cursor()
        # Define some shortcuts functions
        self.executeCommand = self.cursor.execute
        #self.executeCommand = self.__debugExecute
        self.commit = self.connection.commit
        
    def __debugExecute(self, *args):
        print "COMMAND: ", args[0]
        print "ARGUMENTS: ", args[1:]
        self.cursor.execute(*args)
        
    def clear(self):
        self.executeCommand("DROP TABLE IF EXISTS %sClasses;" % self.tablePrefix)
        self.executeCommand("DROP TABLE IF EXISTS %sObjects;" % self.tablePrefix)
        
    def createTables(self, objDict):
        """Create the Classes and Object table to store items of a Set.
        Each object will be stored in a single row.
        Each nested property of the object will be stored as a column value.
        """
        # Create the Classes table to store each column name and type
        self.executeCommand("""CREATE TABLE IF NOT EXISTS %sClasses
                     (id        INTEGER PRIMARY KEY AUTOINCREMENT,
                      label_property      TEXT UNIQUE, --object label                 
                      column_name TEXT UNIQUE,
                      class_name TEXT DEFAULT NULL  -- relation's class name
                      )""" % self.tablePrefix)
        CREATE_OBJECT_TABLE = """CREATE TABLE IF NOT EXISTS %sObjects
                     (id        INTEGER PRIMARY KEY,
                      label     TEXT DEFAULT NULL,   -- object label, text used for display
                      comment   TEXT DEFAULT NULL   -- object comment, text used for annotations
                      """ % self.tablePrefix
        c = 0
        for k, v in objDict.iteritems():
            colName = 'c%02d' % c
            className = v[0]
            c += 1
            self.executeCommand(self.INSERT_CLASS, (k, colName, className))
            if k != "self":
                CREATE_OBJECT_TABLE += ',%s  %s DEFAULT NULL' % (colName, self.CLASS_MAP.get(className, 'TEXT'))
        
        CREATE_OBJECT_TABLE += ')'
        # Create the Objects table
        self.executeCommand(CREATE_OBJECT_TABLE)
        self.commit()
        # Prepare the INSERT and UPDATE commands
        self.setupCommands(objDict)
        
    def setupCommands(self, objDict):
        """ Setup the INSERT and UPDATE commands base on the object dictionray. """
        self.INSERT_OBJECT = "INSERT INTO %sObjects (id, label, comment" % self.tablePrefix
        self.UPDATE_OBJECT = "UPDATE %sObjects SET label=?, comment=?" % self.tablePrefix 
        c = 0
        for k in objDict:
            colName = 'c%02d' % c
            c += 1
            if k != "self":
                self.INSERT_OBJECT += ',%s' % colName
                self.UPDATE_OBJECT += ', %s=?' % colName
        
        self.INSERT_OBJECT += ') VALUES (?,?' + ',?' * c + ')'
        self.UPDATE_OBJECT += ' WHERE id=?'
        
    def getClassRows(self):
        """ Create a dictionary with names of the attributes
        of the colums. """
        self.executeCommand(self.SELECT_CLASS)
        return self._results(iterate=False)
   
    def insertObject(self, *args):
        """Insert a new object as a row.
        *args: id, label, comment, ...
        where ... is the values of the objDict from which the tables where created.        
        """
        self.executeCommand(self.INSERT_OBJECT, args)

    def updateObject(self, *args):
        """Update object data """
        self.executeCommand(self.UPDATE_OBJECT, args)
        
    def selectObjectById(self, objId):
        """Select an object give its id"""
        self.executeCommand(self.selectCmd("id=?"), (objId,))  
        return self.cursor.fetchone()
    
    def _iterResults(self):
        row = self.cursor.fetchone()
        while row is not None:
            yield row
            row = self.cursor.fetchone()
        
    def _results(self, iterate=False):
        """ Return the results to which cursor, point to. 
        If iterates=True, iterate yielding each result independenly"""
        if not iterate:
            return self.cursor.fetchall()
        else:
            return self._iterResults()
    
    def selectAll(self, iterate=True):
        self.executeCommand(self.selectCmd('1'))
        return self._results(iterate)
    
    def selectObjectsBy(self, iterate=False, **args):     
        """More flexible select where the constrains can be passed
        as a dictionary, the concatenation is done by an AND"""
        whereList = ['%s=?' % k for k in args.keys()]
        whereStr = ' AND '.join(whereList)
        whereTuple = tuple(args.values())
        self.executeCommand(self.selectCmd(whereStr), whereTuple)
        return self._results(iterate)
    
    def selectObjectsWhere(self, whereStr, iterate=False):
        self.executeCommand(self.selectCmd(whereStr))
        return self._results(iterate)   
    
    def deleteObject(self, objId):
        """Delete an existing object"""
        self.executeCommand(self.DELETE + "id=?", (objId,))
        
    def deleteAll(self):
        """ Delete all objects from the db. """
        if not self.missingTables():
            self.executeCommand(self.DELETE + "1")
        
