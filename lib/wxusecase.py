
# Experimental and rather basic support for wx

import guiusecase, os, time, wx, logging
from usecase import UseCaseScriptError
from ndict import seqdict

origApp = wx.App

class App(origApp):
    idle_methods = []
    timeout_methods = []

    def setUpHandlers(self):
        for idle_method in self.idle_methods:
            self.GetTopWindow().Bind(wx.EVT_IDLE, idle_method)
        for milliseconds, timeout_method in self.timeout_methods:
            wx.CallLater(milliseconds, timeout_method)

    def MainLoop(self):
        self.setUpHandlers()
        origApp.MainLoop(self)

wx.App = App
        
class WidgetAdapter(guiusecase.WidgetAdapter):
    def getChildWidgets(self):
        return self.widget.GetChildren()
        
    def getWidgetTitle(self):
        return self.widget.GetTitle()
        
    def getLabel(self):
        return self.widget.GetLabel()

    def isAutoGenerated(self, name):
        return self.widget.__class__.__name__.lower() == name

    def getName(self):
        return self.widget.GetName()

guiusecase.WidgetAdapter.adapterClass = WidgetAdapter

class SignalEvent(guiusecase.GuiEvent):
    def connectRecord(self, method):
        def handler(event):
            method(event, self)
            event.Skip()
        self.widget.Bind(self.event, handler)

    @classmethod
    def getAssociatedSignal(cls, widget):
        return cls.signal

class FrameEvent(SignalEvent):
    event = wx.EVT_CLOSE
    signal = 'Close'
            
    def getChangeMethod(self):
        return self.widget.Close

    def generate(self, *args):
        self.changeMethod()

class DialogEvent(SignalEvent):
    event = wx.EVT_CLOSE
    signal = 'DialogClose'
            
    def getChangeMethod(self):
        return self.widget.Close

    def generate(self, *args):
        self.changeMethod()

class ButtonEvent(SignalEvent):
    event = wx.EVT_BUTTON
    signal = 'Press'
            
    def generate(self, *args):
        wx.CallAfter(self.widget.Command, wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, self.widget.GetId())) 

class TextCtrlEvent(SignalEvent):
    event = wx.EVT_TEXT
    signal = 'TextEnter'
        
    def isStateChange(self):
        return True

    def getChangeMethod(self):
        return self.widget.SetValue

    def generate(self, argumentString):
        self.changeMethod(argumentString)

    def outputForScript(self, *args):
        text = self.widget.GetValue()
        return ' '.join([self.name, text])

class ListCtrlEvent(SignalEvent):
    event = wx.EVT_LIST_ITEM_SELECTED
    signal = 'ListCtrlSelect'

    def isStateChange(self):
        return True

    def implies(self, prevLine, *args):
        currOutput = self.outputForScript()
        return currOutput.startswith(prevLine)

    def getChangeMethod(self):
        return self.widget.Select

    def generate(self, argumentString):
        self._clearSelection()
        label_list = argumentString.split(',')
        for label in label_list:
            index = self._findIndex(label)
            self.changeMethod(index, 1)

    def _clearSelection(self):
        for i in range(self.widget.ItemCount):
            self.changeMethod(i, 0)

    def _findIndex(self, label):
        for i in range(self.widget.ItemCount):
            if self.widget.GetItemText(i) == label:
                return i
        raise UseCaseScriptError, "Could not find item '" + label + "' in ListCtrl."

    def outputForScript(self, *args):
        texts = []
        i = -1
        while True:
            i = self.widget.GetNextSelected(i)
            if i == -1:
                break
            else:
                texts.append(self.widget.GetItemText(i))
        return self.name + " " + ",".join(texts)
                

class UseCaseReplayer(guiusecase.UseCaseReplayer):
    def __init__(self, *args, **kw):
        guiusecase.UseCaseReplayer.__init__(self, *args, **kw)
        self.describer = Describer()

    def makeIdleHandler(self, method):
        if wx.GetApp():
            return wx.GetApp().Bind(wx.EVT_IDLE, method)
        else:
            wx.App.idle_methods.append(method)
            return True # anything to show we've got something
                
    def findWindowsForMonitoring(self):
        return wx.GetTopLevelWindows()

    def handleNewWindows(self, *args):
        self.describer.describeUpdates()
        guiusecase.UseCaseReplayer.handleNewWindows(self)

    def describeNewWindow(self, window):
        self.describer.describe(window)

    def removeHandler(self, handler):
        # Need to do this for real handlers, don't need it yet
        wx.App.idle_methods = []

    def makeTimeoutReplayHandler(self, method, milliseconds):
        if wx.GetApp():
            wx.CallLater(milliseconds, method)
        else:
            wx.App.timeout_methods.append((milliseconds, method))
            return True

class ScriptEngine(guiusecase.ScriptEngine):
    eventTypes = [
        (wx.Frame       , [ FrameEvent ]),
        (wx.Dialog      , [ DialogEvent ]),
        (wx.Button      , [ ButtonEvent ]),
        (wx.TextCtrl    , [ TextCtrlEvent ]),
        (wx.ListCtrl    , [ ListCtrlEvent ]),
        ]
    signalDescs = {
        "<<ListCtrlSelect>>": "select item",
        }
    columnSignalDescs = {} 
    def createReplayer(self, universalLogging=False):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventDescriptor in eventClass.getAssociatedSignatures(widget):
                return eventClass(eventName, widget, argumentParseData)
        
    def getDescriptionInfo(self):
        return "wxPython", "wx", "actions", "http://www.wxpython.org/docs/api/"

    def getDocName(self, className):
        return className + "-class"

    def addSignals(self, classes, widgetClass, currEventClasses, module):
        signalNames = set()
        for eventClass in currEventClasses:
            signatures = eventClass.getAssociatedSignatures(None)
            signalNames.update(signatures)
        className = self.getClassName(widgetClass, module)
        classes[className] = sorted(signalNames)

    def getSupportedLogWidgets(self):
        return Describer.statelessWidgets + Describer.stateWidgets

class Describer:
    statelessWidgets = [ wx.Button, wx.ScrolledWindow, wx.Window ]
    stateWidgets = [ wx.Frame, wx.Dialog, wx.ListCtrl, wx.TextCtrl ]
    def __init__(self):
        self.logger = logging.getLogger("gui log")
        self.frames = set()
        self.widgetsWithState = seqdict()

    def describe(self, frame):
        if frame in self.frames:
            return
        self.frames.add(frame)
        message = "-" * 10 + " Frame '" + frame.GetTitle() + "' " + "-" * 10
        self.widgetsWithState[frame] = frame.GetTitle()
        self.logger.info("\n" + message)
        self.logger.info(self.getChildrenDescription(frame))
        footerLength = min(len(message), 100) # Don't let footers become too huge, they become ugly...
        self.logger.info("-" * footerLength)

    # TODO factoring out a parent class for the describers of wx and tkinter
    # this is exactly the same code from tkinterusecase.py
    def describeUpdates(self):
        defunctWidgets = []
        for widget, oldState in self.widgetsWithState.items():
            try:
                state = self.getState(widget)
                if state != oldState:
                    self.logger.info(self.getStateChangeDescription(widget, oldState, state))
                    self.widgetsWithState[widget] = state
            except:
                # If the frame where it existed has been removed, for example...
                defunctWidgets.append(widget)
        for widget in defunctWidgets:
            del self.widgetsWithState[widget]

    def addToDescription(self, desc, newText):
        if newText:
            if desc:
                desc += "\n"
            desc += newText.rstrip() + "\n"
        return desc

    def getDescription(self, widget):
        desc = ""
        desc = self.addToDescription(desc, self.getWidgetDescription(widget))
        desc = self.addToDescription(desc, self.getChildrenDescription(widget))
        return desc.rstrip()
    
    def getChildrenDescription(self, widget):
        slaves = set()
        children = widget.GetChildren()
        desc = ""
        for child in children:
            desc = self.addToDescription(desc, self.getDescription(child))
        
        return desc.rstrip()

    def getWidgetDescription(self, widget):
        for widgetClass in self.stateWidgets + self.statelessWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "Description"
                return getattr(self, methodName)(widget)
        
        return "A widget of type '" + widget.__class__.__name__ + "'" # pragma: no cover - should be unreachable

    def getStateChangeDescription(self, widget, oldState, state):
        return 'updated with new state:\n' + state

    def getState(self, widget):
        state = self.getSpecificState(widget)
        return state.strip()

    def getSpecificState(self, widget):
        for widgetClass in self.stateWidgets:
            if isinstance(widget, widgetClass):
                methodName = "get" + widgetClass.__name__ + "State"
                return getattr(self, methodName)(widget)
        return "Widget state unknown for type '" + widget.__class__.__name__ + "'" # pragma: no cover - unreachable

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = widget.GetLabel()
        if labelText:
            text += " '" + labelText + "'"
        return text

    def getScrolledWindowDescription(self, widget):
        return ""

    def getWindowDescription(self, widget):
        return ""

    def getListCtrlState(self, widget):
        text = ".................\n"
        for i in range(widget.ItemCount):
            if widget.IsSelected(i):
                text += "-> " + widget.GetItemText(i) + "   ***\n"
            else:
                text += "-> " + widget.GetItemText(i) + "\n"
        text += ".................\n"
        return text

    def getListCtrlDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return state

    def getTextCtrlDescription(self, widget):
        text = "Text Control"
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            text += " (preset to '" + state + "')"
        return text

    def getTextCtrlState(self, widget):
        text = widget.GetValue()
        return text

    def getDialogDescription(self, widget):
        text = "Dialog"
        title = widget.GetTitle()
        if title:
            text += " '" + title + "'"
        return text

    def getDialogState(self, widget):
        return widget.GetValue()

    def getFrameState(self, widget):
        return widget.GetTitle()
