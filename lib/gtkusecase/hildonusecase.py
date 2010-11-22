
"""
Support for the Hildon widget set, used in touchscreen phones on Nokia's Maemo platform.
For now highly experimental and not regularly tested.
"""

import hildon, gtk, describer, simulator, guiusecase, widgetadapter, treeviewextract

def addHildonSupport():
    describer.describerClass = Describer
    guiusecase.WidgetAdapter.adapterClass = WidgetAdapter
    Describer.addHildonWidgets()
    simulator.eventTypes += [(hildon.CheckButton , [ simulator.miscevents.ActivateEvent ]),
                             (hildon.AppMenu     , [ AppMenuEvent ])] 


class WidgetAdapter(widgetadapter.WidgetAdapter):
    def isAutoGenerated(self, name):
        return widgetadapter.WidgetAdapter.isAutoGenerated(self, name) or name.startswith("Hildon") 

    def isInstanceOf(self, cls):
        if cls is gtk.TreeView:
            return isinstance(self.widget, treeviewextract.TreeViewHelper)
        else:
            return widgetadapter.WidgetAdapter.isInstanceOf(self, cls)

class AppMenuEvent(simulator.baseevents.SignalEvent):
    signalName = "show"
    def generate(self, *args):
        return self.widget.show()

class Describer(describer.Describer):
    @classmethod
    def addHildonWidgets(cls):
        cls.supportedWidgets = [ hildon.CheckButton ] + cls.supportedWidgets

    def getCheckButtonDescription(self, widget):
        return self.getToggleButtonDescription(widget)
    
    def isCheckWidget(self, button):
        return isinstance(button, hildon.CheckButton) or describer.Describer.isCheckWidget(self, button)


origStackableWindow = hildon.StackableWindow
origGtkTreeView = hildon.GtkTreeView

class StackableWindow(origStackableWindow):
    def __init__(self, *args, **kw):
        origStackableWindow.__init__(self, *args, **kw)
        self.toolbar = None

    def set_edit_toolbar(self, toolbar):
        self.toolbar = toolbar
        origStackableWindow.set_edit_toolbar(self, toolbar)
        
    def get_children(self):
        children = origStackableWindow.get_children(self)
        if self.toolbar:
            children = [ self.toolbar ] + children
        return children

class GtkTreeView(treeviewextract.TreeViewHelper, origGtkTreeView):
    pass

def performInterceptions():
    hildon.StackableWindow = StackableWindow
    hildon.GtkTreeView = GtkTreeView
    return {}
