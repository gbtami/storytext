import wx
import inspect

import storytext.guishared
from textlabelfinder import TextLabelFinder



class WidgetAdapter(storytext.guishared.WidgetAdapter):
    def getChildWidgets(self):
        if self.isInstanceOf(wx.MenuItem):
            return []
        children = filter(lambda w: not isinstance(w, wx.Dialog), 
                                                self.widget.GetChildren())
        if self.isInstanceOf(wx.Frame) and self.GetMenuBar() is not None:
            for menu, _ in self.GetMenuBar().GetMenus():
                children += menu.GetMenuItems()
        return children
        
    def getWidgetTitle(self):
        return self.widget.GetTitle() or self.widget.GetMessage()
        
    def getLabel(self):
        if isinstance(self.widget, wx.TextCtrl):
            return TextLabelFinder(self.widget).find()
        elif not isinstance(self.widget, wx.TopLevelWindow):
            return self.widget.GetLabel()
        else:
            return ""

    def isAutoGenerated(self, name):
        if not name:
            return True
        baseclasses = inspect.getmro(self.widget.__class__)
        autoGenNames = [ "check" ] + [ cls.__name__.lower().replace("ctrl", "") for cls in baseclasses ]
        return name.lower().replace("ctrl", "") in autoGenNames

    def getName(self):
        return self.widget.GetName() if hasattr(self.widget, "GetName") else ""
    
    
storytext.guishared.WidgetAdapter.adapterClass = WidgetAdapter