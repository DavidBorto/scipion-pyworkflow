#!/usr/bin/env python
# **************************************************************************
# *
# * Authors:     J.M. De la Rosa Trevin (delarosatrevin@scilifelab.se) [1]
# *
# * [1] SciLifeLab, Stockholm University
# *
# * This program is free software: you can redistribute it and/or modify
# * it under the terms of the GNU General Public License as published by
# * the Free Software Foundation, either version 3 of the License, or
# * (at your option) any later version.
# *
# * This program is distributed in the hope that it will be useful,
# * but WITHOUT ANY WARRANTY; without even the implied warranty of
# * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# * GNU General Public License for more details.
# *
# * You should have received a copy of the GNU General Public License
# * along with this program.  If not, see <https://www.gnu.org/licenses/>.
# *
# *  All comments concerning this program package may be sent to the
# *  e-mail address 'scipion@cnb.csic.es'
# *
# **************************************************************************
from configparser import ConfigParser

from pyworkflow.project import MenuConfig
from pyworkflow import Config

INIT_REFRESH_SECONDS = 3

"""
View with the protocols inside the main project window.
"""

import os
import json
import re
import tempfile
from collections import OrderedDict
import tkinter as tk
import tkinter.ttk as ttk
import datetime as dt

import pyworkflow.object as pwobj
import pyworkflow.utils as pwutils
import pyworkflow.protocol as pwprot
import pyworkflow.gui as pwgui
from pyworkflow.gui.dialog import askColor, FloatingMessage
from pyworkflow.viewer import DESKTOP_TKINTER, ProtocolViewer
from pyworkflow.utils.properties import Message, Icon, Color, KEYSYM
from pyworkflow.gui.project.utils import getStatusColorFromNode
from pyworkflow.gui.form import FormWindow
from pyworkflow.webservices import WorkflowRepository

DEFAULT_BOX_COLOR = '#f8f8f8'

ACTION_EDIT = Message.LABEL_EDIT
ACTION_RENAME = Message.LABEL_RENAME
ACTION_SELECT_TO = Message.LABEL_SELECT_TO
ACTION_COPY = Message.LABEL_COPY
ACTION_DELETE = Message.LABEL_DELETE
ACTION_REFRESH = Message.LABEL_REFRESH
ACTION_STEPS = Message.LABEL_STEPS
ACTION_BROWSE = Message.LABEL_BROWSE
ACTION_DB = Message.LABEL_DB
ACTION_TREE = Message.LABEL_TREE
ACTION_LIST = Message.LABEL_LIST
ACTION_STOP = Message.LABEL_STOP
ACTION_DEFAULT = Message.LABEL_DEFAULT
ACTION_CONTINUE = Message.LABEL_CONTINUE
ACTION_RESULTS = Message.LABEL_ANALYZE
ACTION_EXPORT = Message.LABEL_EXPORT
ACTION_EXPORT_UPLOAD = Message.LABEL_EXPORT_UPLOAD
ACTION_SWITCH_VIEW = 'Switch_View'
ACTION_COLLAPSE = 'Collapse'
ACTION_EXPAND = 'Expand'
ACTION_LABELS = 'Labels'
ACTION_RESTART_WORKFLOW = Message.LABEL_RESTART_WORKFLOW
ACTION_CONTINUE_WORKFLOW = Message.LABEL_CONTINUE_WORKFLOW
ACTION_STOP_WORKFLOW = Message.LABEL_STOP_WORKFLOW
ACTION_RESET_WORKFLOW = Message.LABEL_RESET_WORKFLOW

RUNS_TREE = Icon.RUNS_TREE
RUNS_LIST = Icon.RUNS_LIST

VIEW_LIST = 0
VIEW_TREE = 1
VIEW_TREE_SMALL = 2

ActionIcons = {
    ACTION_EDIT: Icon.ACTION_EDIT,
    ACTION_SELECT_TO: Icon.ACTION_SELECT_TO,
    ACTION_COPY: Icon.ACTION_COPY,
    ACTION_DELETE: Icon.ACTION_DELETE,
    ACTION_REFRESH: Icon.ACTION_REFRESH,
    ACTION_RENAME: Icon.ACTION_RENAME,
    ACTION_STEPS: Icon.ACTION_STEPS,
    ACTION_BROWSE: Icon.ACTION_BROWSE,
    ACTION_DB: Icon.ACTION_DB,
    ACTION_TREE: None,  # should be set
    ACTION_LIST: Icon.ACTION_LIST,
    ACTION_STOP: Icon.ACTION_STOP,
    ACTION_CONTINUE: Icon.ACTION_CONTINUE,
    ACTION_RESULTS: Icon.ACTION_RESULTS,
    ACTION_EXPORT: Icon.ACTION_EXPORT,
    ACTION_EXPORT_UPLOAD: Icon.ACTION_EXPORT_UPLOAD,
    ACTION_COLLAPSE: 'fa-minus-square.gif',
    ACTION_EXPAND: 'fa-plus-square.gif',
    ACTION_LABELS: Icon.TAGS,
    ACTION_RESTART_WORKFLOW: Icon.ACTION_EXECUTE,
    ACTION_CONTINUE_WORKFLOW: Icon.ACTION_CONTINUE,
    ACTION_STOP_WORKFLOW: Icon.ACTION_STOP_WORKFLOW,
    ACTION_RESET_WORKFLOW: Icon.ACTION_REFRESH
}


class RunsTreeProvider(pwgui.tree.ProjectRunsTreeProvider):
    """Provide runs info to populate tree"""

    def __init__(self, project, actionFunc):
        pwgui.tree.ProjectRunsTreeProvider.__init__(self, project)
        self.actionFunc = actionFunc
        self._selection = project.getSettings().runSelection

    def getActionsFromSelection(self):
        """ Return the list of options available for selection. """
        n = len(self._selection)
        single = n == 1
        if n:
            prot = self.project.getProtocol(self._selection[0])
            status = prot.getStatus()
            nodeInfo = self.project.getSettings().getNodeById(prot.getObjId())
            expanded = nodeInfo.isExpanded() if nodeInfo else True
        else:
            status = None

        stoppable = status in [pwprot.STATUS_RUNNING, pwprot.STATUS_SCHEDULED, 
                               pwprot.STATUS_LAUNCHED]

        return [(ACTION_EDIT, single),
                (ACTION_RENAME, single),
                (ACTION_COPY, True),
                (ACTION_DELETE, status != pwprot.STATUS_RUNNING),
                (ACTION_STEPS, single and Config.debugOn()),
                (ACTION_BROWSE, single),
                (ACTION_DB, single and Config.debugOn()),
                (ACTION_STOP, stoppable and single),
                (ACTION_EXPORT, not single),
                (ACTION_EXPORT_UPLOAD, not single),
                (ACTION_COLLAPSE, single and status and expanded),
                (ACTION_EXPAND, single and status and not expanded),
                (ACTION_LABELS, True),
                (ACTION_SELECT_TO, True),
                (ACTION_RESTART_WORKFLOW, single),
                (ACTION_CONTINUE_WORKFLOW, single),
                (ACTION_STOP_WORKFLOW, single),
                (ACTION_RESET_WORKFLOW, single)
                ]

    def getObjectActions(self, obj):

        def addAction(actionLabel):
            if actionLabel:
                text = actionLabel
                action = actionLabel
                actionLabel = (text, lambda: self.actionFunc(action),
                               ActionIcons.get(action, None))
            return actionLabel

        actions = [addAction(a)
                   for a, cond in self.getActionsFromSelection() if cond]

        if hasattr(obj, 'getActions'):
            for text, action in obj.getActions():
                actions.append((text, action, None))

        return actions


class ProtocolTreeProvider(pwgui.tree.ObjectTreeProvider):
    """Create the tree elements for a Protocol run"""

    def __init__(self, protocol):
        self.protocol = protocol
        # This list is create to group the protocol parameters
        # in the tree display
        self.status = pwobj.List(objName='_status')
        self.params = pwobj.List(objName='_params')
        self.statusList = ['status', 'initTime', 'endTime', 'error',
                           'interactive', 'mode']

        objList = [] if protocol is None else [protocol]
        pwgui.tree.ObjectTreeProvider.__init__(self, objList)


class StepsTreeProvider(pwgui.tree.TreeProvider):
    """Create the tree elements for a Protocol run"""

    def __init__(self, stepsList):
        for i, s in enumerate(stepsList):
            if not s._index:
                s._index = i + 1

        self._stepsList = stepsList
        self.getColumns = lambda: [('Index', 50), ('Step', 200),
                                   ('Time', 150), ('Class', 100)]
        self._parentDict = {}

    def getObjects(self):
        return self._stepsList

    @staticmethod
    def getObjectInfo(obj):
        info = {'key': obj._index,
                'values': (str(obj), pwutils.prettyDelta(obj.getElapsedTime()),
                           obj.getClassName())}
        return info

    @staticmethod
    def getObjectPreview(obj):

        args = json.loads(obj.argsStr.get())
        msg = "*Prerequisites*: %s \n" % str(obj._prerequisites)
        msg += "*Arguments*: " + '\n  '.join([str(a) for a in args])
        if hasattr(obj, 'resultFiles'):
            results = json.loads(obj.resultFiles.get())
            if len(results):
                msg += "\n*Result files:* " + '\n  '.join(results)

        return None, msg


class StepsWindow(pwgui.browser.BrowserWindow):
    def __init__(self, title, parentWindow, protocol, **args):
        self._protocol = protocol
        provider = StepsTreeProvider(protocol.loadSteps())
        pwgui.browser.BrowserWindow.__init__(self, title, parentWindow,
                                             weight=False, **args)
        # Create buttons toolbar
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = tk.Frame(self.root)
        toolbar.grid(row=0, column=0, sticky='nw', padx=5, pady=5)
        btn = tk.Label(toolbar, text="Tree",
                       image=self.getImage(Icon.RUNS_TREE),
                       compound=tk.LEFT, cursor='hand2')
        btn.bind('<Button-1>', self._showTree)
        btn.grid(row=0, column=0, sticky='nw')
        # Create and set browser
        browser = pwgui.browser.ObjectBrowser(self.root, provider,
                                              showPreviewTop=False)
        self.setBrowser(browser, row=1, column=0)

    # noinspection PyUnusedLocal
    def _showTree(self, e=None):
        g = self._protocol.getStepsGraph()
        w = pwgui.Window("Protocol steps", self, minsize=(800, 600))
        root = w.root
        canvas = pwgui.Canvas(root, width=600, height=500,
                              tooltipCallback=self._stepTooltip,)
        canvas.grid(row=0, column=0, sticky='nsew')
        canvas.drawGraph(g, pwgui.LevelTreeLayout())
        w.show()

    def _stepTooltip(self, tw, item):
        """ Create the contents of the tooltip to be displayed
        for the given step.
        Params:
            tw: a tk.TopLevel instance (ToolTipWindow)
            item: the selected step.
        """

        if not hasattr(item.node, 'step'):
            return

        step = item.node.step

        tm = str(step.funcName)

        if not hasattr(tw, 'tooltipText'):
            frame = tk.Frame(tw)
            frame.grid(row=0, column=0)
            tw.tooltipText = pwgui.dialog.createMessageBody(
                frame, tm, None, textPad=0, textBg=Color.LIGHT_GREY_COLOR_2)
            tw.tooltipText.config(bd=1, relief=tk.RAISED)
        else:
            pwgui.dialog.fillMessageText(tw.tooltipText, tm)


class SearchProtocolWindow(pwgui.Window):
    def __init__(self, parentWindow, **kwargs):
        pwgui.Window.__init__(self, title="Search for a protocol",
                              masterWindow=parentWindow)
        content = tk.Frame(self.root, bg='white')
        self._createContent(content)
        content.grid(row=0, column=0, sticky='news')
        content.columnconfigure(0, weight=1)
        content.rowconfigure(1, weight=1)

    def _createContent(self, content):
        self._createSearchBox(content)
        self._createResultsBox(content)

    def _createSearchBox(self, content):
        """ Create the Frame with Search widgets """
        frame = tk.Frame(content, bg='white')

        label = tk.Label(frame, text="Search", bg='white')
        label.grid(row=0, column=0, sticky='nw')
        self._searchVar = tk.StringVar()
        entry = tk.Entry(frame, bg='white', textvariable=self._searchVar)
        entry.bind('<Return>', self._onSearchClick)
        entry.bind('<KP_Enter>', self._onSearchClick)
        entry.focus_set()
        entry.grid(row=0, column=1, sticky='nw')
        btn = pwgui.widgets.IconButton(frame, "Search",
                                       imagePath=Icon.ACTION_SEARCH,
                                       command=self._onSearchClick)
        btn.grid(row=0, column=2, sticky='nw')

        frame.grid(row=0, column=0, sticky='new', padx=5, pady=(10, 5))

    def _createResultsBox(self, content):
        frame = tk.Frame(content, bg=Color.LIGHT_GREY_COLOR, padx=5, pady=5)
        pwgui.configureWeigths(frame)
        self._resultsTree = self.master.getViewWidget()._createProtocolsTree(
            frame, show=None, columns=("protocol", "streaming", "installed", "help", "score"))
        self._configureTreeColumns()
        self._resultsTree.grid(row=0, column=0, sticky='news')
        frame.grid(row=1, column=0, sticky='news', padx=5, pady=5)

    def _configureTreeColumns(self):
        self._resultsTree.column('#0', width=0, stretch=tk.FALSE)
        self._resultsTree.column('protocol', width=300, stretch=tk.FALSE)
        self._resultsTree.column('streaming', width=100, stretch=tk.FALSE)
        self._resultsTree.column('installed', width=110, stretch=tk.FALSE)
        self._resultsTree.column('help', minwidth=300, stretch=tk.YES)
        self._resultsTree.column('score', width=50, stretch=tk.FALSE)
        self._resultsTree.heading('protocol', text='Protocol', command=lambda: self._resultsTree.sortByColumn("protocol", False))
        self._resultsTree.heading('streaming', text='Streamified', command=lambda: self._resultsTree.sortByColumn("streaming", False))
        self._resultsTree.heading('installed', text='Installation', command=lambda: self._resultsTree.sortByColumn("installed", False))
        self._resultsTree.heading('help', text='Help', command=lambda: self._resultsTree.sortByColumn("help", False))
        self._resultsTree.heading('score', text='Score', command=lambda: self._resultsTree.sortByColumn("score", False, casting=int))

    def _onSearchClick(self, e=None):
        self._resultsTree.clear()
        keyword = self._searchVar.get().lower().strip()
        emProtocolsDict = Config.getDomain().getProtocols()
        protList = []

        def addSearchWeight(line2Search, searchtext):
            # Adds a weight value for the search
            weight = 0

            # prioritize findings in label
            if searchtext in line2Search[1]:
                weight += 10

            for value in line2Search[2:]:
                weight += 5 if searchtext in value else 0

            if " " in searchtext:
                for word in searchtext.split():
                    if word in line2Search[1]:
                        weight += 3

                    for value in line2Search[2:]:
                        weight += 1 if word in value else 0

            return line2Search + (weight,)

        for key, prot in emProtocolsDict.items():
            if ProtocolTreeConfig.isAFinalProtocol(prot, key):
                label = prot.getClassLabel().lower()
                line = (key, label,
                        "installed" if prot.isInstalled() else "missing installation",
                        prot.getHelpText().strip().replace('\r', '').replace('\n', '').lower(),
                        "streamified" if prot.worksInStreaming() else "static")

                line = addSearchWeight(line, keyword)
                # something was found: weight > 0
                if line[5] != 0:
                    protList.append(line)

        # Sort by weight
        protList.sort(reverse=True, key=lambda x: x[5])

        for key, label, installed, help, streamified, weight in protList:
            tag = ProtocolTreeConfig.getProtocolTag(installed == 'installed')
            self._resultsTree.insert(
                '', 'end', key, text="", tags=tag,
                values=(label, streamified, installed, help, weight))


class RunIOTreeProvider(pwgui.tree.TreeProvider):
    """Create the tree elements from a Protocol Run input/output childs"""

    def __init__(self, parent, protocol, mapper):
        # TreeProvider.__init__(self)
        self.parent = parent
        self.protocol = protocol
        self.mapper = mapper

    @staticmethod
    def getColumns():
        return [('Attribute', 200), ('Info', 100)]

    def getObjects(self):
        objs = []
        if self.protocol:
            # Store a dict with input parents (input, PointerList)
            self.inputParentDict = OrderedDict()
            inputs = []
            inputObj = pwobj.String(Message.LABEL_INPUT)
            inputObj._icon = Icon.ACTION_IN
            self.inputParentDict['_input'] = inputObj
            inputParents = [inputObj]

            for key, attr in self.protocol.iterInputAttributes():
                attr._parentKey = key
                # Repeated keys means there are inside a pointerList
                # since the same key is yielded for all items inside
                # so update the parent dict with a new object
                if key in self.inputParentDict:
                    if self.inputParentDict[key] == inputObj:
                        parentObj = pwobj.String(key)
                        parentObj._icon = Icon.ACTION_IN
                        parentObj._parentKey = '_input'
                        inputParents.append(parentObj)
                        self.inputParentDict[key] = parentObj
                else:
                    self.inputParentDict[key] = inputObj
                inputs.append(attr)

            outputs = [attr for _, attr in
                       self.protocol.iterOutputAttributes()]
            self.outputStr = pwobj.String(Message.LABEL_OUTPUT)
            objs = inputParents + inputs + [self.outputStr] + outputs
        return objs

    def _visualizeObject(self, ViewerClass, obj):
        viewer = ViewerClass(project=self.protocol.getProject(),
                             protocol=self.protocol,
                             parent=self.parent.windows)
        viewer.visualize(obj)

    def _editObject(self, obj):
        """Open the Edit GUI Form given an instance"""
        pwgui.dialog.EditObjectDialog(self.parent, Message.TITLE_EDIT_OBJECT,
                                      obj, self.mapper)

    def _deleteObject(self, obj):
        """ Remove unnecessary output, specially for Coordinates. """
        prot = self.protocol
        try:
            objLabel = self.getObjectLabel(obj, prot)
            if self.parent.windows.askYesNo("Delete object",
                                            "Are you sure to delete *%s* object?"
                                            % objLabel):
                prot.getProject().deleteProtocolOutput(prot, obj)
                self.parent._fillSummary()
                self.parent.windows.showInfo("Object *%s* successfully deleted."
                                             % objLabel)
        except Exception as ex:
            self.parent.windows.showError(str(ex))

    @staticmethod
    def getObjectPreview(obj):
        desc = "<name>: " + obj.getName()
        return None, desc

    def getObjectActions(self, obj):
        if isinstance(obj, pwobj.Pointer):
            obj = obj.get()
            isPointer = True
        else:
            isPointer = False
        actions = []

        viewers = Config.getDomain().findViewers(obj.getClassName(), DESKTOP_TKINTER)

        def viewerCallback(viewer):
            return lambda: self._visualizeObject(viewer, obj)

        for v in viewers:
            actions.append(('Open with %s' % v.__name__,
                            viewerCallback(v),
                            Icon.ACTION_VISUALIZE))
        # EDIT
        actions.append((Message.LABEL_EDIT,
                        lambda: self._editObject(obj),
                        Icon.ACTION_EDIT))
        # DELETE
        # Special case to allow delete outputCoordinates
        # since we can end up with several outputs and
        # we may want to clean up
        if self.protocol.allowsDelete(obj) and not isPointer:
            actions.append((Message.LABEL_DELETE_ACTION,
                            lambda: self._deleteObject(obj),
                            Icon.ACTION_DELETE))
        return actions

    @staticmethod
    def getObjectLabel(obj, parent):
        """ We will try to show in the list the string representation
        that is more readable for the user to pick the desired object.
        """
        label = 'None'
        if obj:
            label = obj.getObjLabel()
            if not len(label.strip()):
                parentLabel = parent.getObjLabel() if parent else 'None'
                label = "%s -> %s" % (parentLabel, obj.getLastName())
        return label

    def getObjectInfo(self, obj):
        if obj is None or not obj.hasValue():
            return None

        if isinstance(obj, pwobj.String):
            value = obj.get()
            info = {'key': value, 'text': value, 'values': '', 'open': True}
            if hasattr(obj, '_parentKey'):
                info['parent'] = self.inputParentDict[obj._parentKey]
        else:
            # All attributes are considered output, unless they are pointers
            image = Icon.ACTION_OUT
            parent = self.outputStr

            if isinstance(obj, pwobj.Pointer):
                name = obj.getLastName()
                # Remove ugly item notations inside lists
                name = name.replace('__item__000', '')
                # Consider Pointer as inputs
                image = getattr(obj, '_icon', '')
                parent = self.inputParentDict[obj._parentKey]

                suffix = ''
                if obj.hasExtended():
                    # getExtended method remove old attributes conventions.
                    extendedValue = obj.getExtended()
                    if obj.hasExtended():
                        suffix = '[%s]' % extendedValue
                    # else:
                    #     suffix = '[Item %s]' % extendedValue

                    # Tolerate loading projects:
                    # When having only the project sqlite..an obj.get() will
                    # the load of the set...and if it is missing this whole
                    # "thread" fails.
                    try:
                        if obj.get() is None:
                            labelObj = obj.getObjValue()
                            suffix = ''
                        else:
                            labelObj = obj.get()
                    except Exception as e:
                        return {'parent': parent, 'image': image, 'text': name,
                                'values': ("Couldn't read object attributes.",)}
                else:
                    labelObj = obj.get()

                objKey = obj._parentKey + str(labelObj.getObjId())
                label = self.getObjectLabel(labelObj,
                                            self.mapper.getParent(labelObj))
                name += '   (from %s %s)' % (label, suffix)
            else:
                name = self.getObjectLabel(obj, self.protocol)
                objKey = str(obj.getObjId())
                labelObj = obj

            # To tolerate str(labelObj) in case xmippLib is missing, but
            # still being able to open a project.
            try:
                value = str(labelObj)
            except Exception as e:
                print("Can not convert object %s - %s to string." % (objKey, name))
                value = str(e)

            info = {'key': objKey, 'parent': parent, 'image': image,
                    'text': name, 'values': (value,)}
        return info


# noinspection PyAttributeOutsideInit
class ProtocolsView(tk.Frame):
    """ What you see when the "Protocols" tab is selected.

    In the main project window there are three tabs: "Protocols | Data | Hosts".
    This extended tk.Frame is what will appear when Protocols is on.
    """

    RUNS_CANVAS_NAME = "runs_canvas"
    _protocolViews = None

    def __init__(self, parent, windows, **args):
        tk.Frame.__init__(self, parent, **args)
        # Load global configuration
        self.windows = windows
        self.project = windows.project
        self.domain = self.project.getDomain()
        self.root = windows.root
        self.getImage = windows.getImage
        self.protCfg = self.getCurrentProtocolView()
        self.settings = windows.getSettings()
        self.runsView = self.settings.getRunsView()
        self._loadSelection()
        self._items = {}
        self._lastSelectedProtId = None
        self._lastStatus = None
        self.selectingArea = False
        self._lastRightClickPos = None  # Keep last right-clicked position

        self.style = ttk.Style()
        self.root.bind("<F5>", self.refreshRuns)
        self.root.bind("<Control-f>", self._findProtocol)
        self.root.bind("<Control-a>", self._selectAllProtocols)
        self.root.bind("<Control-t>", self._toggleColorScheme)
        self.root.bind("<Control-d>", self._toggleDebug)
        if Config.debugOn():
            self.root.bind("<Control-i>", self._inspectProtocols)

        # To bind key press to methods
        # Listen to any key: send event to keyPressed method
        self.root.bind("<Key>", self.keyPressed)
        self.keybinds = dict()

        # Register key binds
        self._bindKeyPress(KEYSYM.DELETE, self._onDelPressed)

        self.__autoRefresh = None
        self.__autoRefreshCounter = INIT_REFRESH_SECONDS  # start by 3 secs

        c = self.createContent()
        pwgui.configureWeigths(self)
        c.grid(row=0, column=0, sticky='news')

    def _bindKeyPress(self, key, method):

        self.keybinds[key] = method

    def keyPressed(self, event):

        if event.keysym in self.keybinds:
            method = self.keybinds[event.keysym]

            method()

    def createContent(self):
        """ Create the Protocols View for the Project.
        It has two panes:
            Left: containing the Protocol classes tree
            Right: containing the Runs list
        """
        p = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg='white')
        bgColor = Color.LIGHT_GREY_COLOR
        # Left pane, contains Protocols Pane
        leftFrame = tk.Frame(p, bg=bgColor)
        leftFrame.columnconfigure(0, weight=1)
        leftFrame.rowconfigure(1, weight=1)

        # Protocols Tree Pane
        protFrame = tk.Frame(leftFrame, width=300, height=500, bg=bgColor)
        protFrame.grid(row=1, column=0, sticky='news', padx=5, pady=5)
        protFrame.columnconfigure(0, weight=1)
        protFrame.rowconfigure(1, weight=1)
        self._createProtocolsPanel(protFrame, bgColor)
        self.updateProtocolsTree(self.protCfg)
        # Create the right Pane that will be composed by:
        # a Action Buttons TOOLBAR in the top
        # and another vertical Pane with:
        # Runs History (at Top)

        # Selected run info (at Bottom)
        rightFrame = tk.Frame(p, bg='white')
        rightFrame.columnconfigure(0, weight=1)
        rightFrame.rowconfigure(1, weight=1)
        # rightFrame.rowconfigure(0, minsize=label.winfo_reqheight())

        # Create the Action Buttons TOOLBAR
        toolbar = tk.Frame(rightFrame, bg='white')
        toolbar.grid(row=0, column=0, sticky='news')
        pwgui.configureWeigths(toolbar)
        # toolbar.columnconfigure(0, weight=1)
        toolbar.columnconfigure(1, weight=1)

        self.runsToolbar = tk.Frame(toolbar, bg='white')
        self.runsToolbar.grid(row=0, column=0, sticky='sw')
        # On the left of the toolbar will be other
        # actions that can be applied to all runs (refresh, graph view...)
        self.allToolbar = tk.Frame(toolbar, bg='white')
        self.allToolbar.grid(row=0, column=10, sticky='se')
        self.createActionToolbar()

        # Create the Run History tree
        v = ttk.PanedWindow(rightFrame, orient=tk.VERTICAL)
        # runsFrame = ttk.Labelframe(v, text=' History ', width=500, height=500)
        runsFrame = tk.Frame(v, bg='white')
        # runsFrame.grid(row=1, column=0, sticky='news', pady=5)
        self.runsTree = self.createRunsTree(runsFrame)
        pwgui.configureWeigths(runsFrame)

        self.createRunsGraph(runsFrame)

        if self.runsView == VIEW_LIST:
            treeWidget = self.runsTree
        else:
            treeWidget = self.runsGraphCanvas

        treeWidget.grid(row=0, column=0, sticky='news')

        # Create the Selected Run Info
        infoFrame = tk.Frame(v)
        infoFrame.columnconfigure(0, weight=1)
        infoFrame.rowconfigure(1, weight=1)
        # Create the Analyze results button
        self.btnAnalyze = pwgui.Button(infoFrame, text=Message.LABEL_ANALYZE,
                                       fg='white', bg=Color.RED_COLOR,
                                       image=self.getImage(Icon.ACTION_VISUALIZE),
                                       compound=tk.LEFT,
                                       activeforeground='white',
                                       activebackground='#A60C0C',
                                       command=self._analyzeResultsClicked)
        self.btnAnalyze.grid(row=0, column=0, sticky='ne', padx=15)
        # self.style.configure("W.TNotebook")#, background='white')
        tab = ttk.Notebook(infoFrame)  # , style='W.TNotebook')

        # Summary tab
        dframe = tk.Frame(tab, bg='white')
        pwgui.configureWeigths(dframe, row=0)
        pwgui.configureWeigths(dframe, row=2)
        provider = RunIOTreeProvider(self, self.getSelectedProtocol(),
                                     self.project.mapper)

        rowheight = pwgui.getDefaultFont().metrics()['linespace']
        self.style.configure("NoBorder.Treeview", background='white',
                             borderwidth=0, font=self.windows.font,
                             rowheight=rowheight)
        self.infoTree = pwgui.browser.BoundTree(dframe, provider, height=6,
                                                show='tree',
                                                style="NoBorder.Treeview")
        self.infoTree.grid(row=0, column=0, sticky='news')
        label = tk.Label(dframe, text='SUMMARY', bg='white',
                         font=self.windows.fontBold)
        label.grid(row=1, column=0, sticky='nw', padx=(15, 0))

        hView = {'sci-open': self._viewObject,
                 'sci-bib': self._bibExportClicked}

        self.summaryText = pwgui.text.TaggedText(dframe, width=40, height=5,
                                                 bg='white', bd=0,
                                                 font=self.windows.font,
                                                 handlers=hView)
        self.summaryText.grid(row=2, column=0, sticky='news', padx=(30, 0))

        # Method tab
        mframe = tk.Frame(tab)
        pwgui.configureWeigths(mframe)
        # Methods text box
        self.methodText = pwgui.text.TaggedText(mframe, width=40, height=15,
                                                bg='white', handlers=hView)
        self.methodText.grid(row=0, column=0, sticky='news')
        # Reference export button
        # btnExportBib = pwgui.Button(mframe, text=Message.LABEL_BIB_BTN,
        #                             fg='white', bg=Color.RED_COLOR,
        #                             image=self.getImage(Icon.ACTION_BROWSE),
        #                             compound=tk.LEFT,
        #                             activeforeground='white',
        #                             activebackground='#A60C0C',
        #                             command=self._bibExportClicked)
        # btnExportBib.grid(row=2, column=0, sticky='w', padx=0)

        # Logs
        ologframe = tk.Frame(tab)
        pwgui.configureWeigths(ologframe)
        self.outputViewer = pwgui.text.TextFileViewer(ologframe, allowOpen=True,
                                                      font=self.windows.font)
        self.outputViewer.grid(row=0, column=0, sticky='news')
        self.outputViewer.windows = self.windows

        self._updateSelection()

        # Add all tabs

        tab.add(dframe, text=Message.LABEL_SUMMARY)
        tab.add(mframe, text=Message.LABEL_METHODS)
        tab.add(ologframe, text=Message.LABEL_LOGS_OUTPUT)
        #         tab.add(elogframe, text=Message.LABEL_LOGS_ERROR)
        #         tab.add(slogframe, text=Message.LABEL_LOGS_SCIPION)
        tab.grid(row=1, column=0, sticky='news')

        v.add(runsFrame, weight=1)
        v.add(infoFrame, weight=20)
        v.grid(row=1, column=0, sticky='news')

        # Add sub-windows to PanedWindows
        p.add(leftFrame, padx=0, pady=0, sticky='news')
        p.add(rightFrame, padx=0, pady=0)
        p.paneconfig(leftFrame, minsize=5)
        leftFrame.config(width=235)
        p.paneconfig(rightFrame, minsize=10)

        return p

    def _viewObject(self, objId):
        """ Call appropriate viewer for objId. """
        proj = self.project
        obj = proj.getObject(int(objId))
        viewerClasses = self.domain.findViewers(obj.getClassName(), DESKTOP_TKINTER)
        if not viewerClasses:
            return  # TODO: protest nicely
        viewer = viewerClasses[0](project=proj, parent=self.windows)
        viewer.visualize(obj)

    def _loadSelection(self):
        """ Load selected items, remove if some do not exists. """
        self._selection = self.settings.runSelection
        for protId in list(self._selection):

            if not self.project.doesProtocolExists(protId):
                self._selection.remove(protId)

    def _isMultipleSelection(self):
        return len(self._selection) > 1

    def _isSingleSelection(self):
        return len(self._selection) == 1

    def _noSelection(self):
        return len(self._selection) == 0

    # noinspection PyUnusedLocal
    def refreshRuns(self, e=None, initRefreshCounter=True, checkPids=False):
        """ Refresh the status of displayed runs.
         Params:
            e: Tk event input
            initRefreshCounter: if True the refresh counter will be set to 3 secs
             then only case when False is from _automaticRefreshRuns where the
             refresh time is doubled each time to avoid refreshing too often.
        """
        if Config.debugOn():
            import psutil
            proc = psutil.Process(os.getpid())
            mem = psutil.virtual_memory()
            print("------------- refreshing ---------- ")
            files = proc.open_files()
            print("  open files: ", len(files))
            for f in files:
                print("    - %s, %s" % (f.path, f.fd))
            print("  memory percent: ", proc.memory_percent())

        self.updateRunsGraph(True, checkPids=checkPids)
        self.updateRunsTree(False)

        if initRefreshCounter:

            self.__autoRefreshCounter = INIT_REFRESH_SECONDS  # start by 3 secs
            if self.__autoRefresh:
                self.runsTree.after_cancel(self.__autoRefresh)
                self.__autoRefresh = self.runsTree.after(
                    self.__autoRefreshCounter * 1000,
                    self._automaticRefreshRuns)

    # noinspection PyUnusedLocal
    def _automaticRefreshRuns(self, e=None):
        """ Schedule automatic refresh increasing the time between refreshes. """
        if pwutils.envVarOn('DO_NOT_AUTO_REFRESH'):
            return

        if self.project.needRefresh():
            self.refreshRuns(initRefreshCounter=False)
            secs = self.__autoRefreshCounter
        else:
            secs = INIT_REFRESH_SECONDS // 2

        # double the number of seconds up to 30 min
        self.__autoRefreshCounter = min(2 * secs, 1800)
        self.__autoRefresh = self.runsTree.after(secs * 1000,
                                                 self._automaticRefreshRuns)

    # noinspection PyUnusedLocal
    def _findProtocol(self, e=None):
        """ Find a desired protocol by typing some keyword. """
        window = SearchProtocolWindow(self.windows)
        window.show()

    def createActionToolbar(self):
        """ Prepare the buttons that will be available for protocol actions. """

        self.actionButtons = {}
        self.actionList = [ACTION_EDIT, ACTION_COPY, ACTION_DELETE,
                           ACTION_STEPS, ACTION_BROWSE, ACTION_DB,
                           ACTION_STOP, ACTION_CONTINUE, ACTION_RESULTS,
                           ACTION_EXPORT, ACTION_EXPORT_UPLOAD, ACTION_COLLAPSE,
                           ACTION_EXPAND, ACTION_LABELS]

        def addButton(action, text, toolbar):
            btn = tk.Label(toolbar, text=text,
                           image=self.getImage(ActionIcons.get(action, None)),
                           compound=tk.LEFT, cursor='hand2', bg='white')
            btn.bind('<Button-1>', lambda e: self._runActionClicked(action))
            return btn

        for action in self.actionList:
            self.actionButtons[action] = addButton(action, action,
                                                   self.runsToolbar)

        ActionIcons[ACTION_TREE] = RUNS_TREE

        self.viewButtons = {}

        # Add combo for switch between views
        viewFrame = tk.Frame(self.allToolbar)
        viewFrame.grid(row=0, column=0)
        self._createViewCombo(viewFrame)

        # Add refresh Tree button
        btn = addButton(ACTION_TREE, "  ", self.allToolbar)
        pwgui.tooltip.ToolTip(btn, "Re-organize the node positions.", 1500)
        self.viewButtons[ACTION_TREE] = btn
        if self.runsView != VIEW_LIST:
            btn.grid(row=0, column=1)

        # Add refresh button
        btn = addButton(ACTION_REFRESH, ACTION_REFRESH, self.allToolbar)
        btn.grid(row=0, column=2)
        self.viewButtons[ACTION_REFRESH] = btn

    def _createViewCombo(self, parent):
        """ Create the select-view combobox. """
        label = tk.Label(parent, text='View:', bg='white')
        label.grid(row=0, column=0)
        viewChoices = ['List', 'Tree', 'Tree - small']
        self.switchCombo = pwgui.widgets.ComboBox(parent, width=10,
                                                  choices=viewChoices,
                                                  values=[VIEW_LIST, VIEW_TREE, VIEW_TREE_SMALL],
                                                  initial=viewChoices[self.runsView],
                                                  onChange=lambda e: self._runActionClicked(
                                                      ACTION_SWITCH_VIEW))
        self.switchCombo.grid(row=0, column=1)

    def _updateActionToolbar(self):
        """ Update which action buttons should be visible. """

        def displayAction(actionToDisplay, column, condition=True):

            """ Show/hide the action button if the condition is met. """

            # If action present (set color is not in the toolbar but in the
            # context menu)
            action = self.actionButtons.get(actionToDisplay, None)
            if action is not None:
                if condition:
                    action.grid(row=0, column=column, sticky='sw',
                                padx=(0, 5), ipadx=0)
                else:
                    action.grid_remove()

        for i, actionTuple in enumerate(self.provider.getActionsFromSelection()):
            action, cond = actionTuple
            displayAction(action, i, cond)

    def _createProtocolsTree(self, parent, background=Color.LIGHT_GREY_COLOR,
                             show='tree', columns=None):
        defaultFont = pwgui.getDefaultFont()
        self.style.configure("W.Treeview", background=background, borderwidth=0,
                             fieldbackground=background,
                             rowheight=defaultFont.metrics()['linespace'])
        t = pwgui.tree.Tree(parent, show=show, style='W.Treeview',
                            columns=columns)
        t.column('#0', minwidth=300)
        # Protocol nodes
        t.tag_configure(ProtocolTreeConfig.TAG_PROTOCOL,
                        image=self.getImage('python_file.gif'))
        t.tag_bind(ProtocolTreeConfig.TAG_PROTOCOL,
                   '<Double-1>', self._protocolItemClick)
        t.tag_bind(ProtocolTreeConfig.TAG_PROTOCOL,
                   '<Return>', self._protocolItemClick)
        t.tag_bind(ProtocolTreeConfig.TAG_PROTOCOL,
                   '<KP_Enter>', self._protocolItemClick)

        # Disable protocols (not installed) are allowed to be added.
        t.tag_configure(ProtocolTreeConfig.TAG_PROTOCOL_DISABLED,
                        image=self.getImage('prot_disabled.gif'))
        t.tag_bind(ProtocolTreeConfig.TAG_PROTOCOL_DISABLED,
                   '<Double-1>', self._protocolItemClick)
        t.tag_bind(ProtocolTreeConfig.TAG_PROTOCOL_DISABLED,
                   '<Return>', self._protocolItemClick)
        t.tag_bind(ProtocolTreeConfig.TAG_PROTOCOL_DISABLED,
                   '<KP_Enter>', self._protocolItemClick)

        t.tag_configure('protocol_base', image=self.getImage('class_obj.gif'))
        t.tag_configure('protocol_group', image=self.getImage('class_obj.gif'))
        t.tag_configure('section', font=self.windows.fontBold)
        return t

    def _createProtocolsPanel(self, parent, bgColor):
        """Create the protocols Tree displayed in left panel"""
        comboFrame = tk.Frame(parent, bg=bgColor)
        tk.Label(comboFrame, text='View', bg=bgColor).grid(row=0, column=0,
                                                           padx=(0, 5), pady=5)
        choices = self.getProtocolViews()
        initialChoice = self.settings.getProtocolView()
        combo = pwgui.widgets.ComboBox(comboFrame, choices=choices,
                                       initial=initialChoice)
        combo.setChangeCallback(self._onSelectProtocols)
        combo.grid(row=0, column=1)
        comboFrame.grid(row=0, column=0, padx=5, pady=5, sticky='nw')

        t = self._createProtocolsTree(parent)
        t.grid(row=1, column=0, sticky='news')
        # Program automatic refresh
        t.after(3000, self._automaticRefreshRuns)
        self.protTree = t

    def getProtocolViews(self):

        if self._protocolViews is None:
            self._loadProtocols()

        return list(self._protocolViews.keys())

    def getCurrentProtocolView(self):
        """ Select the view that is currently selected.
        Read from the settings the last selected view
        and get the information from the self._protocolViews dict.
        """
        currentView = self.project.getProtocolView()
        if currentView in self.getProtocolViews():
            viewKey = currentView
        else:
            viewKey = self.getProtocolViews()[0]
            self.project.settings.setProtocolView(viewKey)
            if currentView is not None:
                print("PROJECT: Warning, protocol view '%s' not found." % currentView)
                print("         Using '%s' instead." % viewKey)

        return self._protocolViews[viewKey]

    def _loadProtocols(self):
        """ Load protocol configuration from a .conf file. """
        # If the host file is not passed as argument...
        configProtocols = Config.SCIPION_PROTOCOLS

        localDir = Config.SCIPION_LOCAL_CONFIG
        protConf = os.path.join(localDir, configProtocols)
        self._protocolViews = ProtocolTreeConfig.load(self.project.getDomain(),
                                                      protConf)

    def _onSelectProtocols(self, combo):
        """ This function will be called when a protocol menu
        is selected. The index of the new menu is passed. 
        """
        protView = combo.getText()
        self.settings.setProtocolView(protView)
        self.protCfg = self.getCurrentProtocolView()
        self.updateProtocolsTree(self.protCfg)

    def populateTree(self, tree, treeItems, prefix, obj, subclassedDict, level=0):
        text = obj.text.get()
        if text:
            value = obj.value.get(text)
            key = '%s.%s' % (prefix, value)

            img = obj.icon.get('')
            tag = obj.tag.get('')

            if len(img):
                img = self.getImage(img)
                # If image is none
                img = img if img is not None else ''

            protClassName = value.split('.')[-1]  # Take last part
            emProtocolsDict = self.domain.getProtocols()
            prot = emProtocolsDict.get(protClassName, None)

            if tag == 'protocol' and text == 'default':
                if prot is None:
                    print("Protocol className '%s' not found!!!. \n"
                          "Fix your config/protocols.conf configuration."
                          % protClassName)
                    return

                text = prot.getClassLabel()

            item = tree.insert(prefix, 'end', key, text=text, image=img, tags=tag)
            treeItems[item] = obj
            # Check if the attribute should be open or close
            openItem = getattr(obj, 'openItem', level < 2)
            if openItem:
                tree.item(item, open=True)

            if obj.value.hasValue() and tag == 'protocol_base':
                if prot is not None:
                    tree.item(item, image=self.getImage('class_obj.gif'))

                    for k, v in emProtocolsDict.items():
                        if (k not in subclassedDict and v is not prot and
                           issubclass(v, prot)):
                            key = '%s.%s' % (item, k)
                            t = v.getClassLabel()
                            tree.insert(item, 'end', key, text=t, tags='protocol')
                else:
                    raise Exception("Class '%s' not found" % obj.value.get())
        else:
            key = prefix

        for sub in obj:
            self.populateTree(tree, treeItems, key, sub, subclassedDict,
                              level + 1)

    def updateProtocolsTree(self, protCfg):

        try:
            self.protCfg = protCfg
            self.protTree.clear()
            self.protTree.unbind('<<TreeviewOpen>>')
            self.protTree.unbind('<<TreeviewClose>>')
            self.protTreeItems = {}
            subclassedDict = {}  # Check which classes serve as base to not show them
            emProtocolsDict = self.domain.getProtocols()
            for _, v1 in emProtocolsDict.items():
                for k2, v2 in emProtocolsDict.items():
                    if v1 is not v2 and issubclass(v1, v2):
                        subclassedDict[k2] = True
            self.populateTree(self.protTree, self.protTreeItems, '', self.protCfg,
                              subclassedDict)
            self.protTree.bind('<<TreeviewOpen>>',
                               lambda e: self._treeViewItemChange(True))
            self.protTree.bind('<<TreeviewClose>>',
                               lambda e: self._treeViewItemChange(False))
        except Exception as e:
            # Tree can't be loaded report back, but continue
            print("Protocols tree couldn't be loaded: %s" % e)

    def _treeViewItemChange(self, openItem):
        item = self.protTree.focus()
        if item in self.protTreeItems:
            self.protTreeItems[item].openItem.set(openItem)

    def createRunsTree(self, parent):
        self.provider = RunsTreeProvider(self.project, self._runActionClicked)

        # This line triggers the getRuns for the first time.
        # Ne need to force the check pids here, temporary
        self.provider._checkPids = True

        # To specify the height of the rows based on the font size.
        # Should be centralized somewhere.
        style = ttk.Style()
        rowheight = pwgui.getDefaultFont().metrics()['linespace']
        style.configure('List.Treeview', rowheight=rowheight)

        t = pwgui.tree.BoundTree(parent, self.provider, style='List.Treeview')
        self.provider._checkPids = False

        t.itemDoubleClick = self._runItemDoubleClick
        t.itemClick = self._runTreeItemClick

        return t

    def updateRunsTree(self, refresh=False):
        self.provider.setRefresh(refresh)
        self.runsTree.update()
        self.updateRunsTreeSelection()

    def updateRunsTreeSelection(self):
        for prot in self._iterSelectedProtocols():
            treeId = self.provider.getObjectFromId(prot.getObjId())._treeId
            self.runsTree.selection_add(treeId)

    def createRunsGraph(self, parent):
        self.runsGraphCanvas = pwgui.Canvas(parent, width=400, height=400,
                                            tooltipCallback=self._runItemTooltip,
                                            tooltipDelay=1000,
                                            name=ProtocolsView.RUNS_CANVAS_NAME,
                                            takefocus=True,
                                            highlightthickness=0)

        self.runsGraphCanvas.onClickCallback = self._runItemClick
        self.runsGraphCanvas.onDoubleClickCallback = self._runItemDoubleClick
        self.runsGraphCanvas.onRightClickCallback = self._runItemRightClick
        self.runsGraphCanvas.onControlClickCallback = self._runItemControlClick
        self.runsGraphCanvas.onAreaSelected = self._selectItemsWithinArea
        self.runsGraphCanvas.onMiddleMouseClickCallback = self._runItemMiddleClick

        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)

        self.settings.getNodes().updateDict()
        self.settings.getLabels().updateDict()

        self.updateRunsGraph()

    def updateRunsGraph(self, refresh=False, reorganize=False, checkPids=False):

        self.runsGraph = self.project.getRunsGraph(refresh=refresh,
                                                   checkPids=checkPids)
        self.drawRunsGraph(reorganize)

    def drawRunsGraph(self, reorganize=False):

        self.runsGraphCanvas.clear()

        # Check if there are positions stored
        if reorganize or len(self.settings.getNodes()) == 0:
            # Create layout to arrange nodes as a level tree
            layout = pwgui.LevelTreeLayout()
        else:
            layout = pwgui.BasicLayout()

        # Create empty nodeInfo for new runs
        for node in self.runsGraph.getNodes():
            nodeId = node.run.getObjId() if node.run else 0
            nodeInfo = self.settings.getNodeById(nodeId)
            if nodeInfo is None:
                self.settings.addNode(nodeId, x=0, y=0, expanded=True)

        self.runsGraphCanvas.drawGraph(self.runsGraph, layout,
                                       drawNode=self.createRunItem)

    def createRunItem(self, canvas, node):

        nodeId = node.run.getObjId() if node.run else 0
        nodeInfo = self.settings.getNodeById(nodeId)

        # Extend attributes: use some from nodeInfo
        node.expanded = nodeInfo.isExpanded()
        node.x, node.y = nodeInfo.getPosition()
        nodeText = self._getNodeText(node)

        # Get status color
        statusColor = getStatusColorFromNode(node)

        # Get the box color (depends on color mode: label or status)
        boxColor = self._getBoxColor(nodeInfo, statusColor, node)

        # Draw the box
        item = RunBox(nodeInfo, self.runsGraphCanvas,
                      nodeText, node.x, node.y,
                      bgColor=boxColor, textColor='black')
        # No border
        item.margin = 0

        # Paint the oval..if apply.
        self._paintOval(item, statusColor)

        # Paint the bottom line (for now only labels are painted there).
        self._paintBottomLine(item)

        if nodeId in self._selection:
            item.setSelected(True)
        return item

    def _getBoxColor(self, nodeInfo, statusColor, node):

        try:

            # If the color has to go to the box
            if self.settings.statusColorMode():
                boxColor = statusColor

            elif self.settings.ageColorMode():

                if node.run:

                    # Project elapsed time
                    elapsedTime = node.run.getProject().getElapsedTime()
                    creationTime = node.run.getProject().getCreationTime()

                    # Get the latest activity timestamp
                    ts = node.run.endTime.datetime()

                    if elapsedTime is None or creationTime is None or ts is None:
                        boxColor = DEFAULT_BOX_COLOR

                    else:

                        # tc closer to the end are younger
                        protAge = ts - creationTime

                        boxColor = self._ageColor('#6666ff', elapsedTime,
                                                  protAge)
                else:
                    boxColor = DEFAULT_BOX_COLOR

            # ... box is for the labels.
            elif self.settings.labelsColorMode():
                # If there is only one label use the box for the color.
                if self._getLabelsCount(nodeInfo) == 1:

                    labelId = nodeInfo.getLabels()[0]
                    label = self.settings.getLabels().getLabel(labelId)

                    # If there is no label (it has been deleted)
                    if label is None:
                        nodeInfo.getLabels().remove(labelId)
                        boxColor = DEFAULT_BOX_COLOR
                    else:
                        boxColor = label.getColor()

                else:
                    boxColor = DEFAULT_BOX_COLOR
            else:
                boxColor = DEFAULT_BOX_COLOR

            return boxColor
        except Exception as e:
            return DEFAULT_BOX_COLOR

    @staticmethod
    def _ageColor(rgbColor, projectAge, protocolAge):

        #  Get the ratio
        ratio = protocolAge.seconds / float(projectAge.seconds)

        # Invert direction: older = white = 100%, newest = rgbColor = 0%
        ratio = 1 - ratio

        # There are cases coming with protocols older than the project.
        ratio = 0 if ratio < 0 else ratio

        return pwutils.rgb_to_hex(pwutils.lighter(pwutils.hex_to_rgb(rgbColor),
                                                  ratio))

    @staticmethod
    def _getLabelsCount(nodeInfo):

        return 0 if nodeInfo.getLabels() is None else len(nodeInfo.getLabels())

    def _paintBottomLine(self, item):

        if self.settings.labelsColorMode():
            self._addLabels(item)

    def _paintOval(self, item, statusColor):
        # Show the status as a circle in the top right corner
        if not self.settings.statusColorMode():
            # Option: Status item.
            (topLeftX, topLeftY, bottomRightX,
             bottomRightY) = self.runsGraphCanvas.bbox(item.id)
            statusSize = 10
            statusX = bottomRightX - (statusSize + 3)
            statusY = topLeftY + 3

            pwgui.Oval(self.runsGraphCanvas, statusX, statusY, statusSize,
                       color=statusColor, anchor=item)

        # in statusColorMode
        else:
            # Show a black circle if there is any label
            if self._getLabelsCount(item.nodeInfo) > 0:
                (topLeftX, topLeftY, bottomRightX,
                 bottomRightY) = self.runsGraphCanvas.bbox(item.id)
                statusSize = 10
                statusX = bottomRightX - (statusSize + 3)
                statusY = topLeftY + 3

                pwgui.Oval(self.runsGraphCanvas, statusX, statusY, statusSize,
                           color='black', anchor=item)

    def _getNodeText(self, node):
        nodeText = node.getLabel()
        # Truncate text to prevent overflow
        if len(nodeText) > 40:
            nodeText = nodeText[:37] + "..."

        if node.run:
            expandedStr = '' if node.expanded else ' (+)'
            if self.runsView == VIEW_TREE_SMALL:
                nodeText = node.getName() + expandedStr
            else:
                nodeText += expandedStr + '\n' + node.run.getStatusMessage()
                if node.run.summaryWarnings:
                    nodeText += u' \u26a0'
        return nodeText

    def _addLabels(self, item):
        # If there is only one label it should be already used in the box color.
        if self._getLabelsCount(item.nodeInfo) < 2:
            return
        # Get the positions of the box
        (topLeftX, topLeftY, bottomRightX,
         bottomRightY) = self.runsGraphCanvas.bbox(item.id)

        # Get the width of the box
        boxWidth = bottomRightX - topLeftX

        # Set the size
        marginV = 3
        marginH = 2
        labelWidth = (boxWidth - (2 * marginH)) / len(item.nodeInfo.getLabels())
        labelHeight = 6

        # Leave some margin on the right and bottom
        labelX = bottomRightX - marginH
        labelY = bottomRightY - (labelHeight + marginV)

        for index, labelId in enumerate(item.nodeInfo.getLabels()):

            # Get the label
            label = self.settings.getLabels().getLabel(labelId)

            # If not none
            if label is not None:
                # Move X one label to the left
                if index == len(item.nodeInfo.getLabels()) - 1:
                    labelX = topLeftX + marginH
                else:
                    labelX -= labelWidth

                pwgui.Rectangle(self.runsGraphCanvas, labelX, labelY,
                                labelWidth, labelHeight, color=label.getColor(),
                                anchor=item)
            else:

                item.nodeInfo.getLabels().remove(labelId)

    def switchRunsView(self):
        previousView = self.runsView
        viewValue = self.switchCombo.getValue()
        self.runsView = viewValue
        self.settings.setRunsView(viewValue)

        if viewValue == VIEW_LIST:
            self.runsTree.grid(row=0, column=0, sticky='news')
            self.runsGraphCanvas.frame.grid_remove()
            self.updateRunsTreeSelection()
            self.viewButtons[ACTION_TREE].grid_remove()
            self._lastRightClickPos = None
        else:
            self.runsTree.grid_remove()
            self.updateRunsGraph(reorganize=(previousView != VIEW_LIST))
            self.runsGraphCanvas.frame.grid(row=0, column=0, sticky='news')
            self.viewButtons[ACTION_TREE].grid(row=0, column=1)

    def _protocolItemClick(self, e=None):
        # Get the tree widget that originated the event
        # it could be the left panel protocols tree or just
        # the search protocol dialog tree
        tree = e.widget
        protClassName = tree.getFirst().split('.')[-1]
        protClass = self.domain.getProtocols().get(protClassName)
        prot = self.project.newProtocol(protClass)
        self._openProtocolForm(prot)

    def _toggleColorScheme(self, e=None):

        currentMode = self.settings.getColorMode()

        if currentMode >= len(self.settings.COLOR_MODES) - 1:
            currentMode = -1

        nextColorMode = currentMode + 1

        self.settings.setColorMode(nextColorMode)
        self._updateActionToolbar()
        # self.updateRunsGraph()
        self.drawRunsGraph()

    def _toggleDebug(self, e=None):
        Config.toggleDebug()

    def _selectAllProtocols(self, e=None):
        self._selection.clear()

        # WHY GOING TO THE db?
        #  Let's try using in memory data.
        # for prot in self.project.getRuns():
        for prot in self.project.runs:
            self._selection.append(prot.getObjId())
        self._updateSelection()

        # self.updateRunsGraph()
        self.drawRunsGraph()

    def _inspectProtocols(self, e=None):
        objs = self._getSelectedProtocols()
        # We will inspect the selected objects or
        #   the whole project is no protocol is selected
        if len(objs) > 0:
            objs.sort(key=lambda obj: obj._objId, reverse=True)
            filePath = objs[0]._getLogsPath('inspector.csv')
            doInspect = True
        else:
            proj = self.project
            filePath = proj.getLogPath('inspector.csv')
            objs = [proj]
            doInspect = pwgui.dialog.askYesNo(Message.TITLE_INSPECTOR,
                                              Message.LABEL_INSPECTOR, self.root)

        if doInspect:
            inspectObj(objs, filePath)
            # we open the resulting CSV file with the OS default software
            pwgui.text.openTextFileEditor(filePath)

    # NOt used!: pconesa 02/11/2016.
    # def _deleteSelectedProtocols(self, e=None):
    #
    #     for selection in self._selection:
    #         self.project.getProtocol(self._selection[0])
    #
    #
    #     self._updateSelection()
    #     self.updateRunsGraph()

    def _updateSelection(self):
        self._fillSummary()
        self._fillMethod()
        self._fillLogs()
        self._showHideAnalyzeResult()

        if self._isSingleSelection():
            last = self.getSelectedProtocol()
            self._lastSelectedProtId = last.getObjId() if last else None

        self._updateActionToolbar()

    def _runTreeItemClick(self, item=None):
        self._selection.clear()
        for prot in self.runsTree.iterSelectedObjects():
            self._selection.append(prot.getObjId())
        self._updateSelection()

    def _selectItemProtocol(self, prot):
        """ Call this function when a new box (item) of a protocol
        is selected. It should be called either from itemClick
        or itemRightClick
        """
        self._selection.clear()
        self.settings.dataSelection.clear()
        self._selection.append(prot.getObjId())

        # Select output data too
        self.toggleDataSelection(prot, True)

        self._updateSelection()
        self.runsGraphCanvas.update_idletasks()

    def _deselectItems(self, item):
        """ Deselect all items except the item one
        """
        g = self.project.getRunsGraph(refresh=False)

        for node in g.getNodes():
            if node.run and node.run.getObjId() in self._selection:
                # This option is only for compatibility with all projects
                if hasattr(node, 'item'):
                    node.item.setSelected(False)
        item.setSelected(True)

    def _runItemClick(self, item=None):

        # If click is in a empty area....start panning
        if item is None:
            print("Click on empty area")
            return

        self.runsGraphCanvas.focus_set()

        # Get last selected item for tree or graph
        if self.runsView == VIEW_LIST:
            prot = self.project.mapper.selectById(int(self.runsTree.getFirst()))
        else:
            prot = item.node.run
            if prot is None:  # in case it is the main "Project" node
                return
            self._deselectItems(item)
        self._selectItemProtocol(prot)

    def _runItemDoubleClick(self, e=None):
        self._runActionClicked(ACTION_EDIT)

    def _runItemMiddleClick(self, e=None):
        self._runActionClicked(ACTION_SELECT_TO)

    def _runItemRightClick(self, item=None):
        prot = item.node.run
        if prot is None:  # in case it is the main "Project" node
            return
        n = len(self._selection)
        # Only select item with right-click if there is a single
        # item selection, not for multiple selection
        if n <= 1:
            self._deselectItems(item)
            self._selectItemProtocol(prot)
            self._lastRightClickPos = self.runsGraphCanvas.eventPos

        return self.provider.getObjectActions(prot)

    def _runItemControlClick(self, item=None):
        # Get last selected item for tree or graph
        if self.runsView == VIEW_LIST:
            # TODO: Prot is not used!!
            prot = self.project.mapper.selectById(int(self.runsTree.getFirst()))
        else:
            prot = item.node.run
            protId = prot.getObjId()
            if protId in self._selection:
                item.setSelected(False)
                self._selection.remove(protId)

                # Remove data selected
                self.toggleDataSelection(prot, False)
            else:

                item.setSelected(True)
                if len(self._selection) == 1:  # repaint first selected item
                    firstSelectedNode = self.runsGraph.getNode(str(self._selection[0]))
                    if hasattr(firstSelectedNode, 'item'):
                        firstSelectedNode.item.setSelected(False)
                        firstSelectedNode.item.setSelected(True)
                self._selection.append(prot.getObjId())

                # Select output data too
                self.toggleDataSelection(prot, True)

        self._updateSelection()

    def toggleDataSelection(self, prot, append):

        # Go through the data selection
        for paramName, output in prot.iterOutputAttributes():
            if append:
                self.settings.dataSelection.append(output.getObjId())
            else:
                self.settings.dataSelection.remove(output.getObjId())

    def _runItemTooltip(self, tw, item):
        """ Create the contents of the tooltip to be displayed
        for the given item.
        Params:
            tw: a tk.TopLevel instance (ToolTipWindow)
            item: the selected item.
        """
        prot = item.node.run

        if prot:
            tm = '*%s*\n' % prot.getRunName()
            tm += '   Id: %s\n' % prot.getObjId()
            tm += 'State: %s\n' % prot.getStatusMessage()
            tm += ' Time: %s\n' % pwutils.prettyDelta(prot.getElapsedTime())
            if not hasattr(tw, 'tooltipText'):
                frame = tk.Frame(tw)
                frame.grid(row=0, column=0)
                tw.tooltipText = pwgui.dialog.createMessageBody(frame, tm, None,
                                                                textPad=0,
                                                                textBg=Color.LIGHT_GREY_COLOR_2)
                tw.tooltipText.config(bd=1, relief=tk.RAISED)
            else:
                pwgui.dialog.fillMessageText(tw.tooltipText, tm)

    @staticmethod
    def _selectItemsWithinArea(x1, y1, x2, y2, enclosed=False):
        """
        Parameters
        ----------
        x1: x coordinate of first corner of the area
        y1: y coordinate of first corner of the area
        x2: x coordinate of second corner of the area
        y2: y coordinate of second corner of the area
        enclosed: Default True. Returns enclosed items,
                  overlapping items otherwise.
        Returns
        -------
        Nothing

        """

        return
        # NOT working properly: Commented for the moment.
        # if enclosed:
        #     items = self.runsGraphCanvas.find_enclosed(x1, y1, x2, y2)
        # else:
        #     items = self.runsGraphCanvas.find_overlapping(x1, y1, x2, y2)
        #
        # update = False
        #
        # for itemId in items:
        #     if itemId in self.runsGraphCanvas.items:
        #
        #         item = self.runsGraphCanvas.items[itemId]
        #         if not item.node.isRoot():
        #             item.setSelected(True)
        #             self._selection.append(itemId)
        #             update = True
        #
        # if update is not None: self._updateSelection()

    def _openProtocolForm(self, prot):
        """Open the Protocol GUI Form given a Protocol instance"""

        w = FormWindow(Message.TITLE_NAME_RUN + prot.getClassName(),
                       prot, self._executeSaveProtocol, self.windows,
                       hostList=self.project.getHostNames(),
                       updateProtocolCallback=self._updateProtocol(prot))
        w.adjustSize()
        w.show(center=True)

    def _browseSteps(self):
        """ Open a new window with the steps list. """
        window = StepsWindow(Message.TITLE_BROWSE_DATA, self.windows,
                             self.getSelectedProtocol())
        window.show()

    def _browseRunData(self):
        provider = ProtocolTreeProvider(self.getSelectedProtocol())
        window = pwgui.browser.BrowserWindow(Message.TITLE_BROWSE_DATA,
                                             self.windows)
        window.setBrowser(pwgui.browser.ObjectBrowser(window.root, provider))
        window.itemConfig(self.getSelectedProtocol(), open=True)
        window.show()

    def _browseRunDirectory(self):
        """ Open a file browser to inspect the files generated by the run. """
        protocol = self.getSelectedProtocol()
        workingDir = protocol.getWorkingDir()
        if os.path.exists(workingDir):

            window = pwgui.browser.FileBrowserWindow("Browsing: " + workingDir,
                                                     master=self.windows,
                                                     path=workingDir)
            window.show()
        else:
            self.windows.showInfo("Protocol working dir does not exists: \n %s"
                                  % workingDir)

    def _iterSelectedProtocols(self):
        for protId in sorted(self._selection):
            prot = self.project.getProtocol(protId)
            if prot:
                yield prot

    def _getSelectedProtocols(self):
        return [prot for prot in self._iterSelectedProtocols()]

    def _iterSelectedNodes(self):

        for protId in sorted(self._selection):
            node = self.settings.getNodeById(protId)

            yield node

    def _getSelectedNodes(self):
        return [node for node in self._iterSelectedNodes()]

    def getSelectedProtocol(self):
        if self._selection:
            return self.project.getProtocol(self._selection[0])
        return None

    def _showHideAnalyzeResult(self):

        if self._selection:
            self.btnAnalyze.grid()
        else:
            self.btnAnalyze.grid_remove()

    def _fillSummary(self):
        self.summaryText.setReadOnly(False)
        self.summaryText.clear()
        self.infoTree.clear()
        n = len(self._selection)

        if n == 1:
            prot = self.getSelectedProtocol()

            if prot:
                provider = RunIOTreeProvider(self, prot, self.project.mapper)
                self.infoTree.setProvider(provider)
                self.infoTree.grid(row=0, column=0, sticky='news')
                self.infoTree.update_idletasks()
                # Update summary
                self.summaryText.addText(prot.summary())
            else:
                self.infoTree.clear()

        elif n > 1:
            self.infoTree.clear()
            for prot in self._iterSelectedProtocols():
                self.summaryText.addLine('> _%s_' % prot.getRunName())
                for line in prot.summary():
                    self.summaryText.addLine(line)
                self.summaryText.addLine('')
        self.summaryText.setReadOnly(True)

    def _fillMethod(self):

        try:
            self.methodText.setReadOnly(False)
            self.methodText.clear()
            self.methodText.addLine("*METHODS:*")
            cites = OrderedDict()

            for prot in self._iterSelectedProtocols():
                self.methodText.addLine('> _%s_' % prot.getRunName())
                for line in prot.getParsedMethods():
                    self.methodText.addLine(line)
                cites.update(prot.getCitations())
                cites.update(prot.getPackageCitations())
                self.methodText.addLine('')

            if cites:
                self.methodText.addLine('*REFERENCES:*   '
                                        ' [[sci-bib:][<<< Open as bibtex >>>]]')
                for cite in cites.values():
                    self.methodText.addLine(cite)

            self.methodText.setReadOnly(True)
        except Exception as e:
            self.methodText.addLine('Could not load all methods:' + str(e))

    def _fillLogs(self):
        prot = self.getSelectedProtocol()

        if not self._isSingleSelection() or not prot:
            self.outputViewer.clear()
            self._lastStatus = None
        elif prot.getObjId() != self._lastSelectedProtId:
            self._lastStatus = prot.getStatus()
            i = self.outputViewer.getIndex()
            self.outputViewer.clear()
            # Right now skip the err tab since we are redirecting
            # stderr to stdout
            out, _, log, schedule = prot.getLogPaths()
            self.outputViewer.addFile(out)
            self.outputViewer.addFile(log)
            if os.path.exists(schedule):
                self.outputViewer.addFile(schedule)
            self.outputViewer.setIndex(i)  # Preserve the last selected tab
            self.outputViewer.selectedText().goEnd()
            # when there are not logs, force re-load next time
            if (not os.path.exists(out) or
                    not os.path.exists(log)):
                self._lastStatus = None

        elif prot.isActive() or prot.getStatus() != self._lastStatus:
            doClear = self._lastStatus is None
            self._lastStatus = prot.getStatus()
            self.outputViewer.refreshAll(clear=doClear, goEnd=doClear)

    def _scheduleRunsUpdate(self, secs=1):
        # self.runsTree.after(secs*1000, self.refreshRuns)
        self.windows.enqueue(self.refreshRuns)

    def executeProtocol(self, prot):
        """ Function to execute a protocol called not
        directly from the Form "Execute" button.
        """
        # We need to equeue the execute action
        # to be executed in the same thread
        self.windows.enqueue(lambda: self._executeSaveProtocol(prot))

    def _executeSaveProtocol(self, prot, onlySave=False, doSchedule=False):
        if onlySave:
            self.project.saveProtocol(prot)
            msg = Message.LABEL_SAVED_FORM
            # msg = "Protocol successfully saved."

        else:
            if doSchedule:
                self.project.scheduleProtocol(prot)
            else:
                self.project.launchProtocol(prot)
            # Select the launched protocol to display its summary, methods..etc
            self._selection.clear()
            self._selection.append(prot.getObjId())
            self._updateSelection()
            self._lastStatus = None  # clear lastStatus to force re-load the logs
            msg = ""

        # Update runs list display, even in save we
        # need to get the updated copy of the protocol
        self._scheduleRunsUpdate()

        return msg

    def _updateProtocol(self, prot):
        """ Callback to notify about the change of a protocol
        label or comment. 
        """
        self._scheduleRunsUpdate()

    def _continueProtocol(self, prot):
        self.project.continueProtocol(prot)
        self._scheduleRunsUpdate()

    def _onDelPressed(self):
        # This function will be connected to the key 'Del' press event
        # We need to check if the canvas have the focus and then
        # proceed with the delete action

        # get the widget with the focus
        widget = self.focus_get()

        # Call the delete action only if the widget is the canvas
        if str(widget).endswith(ProtocolsView.RUNS_CANVAS_NAME):
            self._deleteProtocol()

    def _deleteProtocol(self):
        protocols = self._getSelectedProtocols()

        if len(protocols) == 0:
            return

        protStr = '\n  - '.join(['*%s*' % p.getRunName() for p in protocols])

        if pwgui.dialog.askYesNo(Message.TITLE_DELETE_FORM,
                                 Message.LABEL_DELETE_FORM % protStr,
                                 self.root):
            self.project.deleteProtocol(*protocols)
            self._selection.clear()
            self._updateSelection()
            self._scheduleRunsUpdate()

    def _copyProtocols(self):
        protocols = self._getSelectedProtocols()
        if len(protocols) == 1:
            newProt = self.project.copyProtocol(protocols[0])
            if newProt is None:
                self.windows.showError("Error copying protocol.!!!")
            else:
                self._openProtocolForm(newProt)
        else:
            self.project.copyProtocol(protocols)
            self.refreshRuns()

    def _stopWorkFlow(self, action):

        protocols = self._getSelectedProtocols()
        errorList = []
        if pwgui.dialog.askYesNo(Message.TITLE_STOP_WORKFLOW_FORM,
                                 Message.TITLE_STOP_WORKFLOW, self.root):
            defaultModeMessage = 'Stopping the workflow...'
            message = FloatingMessage(self.root, defaultModeMessage)
            message.show()
            errorList = self.project.stopWorkFlow(protocols[0])
            self.refreshRuns()
            message.close()
        if errorList:
            msg = ''
            for errorProt in errorList:
                error = ("The protocol: %s  is active\n" %
                         (self.project.getProtocol(errorProt).getRunName()))
                msg += str(error)
            pwgui.dialog.MessageDialog(
                self, Message.TITLE_STOPPED_WORKFLOW_FAILED,
                Message.TITLE_STOPPED_WORKFLOW_FAILED + msg,
                'fa-times-circle_alert.gif')

    def _resetWorkFlow(self, action):

        protocols = self._getSelectedProtocols()
        errorList = []
        if pwgui.dialog.askYesNo(Message.TITLE_RESET_WORKFLOW_FORM,
                                 Message.TITLE_RESET_WORKFLOW, self.root):
            defaultModeMessage = 'Resetting the workflow...'
            message = FloatingMessage(self.root, defaultModeMessage)
            message.show()
            errorList = self.project.resetWorkFlow(protocols[0])
            self.refreshRuns()
            message.close()
        if errorList:
            msg = ''
            for errorProt in errorList:
                error = ("The protocol: %s  is active\n" %
                         (self.project.getProtocol(errorProt).getRunName()))
                msg += str(error)
            pwgui.dialog.MessageDialog(
                self, Message.TITLE_RESETED_WORKFLOW_FAILED,
                Message.TITLE_RESETED_WORKFLOW_FAILED + msg,
                'fa-times-circle_alert.gif')

    def _launchWorkFlow(self, action):
        """
        This function can launch a workflow from a selected protocol in two
        modes depending on the 'action' value (RESTART, CONTINUE)
        """
        protocols = self._getSelectedProtocols()
        errorList = []
        defaultMode = pwprot.MODE_CONTINUE
        defaultModeMessage = 'Checking the workflow to continue...'

        if action == ACTION_RESTART_WORKFLOW:
            if pwgui.dialog.askYesNo(Message.TITLE_RESTART_WORKFLOW_FORM,
                                     Message.TITLE_RESTART_WORKFLOW, self.root):
                defaultMode = pwprot.MODE_RESTART
                defaultModeMessage = 'Checking the workflow to restart...'

                message = FloatingMessage(self.root, defaultModeMessage)
                message.show()
                errorList = self.project.launchWorkflow(protocols[0],
                                                        defaultMode)
                self.refreshRuns()
                message.close()
        elif action == ACTION_CONTINUE_WORKFLOW:
            message = FloatingMessage(self.root, defaultModeMessage)
            message.show()
            errorList = self.project.launchWorkflow(protocols[0],
                                                    defaultMode)
            self.refreshRuns()
            message.close()

        if errorList:
            msg = ''
            for errorProt in errorList:
                error = ("The protocol: %s  is active\n" %
                         (self.project.getProtocol(errorProt).getRunName()))
                msg += str(error)
            pwgui.dialog.MessageDialog(
                self, Message.TITLE_LAUNCHED_WORKFLOW_FAILED_FORM,
                Message.TITLE_LAUNCHED_WORKFLOW_FAILED + "\n" + msg,
                'fa-times-circle_alert.gif')

    def _selectLabels(self):
        selectedNodes = self._getSelectedNodes()

        if selectedNodes:
            dlg = self.windows.manageLabels()

            if dlg.resultYes():
                for node in selectedNodes:
                    node.setLabels([label.getName() for label in dlg.values])

                # self.updateRunsGraph()
                self.drawRunsGraph()

    def _selectAncestors(self, childRun=None):

        children = []
        # If parent param not passed...
        if childRun is None:
            # ..use selection, must be first call
            for protId in self._selection:
                run = self.runsGraph.getNode(str(protId))
                children.append(run)
        else:
            name = childRun.getName()

            if not name.isdigit():
                return
            else:
                name = int(name)

            # If already selected (may be this should be centralized)
            if name not in self._selection:
                children = (childRun,)
                self._selection.append(name)
        # Go up .
        for run in children:
            # Select himself plus ancestors
            for parent in run.getParents():
                self._selectAncestors(parent)
        # Only update selection at the end, avoid recursion
        if childRun is None:
            self._lastSelectedProtId = None
            self._updateSelection()
            self.drawRunsGraph()

    def _exportProtocols(self, defaultPath=None, defaultBasename=None):
        protocols = self._getSelectedProtocols()

        def _export(obj):
            filename = os.path.join(browser.getCurrentDir(),
                                    browser.getEntryValue())
            try:
                if (not os.path.exists(filename) or
                    self.windows.askYesNo("File already exists",
                                          "*%s* already exists, do you want "
                                          "to overwrite it?" % filename)):
                    self.project.exportProtocols(protocols, filename)
                    self.windows.showInfo("Workflow successfully saved to '%s' "
                                          % filename)
                else:  # try again
                    self._exportProtocols(defaultPath=browser.getCurrentDir(),
                                          defaultBasename=browser.getEntryValue())
            except Exception as ex:
                import traceback
                traceback.print_exc()
                self.windows.showError(str(ex))

        browser = pwgui.browser.FileBrowserWindow(
            "Choose .json file to save workflow",
            master=self.windows,
            path=defaultPath or self.project.getPath(''),
            onSelect=_export,
            entryLabel='File  ', entryValue=defaultBasename or 'workflow.json')
        browser.show()

    def _exportUploadProtocols(self):
        try:
            jsonFn = os.path.join(tempfile.mkdtemp(), 'workflow.json')
            self.project.exportProtocols(self._getSelectedProtocols(), jsonFn)
            WorkflowRepository().upload(jsonFn)
            pwutils.cleanPath(jsonFn)
        except Exception as ex:
            self.windows.showError("Error connecting to workflow repository:\n"
                                   + str(ex))

    def _stopProtocol(self, prot):
        if pwgui.dialog.askYesNo(Message.TITLE_STOP_FORM,
                                 Message.LABEL_STOP_FORM, self.root):
            self.project.stopProtocol(prot)
            self._lastStatus = None  # force logs to re-load
            self._scheduleRunsUpdate()

    def _analyzeResults(self, prot):
        viewers = self.domain.findViewers(prot.getClassName(), DESKTOP_TKINTER)
        if len(viewers):
            # Instantiate the first available viewer
            # TODO: If there are more than one viewer we should display
            # TODO: a selection menu
            firstViewer = viewers[0](project=self.project, protocol=prot,
                                     parent=self.windows)

            if isinstance(firstViewer, ProtocolViewer):
                firstViewer.visualize(prot, windows=self.windows)
            else:
                firstViewer.visualize(prot)
        else:
            for _, output in prot.iterOutputAttributes():
                viewers = self.domain.findViewers(output.getClassName(), DESKTOP_TKINTER)
                if len(viewers):
                    # Instantiate the first available viewer
                    # TODO: If there are more than one viewer we should display
                    # TODO: a selection menu
                    viewerclass = viewers[0]
                    firstViewer = viewerclass(project=self.project,
                                              protocol=prot,
                                              parent=self.windows)
                    # FIXME:Probably o longer needed protocol on args, already provided on init
                    firstViewer.visualize(output, windows=self.windows,
                                          protocol=prot)

    def _analyzeResultsClicked(self, e=None):
        """ Function called when button "Analyze results" is called. """
        prot = self.getSelectedProtocol()

        # Nothing selected
        if prot is None:
            return

        if os.path.exists(prot._getPath()):
            self._analyzeResults(prot)
        else:
            self.windows.showInfo("Selected protocol hasn't been run yet.")

    def _bibExportClicked(self, e=None):
        try:
            bibTexCites = OrderedDict()
            for prot in self._iterSelectedProtocols():
                bibTexCites.update(prot.getCitations(bibTexOutput=True))
                bibTexCites.update(prot.getPackageCitations(bibTexOutput=True))

            if bibTexCites:
                with tempfile.NamedTemporaryFile(suffix='.bib') as bibFile:
                    for refId, refDict in bibTexCites.items():
                        # getCitations does not always return a dictionary
                        # if the citation is not found in the bibtex file it adds just
                        # the refId: like "Ramirez-Aportela-2019"
                        # we need to exclude this
                        if isinstance(refDict, dict):
                            refType = refDict['ENTRYTYPE']
                            # remove 'type' and 'id' keys
                            refDict = {k: v for k, v in refDict.items()
                                       if k not in ['ENTRYTYPE', 'ID']}
                            jsonStr = json.dumps(refDict, indent=4,
                                                 ensure_ascii=False)[1:]
                            jsonStr = jsonStr.replace('": "', '"= "')
                            jsonStr = re.sub('(?<!= )"(\S*?)"', '\\1', jsonStr)
                            jsonStr = jsonStr.replace('= "', ' = "')
                            refStr = '@%s{%s,%s\n\n' % (refType, refId, jsonStr)
                            bibFile.write(refStr.encode('utf-8'))
                        else:
                            print("WARNING: reference %s not properly defined or unpublished." % refId)
                    # flush so we can see content when opening
                    bibFile.flush()
                    pwgui.text.openTextFileEditor(bibFile.name)

        except Exception as ex:
            self.windows.showError(str(ex))

        return

    def _renameProtocol(self, prot):
        """ Open the EditObject dialog to edit the protocol name. """
        kwargs = {}
        if self._lastRightClickPos:
            kwargs['position'] = self._lastRightClickPos

        dlg = pwgui.dialog.EditObjectDialog(self.runsGraphCanvas, Message.TITLE_EDIT_OBJECT,
                                            prot, self.project.mapper, **kwargs)
        if dlg.resultYes():
            self._updateProtocol(prot)

    def _runActionClicked(self, action):
        prot = self.getSelectedProtocol()
        if prot:
            try:
                if action == ACTION_DEFAULT:
                    pass
                elif action == ACTION_EDIT:
                    self._openProtocolForm(prot)
                elif action == ACTION_RENAME:
                    self._renameProtocol(prot)
                elif action == ACTION_COPY:
                    self._copyProtocols()
                elif action == ACTION_DELETE:
                    self._deleteProtocol()
                elif action == ACTION_STEPS:
                    self._browseSteps()
                elif action == ACTION_BROWSE:
                    self._browseRunDirectory()
                elif action == ACTION_DB:
                    self._browseRunData()
                elif action == ACTION_STOP:
                    self._stopProtocol(prot)
                elif action == ACTION_CONTINUE:
                    self._continueProtocol(prot)
                elif action == ACTION_RESULTS:
                    self._analyzeResults(prot)
                elif action == ACTION_EXPORT:
                    self._exportProtocols(defaultPath=pwutils.getHomePath())
                elif action == ACTION_EXPORT_UPLOAD:
                    self._exportUploadProtocols()
                elif action == ACTION_COLLAPSE:
                    nodeInfo = self.settings.getNodeById(prot.getObjId())
                    nodeInfo.setExpanded(False)
                    self.updateRunsGraph(True, reorganize=True)
                    self._updateActionToolbar()
                elif action == ACTION_EXPAND:
                    nodeInfo = self.settings.getNodeById(prot.getObjId())
                    nodeInfo.setExpanded(True)
                    self.updateRunsGraph(True, reorganize=True)
                    self._updateActionToolbar()
                elif action == ACTION_LABELS:
                    self._selectLabels()
                elif action == ACTION_SELECT_TO:
                    self._selectAncestors()
                elif action == ACTION_RESTART_WORKFLOW:
                    self._launchWorkFlow(action)
                elif action == ACTION_CONTINUE_WORKFLOW:
                    self._launchWorkFlow(action)
                elif action == ACTION_STOP_WORKFLOW:
                    self._stopWorkFlow(action)
                elif action == ACTION_RESET_WORKFLOW:
                    self._resetWorkFlow(action)

            except Exception as ex:
                self.windows.showError(str(ex))
                if Config.debugOn():
                    import traceback
                    traceback.print_exc()

        # Following actions do not need a select run
        if action == ACTION_TREE:
            self.updateRunsGraph(True, reorganize=True)
        elif action == ACTION_REFRESH:
            self.refreshRuns(checkPids=True)

        elif action == ACTION_SWITCH_VIEW:
            self.switchRunsView()


class RunBox(pwgui.TextBox):
    """ Just override TextBox move method to keep track of 
    position changes in the graph.
    """

    def __init__(self, nodeInfo, canvas, text, x, y, bgColor, textColor):
        pwgui.TextBox.__init__(self, canvas, text, x, y, bgColor, textColor)
        self.nodeInfo = nodeInfo
        canvas.addItem(self)

    def move(self, dx, dy):
        pwgui.TextBox.move(self, dx, dy)
        self.nodeInfo.setPosition(self.x, self.y)

    def moveTo(self, x, y):
        pwgui.TextBox.moveTo(self, x, y)
        self.nodeInfo.setPosition(self.x, self.y)


def inspectObj(obj, filename, prefix='', maxDeep=5, inspectDetail=2, memoryDict=None):
    """ Creates a .CSV file in the filename path with
        all its members and recursively with a certain maxDeep,
        if maxDeep=0 means no maxDeep (until all members are inspected).
        
        inspectDetail can be:
         - 1: All attributes are shown
         - 2: All attributes are shown and iterable values are also inspected

        prefix and memoryDict will be updated in the recursive entries:
         - prefix is a compound of the two first columns (DEEP and Tree)
         - memoryDict is a dictionary with the memory address and an identifier
    """
    END_LINE = '\n'  # end of line char
    COL_DELIM = '\t'  # column delimiter
    INDENT_COUNTER = '/'  # character append in each indention (it's not written)

    NEW_CHILD = '  |------>  '  # new item indention
    BAR_CHILD = '  | ' + INDENT_COUNTER  # bar indention
    END_CHILD = ('       -- '+COL_DELIM)*4 + END_LINE  # Child ending
    column1 = '    - Name - ' + COL_DELIM
    column2 = '    - Type - ' + COL_DELIM
    column3 = '    - Value - ' + COL_DELIM
    column4 = '  - Memory Address -'

    #  Constants to distinguish the first, last and middle rows
    IS_FIRST = 1
    IS_LAST = -1
    IS_MIDDLE = 0

    memoryDict = memoryDict or {}

    def writeRow(name, value, prefix, posList=False):
        """ Writes a row item. """
        # we will avoid to recursively print the items wrote before 
        #  (ie. with the same memory address), thus we store a dict with the
        #  addresses and the flag isNew is properly set
        if str(hex(id(value))) in memoryDict:
            memorySTR = memoryDict[str(hex(id(value)))]
            isNew = False
        else:
            # if the item is new, we save its memory address in the memoryDict
            #   and we pass the name and the line on the file as a reference.
            memorySTR = str(hex(id(value)))
            file = open(filename, 'r')
            lineNum = str(len(file.readlines())+1)
            file.close()
            nameDict = str(name)[0:15]+' ...' if len(str(name)) > 25 else str(name)
            memoryDict[str(hex(id(value)))] = '>>> '+nameDict + ' - L:'+lineNum
            isNew = True
        
        if posList:
            # if we have a List, the third column is 'pos/lenght'
            thirdCol = posList
        else:
            # else, we print the value avoiding the EndOfLine char (// instead)
            thirdCol = str(value).replace(END_LINE, ' // ')

        # we will print the indentation deep number in the first row
        indentionDeep = prefix.count(INDENT_COUNTER)
        deepStr = str(indentionDeep) + COL_DELIM

        # the prefix without the indentCounters is 
        #   the tree to be printed in the 2nd row
        prefixToWrite = prefix.replace(INDENT_COUNTER, '')
        
        file = open(filename, 'a')   
        file.write(deepStr + prefixToWrite + COL_DELIM +
                   str(name) + COL_DELIM +
                   str(type(value)) + COL_DELIM +
                   thirdCol + COL_DELIM +
                   memorySTR + END_LINE)
        file.close()

        return isNew

    def recursivePrint(value, prefix, isFirstOrLast):
        """ We print the childs items of tuples, lists, dicts and classes. """ 

        # if it's the last item, its childs has not the bar indention
        if isFirstOrLast == IS_LAST:  # void indention when no more items
            prefixList = prefix.split(INDENT_COUNTER)
            prefixList[-2] = prefixList[-2].replace('|', ' ')
            prefix = INDENT_COUNTER.join(prefixList)

        # recursive step with the new prefix and memory dict.
        inspectObj(value, filename, prefix+BAR_CHILD, maxDeep, inspectDetail, 
                   memoryDict)
        
        if isFirstOrLast == IS_FIRST:
            deepStr = str(indentionDeep) + COL_DELIM
        else:
            # When it was not the first item, the deep is increased
            #   to improve the readability when filter 
            deepStr = str(indentionDeep+1) + COL_DELIM

        prefix = prefix.replace(INDENT_COUNTER, '') + COL_DELIM

        # We introduce the end of the child and 
        #   also the next header while it is not the last
        file = open(filename, 'a')
        file.write(deepStr + prefix + END_CHILD)
        if isFirstOrLast != IS_LAST:
            # header
            file.write(deepStr + prefix + 
                       column1 + column2 + column3 + column4 + END_LINE)
        file.close()

    def isIterable(obj):
        """ Returns true if obj is a tuple, list, dict or calls. """
        isTupleListDict = (isinstance(obj, tuple) or
                           isinstance(obj, dict) or
                           isinstance(obj, list)) and len(value) > 1

        # FIX ME: I don't know how to assert if is a class or not... 
        isClass = str(type(obj))[1] == 'c'

        return isClass or (isTupleListDict and inspectDetail < 2)

    indentionDeep = prefix.count(INDENT_COUNTER)
    if indentionDeep == 0:
        prefix = ' - Root - '

        # dict with name and value pairs of the members
        if len(obj) == 1:
            # if only one obj is passed in the input list,
            #   we directly inspect that obj.
            obj_dict = obj[0].__dict__
            obj = obj[0]

        #  setting the header row
        treeHeader = ' - Print on ' + str(dt.datetime.now())
        prefixHeader = '-DEEP-' + COL_DELIM + treeHeader + COL_DELIM
        col1 = '    - Name - (value for Lists and Tuples)' + COL_DELIM
        col3 = '    - Value - (Pos./Len for Lists and Tuples) ' + COL_DELIM

        #  writing the header row
        file = open(filename, 'w')
        file.write(prefixHeader + col1 + column2 + col3 + column4 + END_LINE)
        file.close()

        #  writing the root object
        writeRow(obj.__class__.__name__, obj, prefix)
        #  adding the child bar to the prefix
        prefix = '  ' + BAR_CHILD
    else:
        # firsts settings depending on the type of the obj
        if str(type(obj))[1] == 'c':
            obj_dict = obj.__dict__
        elif (isinstance(obj, tuple) or
              isinstance(obj, list)):
            column1 = '    - Value - ' + COL_DELIM
            column3 = '  - Pos./Len. - ' + COL_DELIM
        elif isinstance(obj, dict):
            column1 = '    - Key - ' + COL_DELIM
            obj_dict = obj
        else:  # if is not of the type above it not make sense to continue
            return

    indentionDeep = prefix.count(INDENT_COUNTER)
    deepStr = str(indentionDeep) + COL_DELIM
    isBelowMaxDeep = indentionDeep < maxDeep if maxDeep > 0 else True 

    prefixToWrite = prefix.replace(INDENT_COUNTER, '') + COL_DELIM
    file = open(filename, 'a')
    file.write(deepStr + prefixToWrite + 
               column1 + column2 + column3 + column4 + END_LINE)
    file.close()

    #  we update the prefix to put the NEW_CHILD string  ( |----> )
    prefixList = prefix.split(INDENT_COUNTER)
    prefixList[-2] = NEW_CHILD
    #  we return to the string structure
    #    with a certain indention if it's the root
    prefixToWrite = '  ' + INDENT_COUNTER.join(prefixList) if indentionDeep == 1 \
        else INDENT_COUNTER.join(prefixList)

    isNew = True
    if str(type(obj))[1] == 'c' or isinstance(obj, dict):
        counter = 0
        for key, value in obj_dict.items():
            counter += 1
            # write the variable
            isNew = writeRow(key, value, prefixToWrite)

            # managing the extremes of the loop
            if counter == 1:
                isFirstOrLast = IS_FIRST
            elif counter == len(obj_dict):
                isFirstOrLast = IS_LAST
            else:
                isFirstOrLast = IS_MIDDLE

            # show attributes for objects and items for lists and tuples 
            if isBelowMaxDeep and isNew and isIterable(value):
                recursivePrint(value, prefix, isFirstOrLast)
    else:
        for i in range(0, len(obj)):
            # write the variable
            isNew = writeRow(obj[i], obj[i], prefixToWrite, 
                             str(i+1)+'/'+str(len(obj)))

            # managing the extremes of the loop
            if i == 0:
                isFirstOrLast = IS_FIRST
            elif len(obj) == i+1:
                isFirstOrLast = IS_LAST
            else:
                isFirstOrLast = IS_MIDDLE

            # show attributes for objects and items for lists and tuples 
            if isBelowMaxDeep and isNew and isIterable(obj[i]):
                recursivePrint(obj[i], prefix, isFirstOrLast)


class ProtocolTreeConfig:
    """ Handler class that groups functions and constants
    related to the protocols tree configuration.
    """
    ALL_PROTOCOLS = "All"
    TAG_PROTOCOL_DISABLED = 'protocol-disabled'
    TAG_PROTOCOL = 'protocol'
    TAG_SECTION = 'section'
    TAG_PROTOCOL_GROUP = 'protocol_group'
    PLUGIN_CONFIG_PROTOCOLS = 'protocols.conf'

    @classmethod
    def getProtocolTag(cls, isInstalled):
        """ Return the proper tag depending if the protocol is installed or not.
        """
        return cls.TAG_PROTOCOL if isInstalled else cls.TAG_PROTOCOL_DISABLED

    @classmethod
    def isAFinalProtocol(cls, v, k):
        if (issubclass(v, ProtocolViewer) or
                v.isBase() or v.isDisabled()):
            return False

        return v.__name__ == k

    @classmethod
    def __addToTree(cls, menu, item, checkFunction=None):
        """ Helper function to recursively add items to a menu.
        Add item (a dictionary that can contain more dictionaries) to menu
        If check function is added will use it to check if the value must be added.
        """
        children = item.pop('children', [])

        if checkFunction is not None:
            add = checkFunction(item)
            if not add:
                return
        subMenu = menu.addSubMenu(**item)  # we expect item={'text': ...}
        for child in children:
            cls.__addToTree(subMenu, child, checkFunction)  # add recursively to sub-menu

        return subMenu

    @classmethod
    def __inSubMenu(cls, child, subMenu):
        """
        Return True if child belongs to subMenu
        """
        for ch in subMenu:
            if child['tag'] == cls.TAG_PROTOCOL:
                if not ch.value.empty() and ch.value == child['value']:
                    return ch
            elif ch.text == child['text']:
                return ch
        return None

    @classmethod
    def _orderSubMenu(cls, session):
        """
        Order all children of a given session:
        The protocols first, then the sessions(the 'more' session at the end)
        """
        lengthSession = len(session.childs)
        if lengthSession > 1:
            childs = session.childs
            lastChildPos = lengthSession - 1
            if childs[lastChildPos].tag == cls.TAG_PROTOCOL:
                for i in range(lastChildPos - 1, -1, -1):
                    if childs[i].tag == cls.TAG_PROTOCOL:
                        break
                    else:
                        tmp = childs[i + 1]
                        childs[i + 1] = childs[i]
                        childs[i] = tmp
            else:
                for i in range(lastChildPos - 1, -1, -1):
                    if childs[i].tag == cls.TAG_PROTOCOL:
                        break
                    elif 'more' in str(childs[i].text).lower():
                        tmp = childs[i + 1]
                        childs[i + 1] = childs[i]
                        childs[i] = tmp

    @classmethod
    def __findTreeLocation(cls, subMenu, children, parent):
        """
        Locate the protocol position in the given view
        """
        for child in children:
            sm = cls.__inSubMenu(child, subMenu)
            if sm is None:
                cls.__addToTree(parent, child, cls.__checkItem)
                cls._orderSubMenu(parent)
            elif child['tag'] == cls.TAG_PROTOCOL_GROUP or child['tag'] == cls.TAG_SECTION:
                cls.__findTreeLocation(sm.childs, child['children'], sm)

    @classmethod
    def __checkItem(cls, item):
        """ Function to check if the protocol has to be added or not.
        Params:
            item: {"tag": "protocol", "value": "ProtImportMovies",
                   "text": "import movies"}
        """
        if item["tag"] != cls.TAG_PROTOCOL:
            return True

        # It is a protocol as this point, get the class name and
        # check if it is disabled
        protClassName = item["value"]
        protClass = Config.getDomain().getProtocols().get(protClassName)

        return False if protClass is None else not protClass.isDisabled()

    @classmethod
    def __addAllProtocols(cls, domain, protocols):
        # Add all protocols
        allProts = domain.getProtocols()

        # Sort the dictionary
        allProtsSorted = OrderedDict(sorted(allProts.items(),
                                            key=lambda e: e[1].getClassLabel()))
        allProtMenu = ProtocolConfig(cls.ALL_PROTOCOLS)
        packages = {}

        # Group protocols by package name
        for k, v in allProtsSorted.items():
            if cls.isAFinalProtocol(v, k):
                packageName = v.getClassPackageName()
                # Get the package submenu
                packageMenu = packages.get(packageName)

                # If no package menu available
                if packageMenu is None:
                    # Add it to the menu ...
                    packageLine = {"tag": "package", "value": packageName,
                                   "text": packageName}
                    packageMenu = cls.__addToTree(allProtMenu, packageLine)

                    # Store it in the dict
                    packages[packageName] = packageMenu

                # Add the protocol
                tag = cls.getProtocolTag(v.isInstalled())

                protLine = {"tag": tag, "value": k,
                            "text": v.getClassLabel(prependPackageName=False)}

                # If it's a new protocol
                if v.isNew() and v.isInstalled():
                    # add the new icon
                    protLine["icon"] = "newProt.gif"

                cls.__addToTree(packageMenu, protLine)

        protocols[cls.ALL_PROTOCOLS] = allProtMenu

    @classmethod
    def __addProtocolsFromConf(cls, protocols, protocolsConfPath):
        """
        Load the protocols in the tree from a given protocols.conf file,
        either the global one in Scipion or defined in a plugin.
        """
        # Populate the protocols menu from the plugin config file.
        if os.path.exists(protocolsConfPath):
            cp = ConfigParser()
            cp.optionxform = str  # keep case
            cp.read(protocolsConfPath)
            #  Ensure that the protocols section exists
            if cp.has_section('PROTOCOLS'):
                for menuName in cp.options('PROTOCOLS'):
                    if menuName not in protocols:  # The view has not been inserted
                        menu = ProtocolConfig(menuName)
                        children = json.loads(cp.get('PROTOCOLS', menuName))
                        for child in children:
                            cls.__addToTree(menu, child, cls.__checkItem)
                        protocols[menuName] = menu
                    else:  # The view has been inserted
                        menu = protocols.get(menuName)
                        children = json.loads(cp.get('PROTOCOLS',
                                                     menuName))
                        cls.__findTreeLocation(menu.childs, children, menu)

    @classmethod
    def load(cls, domain, protocolsConf):
        """ Read the protocol configuration from a .conf file similar to the
        one in scipion/config/protocols.conf,
        which is the default one when no file is passed.
        """
        protocols = OrderedDict()
        # Read the protocols.conf from Scipion (base) and create an initial
        # tree view
        cls.__addProtocolsFromConf(protocols, protocolsConf)

        # Read the protocols.conf of any installed plugin
        pluginDict = domain.getPlugins()
        pluginList = pluginDict.keys()
        for pluginName in pluginList:
            try:

                # if the plugin has a path
                if pwutils.isModuleAFolder(pluginName):
                    # Locate the plugin protocols.conf file
                    protocolsConfPath = os.path.join(
                        pluginDict[pluginName].__path__[0],
                        cls.PLUGIN_CONFIG_PROTOCOLS)
                    cls.__addProtocolsFromConf(protocols, protocolsConfPath)

            except Exception as e:
                print('Failed to read settings. The reported error was:\n  %s\n'
                      'To solve it, fix %s and run again.' % (
                          e, os.path.abspath(protocolsConfPath)))

            # Add all protocols to All view
        cls.__addAllProtocols(Config.getDomain(), protocols)

        return protocols


class ProtocolConfig(MenuConfig):
    """Store protocols configuration """

    def __init__(self, text=None, value=None, **args):
        MenuConfig.__init__(self, text, value, **args)
        if 'openItem' not in args:
            self.openItem.set(self.tag.get() != 'protocol_base')

    def addSubMenu(self, text, value=None, shortCut=None, **args):
        if 'icon' not in args:
            tag = args.get('tag', None)
            if tag == 'protocol':
                args['icon'] = 'python_file.gif'
            elif tag == 'protocol_base':
                args['icon'] = 'class_obj.gif'

        args['shortCut'] = shortCut
        return MenuConfig.addSubMenu(self, text, value, **args)

