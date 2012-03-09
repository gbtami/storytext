
# Experimental and rather basic support for wx

import guishared, os, time, wx, logging, inspect
from definitions import UseCaseScriptError
from ordereddict import OrderedDict

origApp = wx.App

class App(origApp):
    idle_methods = []
    timeout_methods = []

    def setUpHandlers(self):
        for idle_method in self.idle_methods:
            wx.GetApp().Bind(wx.EVT_IDLE, idle_method)
        for milliseconds, timeout_method in self.timeout_methods:
            wx.CallLater(milliseconds, timeout_method)

    def MainLoop(self):
        self.setUpHandlers()
        return origApp.MainLoop(self)

wx.App = App
        
origDialog = wx.Dialog
class DialogHelper:
    def ShowModal(self):
        self.uiMap.scriptEngine.replayer.runMainLoopWithReplay()
        return origDialog.ShowModal(self)

class Dialog(DialogHelper, origDialog):
    pass


class TextLabelFinder:
    def __init__(self, widget):
        self.widget = widget

    def find(self):
        sizer = self.findSizer(self.widget)
        return self.findInSizer(sizer) if sizer is not None else ""

    def findInSizer(self, sizer):
        sizers, widgets = self.findSizerChildren(sizer)
        if self.widget in widgets:
            return guishared.findPrecedingLabel(self.widget, widgets, wx.StaticText, textMethod="GetLabel")
        for subsizer in sizers:
            label = self.findInSizer(subsizer)
            if label is not None:
                return label

    def findSizerChildren(self, sizer):
        sizers, widgets = [], []
        for item in sizer.GetChildren():
            if item.GetWindow():
                widgets.append(item.GetWindow())
            if item.GetSizer():
                sizers.append(item.GetSizer())
        return sizers, widgets
        
    def findSizer(self, widget):
        if widget.GetSizer():
            return widget.GetSizer()
        if widget.GetParent():
            return self.findSizer(widget.GetParent())


class WidgetAdapter(guishared.WidgetAdapter):
    def getChildWidgets(self):
        return filter(lambda w: not isinstance(w, wx.Dialog), self.widget.GetChildren())
        
    def getWidgetTitle(self):
        return self.widget.GetTitle()
        
    def getLabel(self):
        if isinstance(self.widget, wx.TextCtrl):
            return TextLabelFinder(self.widget).find()
        else:
            return self.widget.GetLabel()

    def isAutoGenerated(self, name):
        baseclasses = inspect.getmro(self.widget.__class__)
        return name.lower().replace("ctrl", "") in [ cls.__name__.lower().replace("ctrl", "") for cls in baseclasses ]

    def getName(self):
        return self.widget.GetName()

guishared.WidgetAdapter.adapterClass = WidgetAdapter

class SignalEvent(guishared.GuiEvent):
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


class ButtonEvent(SignalEvent):
    event = wx.EVT_BUTTON
    signal = 'Press'
            
    def generate(self, *args):
        self.widget.Command(wx.CommandEvent(wx.wxEVT_COMMAND_BUTTON_CLICKED, self.widget.GetId())) 

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

    def implies(self, prevOutput, prevEvent, *args):
        return self.widget is prevEvent.widget

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
        index_list = map(self._findIndex, argumentString.split(','))
        self._clearSelection()
        for index in index_list:
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
                

class UIMap(guishared.UIMap):
    def __init__(self, *args):
        guishared.UIMap.__init__(self, *args)
        wx.Dialog = Dialog
        Dialog.uiMap = self

class UseCaseReplayer(guishared.IdleHandlerUseCaseReplayer):
    def __init__(self, *args, **kw):
        guishared.IdleHandlerUseCaseReplayer.__init__(self, *args, **kw)
        self.describer = Describer()

    def makeIdleHandler(self, method):
        if wx.GetApp():
            return wx.CallLater(0, method)
        else:
            wx.App.idle_methods.append(method)
            return True # anything to show we've got something
                
    def findWindowsForMonitoring(self):
        return wx.GetTopLevelWindows()

    def handleNewWindows(self, *args):
        self.describer.describeUpdates()
        guishared.IdleHandlerUseCaseReplayer.handleNewWindows(self)

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

    def runMainLoopWithReplay(self):
        # if it's called before App.MainLoop() the handler needs to be set up here.
        app = wx.GetApp()
        if app.IsMainLoopRunning():
            if self.isActive():
                self.enableReplayHandler()
        else:
            app.setUpHandlers()
        
class ScriptEngine(guishared.ScriptEngine):
    eventTypes = [
        (wx.Frame       , [ FrameEvent ]),
        (wx.Button      , [ ButtonEvent ]),
        (wx.TextCtrl    , [ TextCtrlEvent ]),
        (wx.ListCtrl    , [ ListCtrlEvent ]),
        ]
    signalDescs = {
        "<<ListCtrlSelect>>": "select item",
        }
    columnSignalDescs = {} 

    def createUIMap(self, uiMapFiles):
        return UIMap(self, uiMapFiles)

    def createReplayer(self, universalLogging=False, **kw):
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder, **kw)
        
    def getDescriptionInfo(self):
        return "wxPython", "wx", "actions", "http://www.wxpython.org/docs/api/"

    def getDocName(self, className):
        return className + "-class"

    def getSupportedLogWidgets(self):
        return Describer.statelessWidgets + Describer.stateWidgets

class Describer(guishared.Describer):
    ignoreWidgets = [ wx.ScrolledWindow, wx.Window, wx.Dialog, wx.Sizer ]
    statelessWidgets = [ wx.Button ]
    stateWidgets = [ wx.Frame, wx.Dialog, wx.ListCtrl, wx.TextCtrl, wx.StaticText ]
    visibleMethodName = "IsShown"
    def getWidgetChildren(self, widgetOrSizer):
        # Involve the Sizers, otherwise we have no chance of describing things properly
        # ordinary children structure is not sorted.
        try:
            if isinstance(widgetOrSizer, wx.Sizer):
                children = []
                for item in widgetOrSizer.GetChildren():
                    if item.GetWindow():
                        children.append(item.GetWindow())
                    elif item.GetSizer():
                        children.append(item.GetSizer())
                return children
            elif widgetOrSizer.GetSizer():
                return [ widgetOrSizer.GetSizer() ]
            else:
                return filter(lambda c: not isinstance(c, wx.Dialog), widgetOrSizer.GetChildren())
        except wx._core.PyDeadObjectError:
            # Gets thrown on Windows intermittently, don't know why
            return []

    def isVisible(self, widget, *args):
        return widget.IsShown() if isinstance(widget, wx.Window) else True

    def shouldDescribeChildren(self, widget):
        return True # no hindrances right now...

    def getLayoutColumns(self, widget, *args):
        return widget.GetCols() if isinstance(widget, wx.GridSizer) else 1

    def widgetTypeDescription(self, typeName): # pragma: no cover - should be unreachable
        if "DeadObject" in typeName: # mystery guests on Windows occasionally
            return ""
        else:
            return "A widget of type '" + typeName + "'" 

    def getWindowString(self):
        return "Frame" # wx has different terminology

    def getDialogDescription(self, *args):
        return "" # don't describe it as a child of the main window
        
    def getWindowClasses(self):
        return wx.Frame, wx.Dialog

    def getTextEntryClass(self):
        return wx.TextCtrl

    def getUpdatePrefix(self, widget, *args):
        if isinstance(widget, self.getTextEntryClass()):
            return "\nUpdated " + (TextLabelFinder(widget).find() or "Text") + " Field\n"
        else:
            return "\nUpdated "
        
    def getStaticTextDescription(self, widget):
        return self.getAndStoreState(widget)

    def getStaticTextState(self, widget):
        return "'" + widget.GetLabel() + "'"

    def getButtonDescription(self, widget):
        text = "Button"
        labelText = widget.GetLabel()
        if labelText:
            text += " '" + labelText + "'"
        return text

    def getListCtrlState(self, widget):
        text = "List :\n"
        for i in range(widget.ItemCount):
            if widget.IsSelected(i):
                text += "-> " + widget.GetItemText(i) + "   ***\n"
            else:
                text += "-> " + widget.GetItemText(i) + "\n"
        return text

    def getListCtrlDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return state

    def getTextCtrlDescription(self, widget):
        contents = self.getState(widget)
        self.widgetsWithState[widget] = contents
        return self.addHeaderAndFooter(widget, contents)

    def getTextCtrlState(self, widget):
        value = widget.GetValue()
        return "*" * len(value) if widget.GetWindowStyle() == wx.TE_PASSWORD else value

    def getDialogState(self, widget):
        return widget.GetTitle()

    def getFrameState(self, widget):
        return widget.GetTitle()

    def shouldCheckForUpdates(self, widget, *args):
        # Hack. How to trace the fact that objects in wxPython can change class?!
        return "Dead" not in widget.__class__.__name__
