import usecase.guishared, logging, util, sys, threading
from usecase import applicationEvent
from usecase.definitions import UseCaseScriptError
from java.awt import AWTEvent, Toolkit, Component
from java.awt.event import AWTEventListener, MouseAdapter, MouseEvent, KeyEvent, WindowAdapter, \
     WindowEvent, ComponentEvent, ContainerEvent, ActionListener, ActionEvent, KeyAdapter
from java.lang import IllegalArgumentException
from javax import swing
import SwingLibrary

swinglib = SwingLibrary()

def selectWindow(widget):
    w = checkWidget(widget)
    window = swing.SwingUtilities.getWindowAncestor(w)
    if isinstance(window, swing.JFrame):
        swinglib.runKeyword("selectWindow", [ window.getTitle() ])
    elif isinstance(window, swing.JDialog):
        swinglib.runKeyword("selectDialog", [ window.getTitle() ])

def checkWidget(widget):
    if isinstance(widget, swing.JMenuItem):
        return widget.getParent().getInvoker()
    return widget
        
class WidgetAdapter(usecase.guishared.WidgetAdapter):
    # All the standard message box texts
    dialogTexts = [ "OK", "Cancel", "Yes", "No", "Abort", "Retry", "Ignore" ]
    
    def getChildWidgets(self):
        if isinstance(self.widget, swing.JMenu):
            return self.widget.getPopupMenu().getSubElements()
        else:
            return self.widget.getComponents()
        
    def getName(self):
        return self.widget.getName() or ""
    
    def getWidgetTitle(self):
        if hasattr(self.widget, "getTitle"):
            return self.widget.getTitle()
        else:
            return ""
            
    def isAutoGenerated(self, name):
        return name == "frame0" or name.startswith("OptionPane") or len(name) == 0
    
    def getLabel(self):
        text = ""
        if hasattr(self.widget, "getLabel"):
            text =  self.widget.getLabel()
        else:
            return ""
        if text in self.dialogTexts:
            dialogTitle = self.getDialogTitle()
            if dialogTitle:
                return text + ", Dialog=" + dialogTitle
        return text
    
    def getDialogTitle(self):
        return swing.SwingUtilities.getWindowAncestor(self.widget).getTitle()

usecase.guishared.WidgetAdapter.adapterClass = WidgetAdapter

# Jython has problems with exceptions thrown from Java callbacks
# Print them out and continue, don't just lose them...
def catchAll(method, *args):
    try:
        method(*args)
    except:
        sys.stderr.write(usecase.guishared.getExceptionString() + "\n")

class SignalEvent(usecase.guishared.GuiEvent):
                
    def generate(self, *args):
        self.setNameIfNeeded()
        selectWindow(self.widget.widget)
        self._generate(*args)
            
    def connectRecord(self, method):
        class ClickListener(MouseAdapter):
            def mousePressed(listenerSelf, event):
                listenerSelf.pressedEvent = event
            
            def mouseReleased(listenerSelf, event):
                catchAll(method, listenerSelf.pressedEvent, event, self)

        util.runOnEventDispatchThread(self.widget.widget.addMouseListener, ClickListener())
        

    def shouldRecord(self, event, *args):
        return Filter.getEventFromUser(event)
    
    def setNameIfNeeded(self):
        mapId = self.widget.getUIMapIdentifier()
        if not mapId.startswith("Name="):
            name = "PyUseCase map ID: " + mapId + " " + str(id(self))
            self.widget.setName(name)

    def delayLevel(self):
        # If there are events for other windows, implies we should delay as we're in a dialog
        return len(Filter.eventsFromUser)

class FrameCloseEvent(SignalEvent):
    def _generate(self, *args):
        # What happens here if we don't have a title?
        swinglib.runKeyword("closeWindow", [ self.widget.getTitle() ])
  
    def connectRecord(self, method):
        class WindowCloseListener(WindowAdapter):
            def windowClosing(listenerSelf, event):
                catchAll(method, event, self)
            
            def windowClosed(listenerSelf, event):
                catchAll(Filter.stopListening)
                        
        util.runOnEventDispatchThread(self.widget.widget.addWindowListener, WindowCloseListener())
        
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Close"

class SelectEvent(SignalEvent):
    def _generate(self, *args):
        swinglib.runKeyword("clickOnComponent", [ self.widget.getName()])
        
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Click"

    def shouldRecord(self, event, *args):
        if event.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and event.getClickCount() == 1:
            return Filter.getEventFromUser(event)
        return False

class DoubleClickEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "DoubleClick"
    
    def shouldRecord(self, oldEvent, newEvent, *args):
        return Filter.getEventFromUser(oldEvent) and newEvent.getModifiers() & \
        MouseEvent.BUTTON1_MASK != 0 and newEvent.getClickCount() == 2
        
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, SelectEvent)
        
class ButtonClickEvent(SelectEvent):
    def connectRecord(self, method):
        SelectEvent.connectRecord(self, method)
        class FakeActionListener(ActionListener):
            def actionPerformed(lself, event):
                catchAll(self.tryApplicationEvent, event)
                    
        util.runOnEventDispatchThread(self.widget.widget.addActionListener, FakeActionListener())

    def tryApplicationEvent(self, event):
        if isinstance(event.getSource(), swing.JButton) and event.getActionCommand() is not None and \
               event.getActionCommand().startswith("ApplicationEvent"):
            applicationEvent(event.getActionCommand().replace("ApplicationEvent", "").lstrip())

    
class StateChangeEvent(SelectEvent):
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateText(*args) ])

    def isStateChange(self, *args):
        return True
    
class MenuSelectEvent(SelectEvent):    
    def _generate(self, *args):
        path = util.getMenuPathString(self.widget)
        swinglib.runKeyword("selectFromMenuAndWait", [ path ])

    def shouldRecord(self, event, *args):
        return not isinstance(event.getSource(), swing.JMenu) and SelectEvent.shouldRecord(self, event, *args)

class TabSelectEvent(SelectEvent):
    def isStateChange(self):
        return True
                    
    def _generate(self, argumentString):
        swinglib.runKeyword("selectTab", [ argumentString ])
    
    def outputForScript(self, event, *args):
        swinglib.runKeyword("selectWindow", [ swing.SwingUtilities.getWindowAncestor(self.widget.widget).getTitle()])
        #Should be used when more than one TabbedPane exist: swinglib.runKeyword("selectTabPane", [ self.widget.getLabel() ])
        text = swinglib.runKeyword("getSelectedTabLabel", [])
        return ' '.join([self.name, text])
     
    def implies(self, *args):
        # State change because it can be implied by TabCloseEvents
        # But don't amalgamate them together, allow several tabs to be selected in sequence
        return False

class ListSelectEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select" 
    
    def _generate(self, argumentString):
        selected = argumentString.split(", ")
        params = [ self.widget.getName() ]
        try:
            swinglib.runKeyword("selectFromList", params + selected)
        except:
            raise UseCaseScriptError, "Could not find item labeled '" + argumentString + "' in list."
    
    def getStateText(self, *args):
        texts = [ util.getJListText(self.widget.widget, i) for i in self.widget.getSelectedIndices() ]
        return ", ".join(texts)
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)

class TableSelectEvent(ListSelectEvent):
    def _generate(self, argumentString):
        # To be used when using multi-selection: selectedCells = argumentString.split(", ")
        params = [ self.widget.getName() ]
        row, column = TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(argumentString)
        # It seems to be a bug in SwingLibrary. Using Column name as argument doesn't work as expected. It throws exceptions
        # for some cell values. 
        swinglib.runKeyword("selectTableCell", params + [row, column])
        
    def getStateText(self, *args):
        text = []
        indexer = TableIndexer.getIndexer(self.widget.widget)
        for row in self.widget.getSelectedRows():
            for col in self.widget.getSelectedColumns():
                text.append(indexer.getCellDescription(row, col))
        return ", ".join(text)

class TableHeaderEvent(SelectEvent):
    def _generate(self, argumentString):
        swinglib.runKeyword("clickTableHeader", [self.widget.getTable().getName(), argumentString])

    def outputForScript(self, event, *args):
        colIndex = self.widget.columnAtPoint(event.getPoint())
        name = self.widget.getTable().getColumnName(colIndex)        
        return SelectEvent.outputForScript(self, event, *args) + " " + name
    
class CellDoubleClickEvent(DoubleClickEvent):
    def isStateChange(self):
        return True
    
    def _generate(self, argumentString):
        row, column = TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(argumentString)            
        swinglib.runKeyword("clickOnTableCell", [self.widget.getName(), row, column, 2, "BUTTON1_MASK" ])
        
    def outputForScript(self, event, *args):
        predefined = DoubleClickEvent.outputForScript(self,event, *args)
        row = self.widget.getSelectedRow()
        col = self.widget.getSelectedColumn()
        desc = TableIndexer.getIndexer(self.widget.widget).getCellDescription(row, col)
        return predefined + " " + desc

class HeaderDoubleClickEvent(DoubleClickEvent):
    def isStateChange(self):
        return True
    
    def _generate(self, argumentString):
        row, column = TableIndexer.getIndexer(self.widget.widget.getTable()).getViewCellIndices(argumentString)            
        swinglib.runKeyword("clickOnTableCell", [self.widget.getName(), row, column, 2, "BUTTON1_MASK" ])
        
    def outputForScript(self, event, *args):
        predefined = DoubleClickEvent.outputForScript(self,event, *args)
        row = self.widget.getTable().getSelectedRow()
        col = self.widget.getTable().getSelectedColumn()
        desc = TableIndexer.getIndexer(self.widget.widget.getTable()).getCellDescription(row, col)
        return predefined + " " + desc
    
class CellEditEvent(StateChangeEvent):
    def _generate(self, argumentString):
        cellDescription, newValue = argumentString.split("=")
        row, column = TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(cellDescription)            
        swinglib.runKeyword("typeIntoTableCell", [self.widget.getName(), row, column, newValue + "\n" ])
    
    def connectRecord(self, method):
        class TableListener(swing.event.TableModelListener):
            def tableChanged(listenerSelf, event):
                if (event.getType() == swing.event.TableModelEvent.UPDATE):                   
                    row = self.widget.getEditingRow()
                    column = self.widget.getEditingColumn()
                    if row >= 0 and column >= 0:
                        method(row, column, self)
                    
        util.runOnEventDispatchThread(self.widget.widget.getModel().addTableModelListener, TableListener())
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, CellEditEvent) or isinstance(stateChangeEvent, CellDoubleClickEvent) or isinstance(stateChangeEvent, TableSelectEvent)
    
    def getStateText(self, row, col, *args):
        cellEditor = self.widget.getCellEditor()
        if cellEditor is not None:
            value = cellEditor.getCellEditorValue()
        else:
            value = self.widget.getValueAt(row, col)
        return str(TableIndexer.getIndexer(self.widget.widget).getCellDescription(row, col)) + "=" + str(value)
            
    def shouldRecord(self, row, col, *args):
        return True
    
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Edited" 

class TextEditEvent(StateChangeEvent):
    def connectRecord(self, method):
        class TextEventListener(KeyAdapter):
            def keyReleased(lself, event):
                method(event, self)

        ancestor = swing.SwingUtilities.getAncestorOfClass(swing.JTable, self.widget.widget)
        if ancestor is None:
            util.runOnEventDispatchThread(self.widget.widget.addKeyListener, TextEventListener())

    def _generate(self, argumentString):
        swinglib.runKeyword("clearTextField", [self.widget.getName()])
        swinglib.runKeyword("typeIntoTextField", [self.widget.getName(), argumentString])
    
    def getStateText(self, event, *args):
        return self.widget.getText()

    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Modify"
    
    def shouldRecord(self, row, col, *args):
        return True
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, TextEditEvent)

class Filter:
    eventsFromUser = []
    ignoredWidgets = [swing.JTextField]
    logger = None
    eventListener = None
    def __init__(self, uiMap):
        Filter.logger = logging.getLogger("usecase record")
        self.uiMap = uiMap

    @classmethod
    def getEventFromUser(cls, event):
        if event in cls.eventsFromUser:
            cls.eventsFromUser.remove(event)
            cls.logger.debug("Filter matched for event " + event.toString())
            return True
        else:
            if len(cls.eventsFromUser) == 0:
                cls.logger.debug("Rejecting event, it has not yet been seen in the display filter")
            else:
                cls.logger.debug("Received event " + repr(event))
                cls.logger.debug("Rejecting event, not yet processed " + repr([ repr(e) for e in cls.eventsFromUser ]))
            return False
        
    def getWindow(self, widget):
        return swing.SwingUtilities.getWindowAncestor(widget)
    
    def hasEventOnWindow(self, widget):
        currWindow = self.getWindow(widget)
        if not currWindow:
            return False

        for event in self.eventsFromUser:
            if self.getWindow(event.getSource()) is currWindow:
                return True
        return False
    
    def startListening(self, handleNewComponent):
        eventMask = AWTEvent.MOUSE_EVENT_MASK | AWTEvent.KEY_EVENT_MASK | AWTEvent.WINDOW_EVENT_MASK | \
                    AWTEvent.COMPONENT_EVENT_MASK | AWTEvent.ACTION_EVENT_MASK | AWTEvent.CONTAINER_EVENT_MASK
        # Should be commented out if we need to listen to these events:
        #| AWTEvent.ITEM_EVENT_MASK | AWTEvent.INPUT_METHOD_EVENT_MASk
        
        class AllEventListener(AWTEventListener):
            def eventDispatched(listenerSelf, event):
                # Primarily to make coverage work, it doesn't get enabled in threads made by Java
                if hasattr(threading, "_trace_hook") and threading._trace_hook:
                    sys.settrace(threading._trace_hook)

                if event.getID() == ComponentEvent.COMPONENT_SHOWN:
                    handleNewComponent(event.getSource())
                elif event.getID() == ContainerEvent.COMPONENT_ADDED:
                    handleNewComponent(event.getChild())
                else:
                    self.handleEvent(event)
        
        self.eventListener = AllEventListener()
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, self.eventListener, eventMask)
    
    @classmethod
    def stopListening(cls):
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().removeAWTEventListener, cls.eventListener)
    
    def handleEvent(self, event):
        if isinstance(event.getSource(), Component):
            if self.addToFilter(event) and not self.hasEventOnWindow(event.getSource()) and not event.getSource().__class__ in self.ignoredWidgets and self.uiMap.scriptEngine.checkType(event.getSource()):
                self.logger.debug("Filter for event " + event.toString())
                self.eventsFromUser.append(event)
    
    def addToFilter(self, event):
        for cls in [ MouseEvent, KeyEvent, WindowEvent, ComponentEvent, ActionEvent ]:
            if isinstance(event, cls):
                return getattr(self, "handle" + cls.__name__)(event)
        return True
            
    def handleMouseEvent(self, event):
        return event.getID() == MouseEvent.MOUSE_PRESSED and not isinstance(event.getSource(), swing.JMenu)
            
    def handleKeyEvent(self, event):
        # TODO: to be implemented
        return False
        
    def handleWindowEvent(self, event):
        return event.getID() == WindowEvent.WINDOW_CLOSING or self.handleComponentEvent(event)
    
    def handleComponentEvent(self, event):       
        return False #TODO: return event.getID() == ComponentEvent.COMPONENT_RESIZED

    def handleActionEvent(self, event):
        return False
    
class TableIndexer():
    allIndexers = {}
    def __init__(self, table):
        self.tableModel = table.getModel()
        self.table = table
        self.logger = logging.getLogger("TableModelIndexer")
        self.rowNames = self.findRowNames()
        self.observeUpdates()
        self.logger.debug("Creating table indexer with rows " + repr(self.rowNames))

    def observeUpdates(self):
        class TableListener(swing.event.TableModelListener):
            def tableChanged(listenerSelf, event):
                if (event.getType() == swing.event.TableModelEvent.INSERT or event.getType() == swing.event.TableModelEvent.DELETE):
                    self.rowNames = self.findRowNames()

        util.runOnEventDispatchThread(self.table.getModel().addTableModelListener, TableListener())

    @classmethod
    def getIndexer(cls, table):
        # Don't just do setdefault, shouldn't create the TableIndexer if it already exists
        if table in cls.allIndexers:
            return cls.allIndexers.get(table)
        else:
            return cls.allIndexers.setdefault(table, cls(table))

    def getColumn(self, col):
        return [ self.tableModel.getValueAt(row, col) or "" for row in range(self.tableModel.getRowCount()) ]

    def findRowNames(self):
        for colIndex in range(self.tableModel.getColumnCount()):
            column = self.getColumn(colIndex)
            if len(set(column)) == len(column):
                return column
        # No unique columns to use as row names. Use the first row and add numbers
        return self.addIndexes(self.getColumn(0))

    def getIndexedValue(self, index, value, mapping):
        indices = mapping.get(value)
        if len(indices) == 1:
            return value
        else:
            return value + " (" + str(indices.index(index) + 1) + ")"

    def addIndexes(self, values):
        mapping = {}
        for i, value in enumerate(values):
            mapping.setdefault(value, []).append(i)

        return [ self.getIndexedValue(i, v, mapping) for i, v in enumerate(values) ]

    def parseDescription(self, description):
        if " for " in description:
            columnName, rowName = description.split(" for ")
            try:
                return rowName, self.table.getColumn(columnName).getModelIndex()
            except IllegalArgumentException:
                raise UseCaseScriptError, "Could not find column labelled '" + columnName + "' in table."
        else:
            return description, 0
    
    def getViewCellIndices(self, description):
        rowName, columnIndex = self.parseDescription(description)
        try:
            rowModelIndex = self.rowNames.index(rowName)
            return self.getViewIndices(rowModelIndex, columnIndex)
        except ValueError:
            raise UseCaseScriptError, "Could not find row identified by '" + rowName + "' in table."
            
    def getViewIndices(self, row, column):
        return self.table.convertRowIndexToView(row), self.table.convertColumnIndexToView(column)
        
    def getCellDescription(self, row, col):
        name = self.table.getValueAt(row, col)
        rowName = self.rowNames[self.table.convertRowIndexToModel(row)]
        if self.tableModel.getColumnCount() == 1:
            return rowName
        else:
            return self.table.getColumnName(col) + " for " + rowName

