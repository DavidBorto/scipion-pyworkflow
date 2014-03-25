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
"""
This module define a Graph class and some utilities 
"""

class Node(object):
    """ A node inside the graph. """
    _count = 1
    
    def __init__(self, name=None, label=None):
        self._childs = []
        self._parents = []
        
        if name is None:
            name = str(self._count)
            self._count += 1
        self._name = name
        
        if label is None:
            label = name
        self._label = label
        
    def getChilds(self):
        return self._childs
    
    def addChild(self, *nodes):
        for n in nodes:
            if not n in self._childs:
                self._childs.append(n)
                n._parents.append(self)
            
    def isRoot(self):
        return len(self._parents) == 0
    
    def getName(self):
        return self._name
    
    def getLabel(self):
        return self._label
    
    def setLabel(self, newLabel):
        self._label = newLabel
    
    def __str__(self):
        return self._name
    
    
class Graph(object):
    """Simple directed Graph class. 
    Implemented using adjacency lists.
    """
    
    def __init__(self, rootName='ROOT', root=None):
        self._nodes = []
        self._nodesDict = {} # To retrieve nodes from name
        if root is None:
            self._root = self.createNode(rootName)
        else:
            self._root = root
            self._registerNode(root)
            
    def _registerNode(self, node):
        self._nodes.append(node)
        self._nodesDict[node.getName()] = node
        for child in node.getChilds():
            self._registerNode(child)
        
    def getRoot(self):
        return self._root
    
    def createNode(self, nodeName, nodeLabel=None):
        """ Add a node to the graph """
        node = Node(nodeName, nodeLabel)
        self._registerNode(node)
        
        return node
    
    def getNode(self, nodeName):
        return self._nodesDict.get(nodeName, None)
    
    def getNodes(self):
        return self._nodes
    
    def getRootNodes(self):
        """ Return all nodes that have no parent. """
        return [n for n in self._nodes if n.isRoot()]
    
    def printNodes(self):
        for node in self.getNodes():
            print "Node: ", node
            print " Childs: ", ','.join([str(c) for c in node.getChilds()])
            
    def _escape(self, label):
        return label.replace('.', '_').replace(' ', '_')
    
    def printDot(self):
        print "\ndigraph {"
        for node in self.getNodes():
            for child in node.getChilds():
                print "   %s -> %s; " % (self._escape(node.label), self._escape(child.label))
        print "}"
        