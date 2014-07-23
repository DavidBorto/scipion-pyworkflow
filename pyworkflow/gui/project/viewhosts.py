#!/usr/bin/env python
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
Main project window application
"""
import os, sys
from os.path import join, exists, basename

import Tkinter as tk
import ttk
import tkFont

from pyworkflow.gui.tree import TreeProvider, BoundTree
from pyworkflow.protocol.protocol import *

import pyworkflow as pw
from pyworkflow.hosts import HostConfig
from pyworkflow.object import *
from pyworkflow.em import *
from pyworkflow.protocol import *
from pyworkflow.protocol.params import *
from pyworkflow.mapper import SqliteMapper, XmlMapper
from pyworkflow.project import Project
from pyworkflow.utils.properties import Message, Icon, Color

import pyworkflow.gui as gui
from pyworkflow.gui import getImage
from pyworkflow.gui.tree import Tree, ObjectTreeProvider, DbTreeProvider
from pyworkflow.gui.form import FormWindow
from pyworkflow.gui.dialog import askYesNo, showInfo, showError
from pyworkflow.gui.text import Text
from pyworkflow.gui import Canvas
from pyworkflow.gui.graph import LevelTree

from config import *
#TODO: MOVE BROWSER TO A LIBRARY
from pyworkflow.apps.pw_browser import BrowserWindow

ACTION_NEW = Message.LABEL_NEW
ACTION_EDIT = Message.LABEL_EDIT
ACTION_COPY = Message.LABEL_COPY
ACTION_DELETE = Message.LABEL_DELETE

ActionIcons = {
    ACTION_NEW: Icon.ACTION_NEW,
    ACTION_EDIT:  Icon.ACTION_EDIT,
    ACTION_COPY:  Icon.ACTION_COPY,
    ACTION_DELETE:  Icon.ACTION_DELETE,
               }


class HostsTreeProvider(TreeProvider):
    """Provide runs info to populate tree"""
    def __init__(self, settings):
        self.getObjects = lambda: settings.getHosts()
        
    def getColumns(self):
        return [('Label', 100), ('Hostname', 200), ('User', 60), ('Path', 200)]
    
    def getObjectInfo(self, obj):
        return {'key': obj.getObjId(),
                'text': ' ' + obj.getLabel(),
                'image': Icon.BUTTON_PC,
                'values': (obj.getHostName(), obj.getUserName(),
                           obj.getHostPath())}
      
    
class HostsView(tk.Frame):
    def __init__(self, parent, windows, **args):
        tk.Frame.__init__(self, parent, **args)
        # Load global configuration
        self.selectedHost = None
        self.windows = windows
        #self.hostsMapper = windows.getHostsMapper()
        self.settings = windows.getSettings()
        self.getImage = windows.getImage
        
        self.createContent()
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        
        
    def createContent(self):
        """ Create the Hosts list. """

        # Create the Action Buttons TOOLBAR
        toolbar = tk.Frame(self)
        toolbar.grid(row=0, column=0, sticky='nw', pady=(5,0))
        #gui.configureWeigths(toolbar)
        #toolbar.columnconfigure(0, weight=1)
        toolbar.columnconfigure(1, weight=1)
        
        self.createActionToolbar(toolbar)

        # Create the Run History tree
        hostsFrame = ttk.Labelframe(self, text=Message.LABEL_HOSTS_ACTION, width=500, height=500)
        hostsFrame.grid(row=1, column=0, sticky='news', pady=5)
        self.hostsTree = self.createHostsTree(hostsFrame)        
        gui.configureWeigths(hostsFrame)
        
    def refresh(self, e=None):
        """ Refresh the hosts lists. """
        self.hostsTree.update()
        
    def createActionToolbar(self, toolbar):
        """ Prepare the buttons that will be available for protocol actions. """
       
        self.actionList = [ACTION_NEW, ACTION_EDIT, ACTION_COPY, ACTION_DELETE]
        self.actionButtons = {}
        
        def addButton(action, col, toolbar):
            btn = tk.Label(toolbar, text=action, image=self.getImage(ActionIcons[action]), 
                       compound=tk.LEFT, cursor='hand2')
            btn.bind('<Button-1>', lambda e: self._hostActionClick(action))
            btn.grid(row=0, column=col, padx=(5, 0), sticky='nw')
        
        for i, action in enumerate(self.actionList):
            self.actionButtons[action] = addButton(action, i, toolbar)
            
       
    def createHostsTree(self, parent):
        self.provider = HostsTreeProvider(self.settings) 
        tree = BoundTree(parent, self.provider)
        tree.grid(row=0, column=0, sticky='news')
        tree.bind('<Double-1>', self._hostItemDoubleClick)
        #tree.bind("<Button-3>", self._onRightClick)
        tree.bind('<<TreeviewSelect>>', self._hostItemClick)
        return tree
        
    def _hostItemClick(self, e=None):
        # Get last selected item for tree or graph
        self.selectedHost = self.settings.getHostById(int(self.hostsTree.getFirst()))
        
    def _hostItemDoubleClick(self, e=None):
        self._hostActionClick(ACTION_EDIT)
        
    def _openHostForm(self, host):
        """Open the Protocol GUI Form given a Protocol instance"""
        w = HostWindow(host, self.windows, saveCallback=self._saveHost)
        w.show(center=True)
        
    def _saveHost(self, host):
        self.settings.saveHost(host, commit=True)
        self.hostsTree.after(1000, self.refresh)
        
    def _deleteHost(self, host):
        if askYesNo(Message.TITLE_HOST_DELETE_FORM, 
                    Message.LABEL_HOST_DELETE_FORM + "(%s)" % host.getLabel(),
                    self.windows.root):
            self.setting.delete(host, commit=True)
            self.refresh()
        
    def _hostActionClick(self, action):
        host = self.selectedHost
        if host or action == ACTION_NEW:
            if action == ACTION_DELETE:
                self._deleteHost(host)
            else:                
                if action == ACTION_NEW:
                    newHost = HostConfig()
                elif action == ACTION_COPY:
                    newHost = host.clone()
                elif action == ACTION_EDIT:
                    newHost = host
                self._openHostForm(newHost)
                
                
class HostWindow(gui.Window):
    """ Form Windows to edit a host config. """
    
    def __init__(self, host, master=None, saveCallback=None):
        
        gui.Window.__init__(self, "host window", master, icon=master.icon, minsize=(700,500))
        self.host = host
        self.font = tkFont.Font(size=10, family='helvetica')#, weight='bold')
        self.varsDict = []
        self.saveCallback = saveCallback
        
        frame = tk.Frame(self.root)
        frame.grid(row=0, column=0, sticky='news')
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)
        self._createHeader(frame)
        self._createContent(frame)
        self._createButtons(frame)    
        
        
    def _createHeader(self, parent):
        bgColor = gui.cfgButtonBgColor
        self.headerFrame = tk.Frame(parent, bd=2, relief=tk.RAISED, bg=bgColor)
        self.headerFrame.grid(row=0, column=0, sticky='new')
        gui.configureWeigths(self.headerFrame)
        self.headerFrame.columnconfigure(1, weight=1)
        #self.headerFrame.columnconfigure(2, weight=1)
        self.headerLabel = tk.Label(self.headerFrame, text=self.host.getLabel(), fg='white', bg=bgColor)
        self.headerLabel.grid(row=0, column=0, sticky='nw', padx=5)
     
    def _createContent(self, parent):
        self.contentFrame = tk.Frame(parent, bg='white', bd=0)
        self.contentFrame.grid(row=1, column=0, sticky='news', padx=5, pady=5)
        self.contentFrame.columnconfigure(0, weight=1)
        self.contentFrame.columnconfigure(1, weight=4)
        
        self.tags = {'password': 'pass',
                     'submitTemplate': 'text'}
        
        i = 0
        for name, attr in self.host.getAttributesToStore():
            if isinstance(attr, String):
                self._addLabelValue(self.contentFrame, attr, name, i)
                i += 1
            
        self.queueFrame = ttk.Label(self.contentFrame, text='Queue System')
        self.queueFrame.grid(row=i, column=0, columnspan=3, sticky='news', 
                             padx=5, pady=5)
        i += 1
        
        for name, attr in self.host.queueSystem.getAttributesToStore():
            if isinstance(attr, String):
                self._addLabelValue(self.contentFrame, attr, name, i)
                i += 1
                
    def _createButtons(self, parent):
        self.buttonsFrame = tk.Frame(parent)
        self.buttonsFrame.grid(row=2, column=0, sticky='news', padx=5, pady=5)
        self.buttonsFrame.columnconfigure(2, weight=1)
        #self.buttonsFrame.columnconfigure(1, weight=4)
        
        btnClose = tk.Button(self.buttonsFrame, text=Message.LABEL_BUTTON_CLOSE, image=self.getImage(Icon.BUTTON_CLOSE), compound=tk.LEFT, font=self.font,
                          command=self.close)
        btnClose.grid(row=0, column=0, padx=5, sticky='sw')
        btnSave = tk.Button(self.buttonsFrame, text=Message.LABEL_BUTTON_SAVE, image=self.getImage(Icon.BUTTON_SAVE), compound=tk.LEFT, font=self.font, 
                          command=self._save)
        btnSave.grid(row=0, column=1, padx=5, sticky='sw')
        
        btnTest = tk.Button(self.buttonsFrame, text='Test configuration', fg='white', bg=Color.RED_COLOR , font=self.font, 
                        activeforeground='white', activebackground='#A60C0C', command=self._testConfig)
        btnTest.grid(row=0, column=2, padx=5, sticky='se')
        
        
    def _addLabelValue(self, parent, attr, key, row):
        label = tk.Label(parent, text=key, bg='white')
        label.grid(row=row, column=0, sticky='ne', padx=5, pady=3)
        value = attr.get('')
        args = {}
        tag = self.tags.get(key, '')
        if  tag == 'text':
            entry = Text(parent, height=15)
            entry.addText(value)
            entry.setReadOnly(False)
            entry.tag_configure("red", foreground="#ff0000")
            entry.highlight("%\(\w+\)\w", "red", '1.0', 'end', regexp=True)
            self.queueText = entry
        else:
            if tag == 'pass':
                args['show'] = '*'
            if key.endswith('Command') or key.endswith('Path'):
                args['width'] = 60
            var = tk.StringVar()
            var.set(value)
            entry = tk.Entry(parent, textvariable=var, **args)
            self.varsDict.append((attr, var))
        entry.grid(row=row, column=1, sticky='nw', padx=5, pady=3)
        
    def _save(self, e=None):
        for attr, var in self.varsDict:
            attr.set(var.get())
        self.host.queueSystem.submitTemplate.set(self.queueText.getText())
        if self.saveCallback:
            try:
                self.saveCallback(self.host)                
                showInfo(Message. TITLE_HOST_SAVE_FORM, Message.LABEL_HOST_SAVE_FORM_SUCESS , self.root)
            except Exception, ex:
                showError(Message. TITLE_HOST_SAVE_FORM, Message.LABEL_HOST_SAVE_FORM_FAIL + "(%s)" % str(ex), self.root)

    def _testConfig(self, e=None):
        from pyworkflow.utils.remote import testHostConfig
        if testHostConfig(self.host):
            msg = Message.LABEL_HOST_CONECTION_SUCESS +"<%s>"
        else:
            msg = Message.LABEL_HOST_CONECTION_FAIL + "<%s>"
        showInfo(Message.LABEL_HOST_CONECTION_TEST, msg % self.host.getLabel(), self.root) 
        