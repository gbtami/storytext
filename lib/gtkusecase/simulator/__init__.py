
""" Main entry point for simulator functionality """

import baseevents, windowevents, filechooserevents, treeviewevents, miscevents, gtk, guiusecase

performInterceptions = miscevents.performInterceptions
origDialog = gtk.Dialog
origFileChooserDialog = gtk.FileChooserDialog    

class DialogHelper:
    def tryMonitor(self):
        if self.uiMap.scriptEngine.recorderActive():
            self.connect_for_real = self.connect
            self.connect = self.store_connect
            
    def store_connect(self, signalName, *args):
        windowevents.ResponseEvent.storeApplicationConnect(self, signalName, *args)
        

class Dialog(DialogHelper, origDialog):
    uiMap = None
    def __init__(self, *args, **kw):
        origDialog.__init__(self, *args, **kw)
        self.tryMonitor()


class FileChooserDialog(DialogHelper, origFileChooserDialog):
    uiMap = None
    def __init__(self, *args, **kw):
        origFileChooserDialog.__init__(self, *args, **kw)
        self.tryMonitor()


class UIMap(guiusecase.UIMap):
    ignoreWidgetTypes = [ "Label" ]
    def __init__(self, *args): 
        guiusecase.UIMap.__init__(self, *args)
        gtk.Dialog = Dialog
        Dialog.uiMap = self
        gtk.FileChooserDialog = FileChooserDialog
        FileChooserDialog.uiMap = self
        gtk.quit_add(1, self.fileHandler.write) # Write changes to the GUI map when the application exits
                                     
    def tryAutoInstrument(self, eventName, signature, signaturesInstrumented, *args):
        signature = signature.replace("notify-", "notify::")
        return guiusecase.UIMap.tryAutoInstrument(self, eventName, signature, signaturesInstrumented, *args)
    
    def monitorChildren(self, widget, *args, **kw):
        if widget.getName() != "Shortcut bar" and \
               not widget.isInstanceOf(gtk.FileChooser) and not widget.isInstanceOf(gtk.ToolItem):
            guiusecase.UIMap.monitorChildren(self, widget, *args, **kw)

    def monitorWindow(self, window):
        if window.isInstanceOf(origDialog):
            # Do the dialog contents before we do the dialog itself. This is important for FileChoosers
            # as they have things that use the dialog signals
            self.logger.debug("Monitoring children for dialog with title " + repr(window.getTitle()))
            self.monitorChildren(window, excludeWidgets=self.getResponseWidgets(window, window.action_area))
            self.monitorWidget(window)
            windowevents.ResponseEvent.connectStored(window)
        else:
            guiusecase.UIMap.monitorWindow(self, window)

    def getResponseWidgets(self, dialog, widget):
        widgets = []
        for child in widget.get_children():
            if dialog.get_response_for_widget(child) != gtk.RESPONSE_NONE:
                widgets.append(child)
        return widgets

eventTypes = [
        (gtk.Button           , [ baseevents.SignalEvent ]),
        (gtk.ToolButton       , [ baseevents.SignalEvent ]),
        (gtk.MenuItem         , [ miscevents.MenuItemSignalEvent ]),
        (gtk.CheckMenuItem    , [ miscevents.MenuActivateEvent ]),
        (gtk.ToggleButton     , [ miscevents.ActivateEvent ]),
        (gtk.ToggleToolButton , [ miscevents.ActivateEvent ]),
        (gtk.ComboBoxEntry    , []), # just use the entry, don't pick up ComboBoxEvents
        (gtk.ComboBox         , [ miscevents.ComboBoxEvent ]),
        (gtk.Entry            , [ miscevents.EntryEvent, 
                                  baseevents.SignalEvent ]),
        (gtk.TextView         , [ miscevents.TextViewEvent ]),
        (gtk.FileChooser      , [ filechooserevents.FileChooserFileSelectEvent, 
                                  filechooserevents.FileChooserFolderChangeEvent, 
                                  filechooserevents.FileChooserEntryEvent ]),
        (gtk.Dialog           , [ windowevents.ResponseEvent, 
                                  windowevents.DeletionEvent ]),
        (gtk.Window           , [ windowevents.DeletionEvent ]),
        (gtk.Notebook         , [ miscevents.NotebookPageChangeEvent ]),
        (gtk.Paned            , [ miscevents.PaneDragEvent ]),
        (gtk.TreeView         , [ treeviewevents.RowActivationEvent, 
                                  treeviewevents.TreeSelectionEvent, 
                                  treeviewevents.RowExpandEvent, 
                                  treeviewevents.RowCollapseEvent, 
                                  treeviewevents.RowRightClickEvent, 
                                  treeviewevents.CellToggleEvent,
                                  treeviewevents.CellEditEvent, 
                                  treeviewevents.TreeColumnClickEvent ])
]

universalEventClasses = [ baseevents.LeftClickEvent, baseevents.RightClickEvent ]
fallbackEventClass = baseevents.SignalEvent