import usecase.guishared, logging, util, sys, threading, time
from usecase import applicationEvent
from usecase.definitions import UseCaseScriptError
from java.awt import AWTEvent, Toolkit, Component
from java.awt.event import AWTEventListener, MouseAdapter, MouseEvent, KeyEvent, WindowAdapter, \
     WindowEvent, ComponentEvent, ContainerEvent, ActionListener, ActionEvent, InputEvent
from java.lang import IllegalArgumentException, System
from java.io import PrintStream, OutputStream
from javax import swing
from abbot.tester import Robot

# Importing writes uninteresting stuff to stdout
out_orig = System.out
class NullOutputStream(OutputStream):
    def write(self, *args):
        pass

System.setOut(PrintStream(NullOutputStream()))
import SwingLibrary
swinglib = SwingLibrary()
System.setOut(out_orig)

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
        if isinstance(self.widget, swing.text.JTextComponent):
            return util.getTextLabel(self.widget)

        text = ""
        if hasattr(self.widget, "getLabel"):
            text = self.widget.getLabel()
        else:
            return ""
                
        if text in self.dialogTexts:
            dialogTitle = self.getDialogTitle()
            if dialogTitle:
                return text + ", Dialog=" + dialogTitle
        return text
    
    def getTooltip(self):
        if hasattr(self.widget, "getToolTipText"):
            return self.widget.getToolTipText() or ""
        else:
            return ""
    
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
        self.checkWidgetStatus()
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
        return Filter.getEventFromUser(event) and not util.hasComplexAncestors(self.widget.widget)
    
    def setNameIfNeeded(self):
        mapId = self.widget.getUIMapIdentifier()
        if not mapId.startswith("Name="):
            name = "PyUseCase map ID: " + mapId + " " + str(id(self))
            self.widget.setName(name)

    def delayLevel(self):
        return Filter.delayLevel()
    
    def widgetVisible(self):
        return self.widget.isShowing()

    def widgetSensitive(self):
        return self.widget.isEnabled()
    
    def describeWidget(self):
        return " of type " + self.widget.getType()

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
        return event.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and \
               event.getClickCount() == 1 and \
               SignalEvent.shouldRecord(self, event, *args)

class DoubleClickEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "DoubleClick"
    
    def shouldRecord(self, oldEvent, newEvent, *args):
        return newEvent.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and \
               newEvent.getClickCount() == 2 and \
               SignalEvent.shouldRecord(self, oldEvent, newEvent, *args)
        
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, SelectEvent)
        
class ButtonClickEvent(SelectEvent):
    def _generate(self, *args):
        # Just doing clickOnComponent as in SelectEvent ought to work, but doesn't, see
        # http://code.google.com/p/robotframework-swinglibrary/issues/detail?id=175
        swinglib.runKeyword("pushButton", [ self.widget.getName()])

    def connectRecord(self, method):
        SelectEvent.connectRecord(self, method)
        class FakeActionListener(ActionListener):
            def actionPerformed(lself, event):
                catchAll(self.tryApplicationEvent, event)
                    
        util.runOnEventDispatchThread(self.widget.widget.addActionListener, FakeActionListener())

    def tryApplicationEvent(self, event):
        if isinstance(event.getSource(), swing.JButton) and event.getActionCommand() is not None and \
               event.getActionCommand().startswith("ApplicationEvent"):
            appEventName = event.getActionCommand().replace("ApplicationEvent", "").lstrip()
            applicationEvent(appEventName, delayLevel=self.delayLevel())

    
class StateChangeEvent(SelectEvent):
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateText(*args) ])

    def isStateChange(self, *args):
        return True


class TextEditEvent(StateChangeEvent):
    def connectRecord(self, method):
        class TextDocumentListener(swing.event.DocumentListener):
            def insertUpdate(lself, event):
                catchAll(method, event, self)
                
            changedUpdate = insertUpdate
            removeUpdate = insertUpdate

        util.runOnEventDispatchThread(self.widget.getDocument().addDocumentListener, TextDocumentListener())

    def _generate(self, argumentString):
        swinglib.runKeyword("clearTextField", [self.widget.getName()])
        swinglib.runKeyword("insertIntoTextField", [self.widget.getName(), argumentString])

    def getStateText(self, event, *args):        
        return usecase.guishared.removeMarkup(self.widget.getText())

    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Modify"
    
    def shouldRecord(self, row, col, *args):
        # Can get document changes on things that aren't visible
        return self.widget.isShowing() and not util.hasComplexAncestors(self.widget.widget)
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, TextEditEvent)

class ActivateEvent(SignalEvent):
    def connectRecord(self, method):
        class ActivateEventListener(ActionListener):
            def actionPerformed(lself, event):
                method(event, self)
                    
        util.runOnEventDispatchThread(self.widget.widget.addActionListener, ActivateEventListener())
        
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Activate"
    
    def shouldRecord(self, *args):
        return not util.hasComplexAncestors(self.widget.widget)

class TextActivateEvent(ActivateEvent):
    def _generate(self, argumentString):
        swinglib.runKeyword("selectContext", [self.widget.getName()])
        swinglib.runKeyword("sendKeyboardEvent", ["VK_ENTER"])

    
class MenuSelectEvent(SelectEvent):    
    def _generate(self, *args):
        path = util.getMenuPathString(self.widget)
        swinglib.runKeyword("selectFromMenuAndWait", [ path ])

    def shouldRecord(self, event, *args):
        return not isinstance(event.getSource(), swing.JMenu) and SelectEvent.shouldRecord(self, event, *args)
    
    def widgetVisible(self):
        return True

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

    def getIndex(self, text):
        for i in range(self.widget.getModel().getSize()):
            if util.getJListText(self.widget.widget, i) == text:
                return i
        raise UseCaseScriptError, "Could not find item labeled '" + text + "' in list."
    
    def _generate(self, argumentString):
        self._generateAbbot(argumentString)

    def _generateAbbot(self, argumentString):
        selected = argumentString.split(", ")
        indices = map(self.getIndex, selected)
        mask1 = InputEvent.BUTTON1_MASK
        mask2 = InputEvent.BUTTON1_MASK | InputEvent.CTRL_MASK
        self.widget.clearSelection()
        count = 0
        for index in indices:
            if count == 0:
                mask = mask1
            else:
                mask = mask2
            count += 1
            rect = self.widget.getCellBounds(index, index)
            System.setProperty("abbot.robot.mode", "awt")
            robot = Robot()
            robot.setEventMode(Robot.EM_AWT)
            util.runOnEventDispatchThread(robot.click, self.widget.widget, rect.width / 2, rect.y + rect.height / 2, mask, 1)

# It seems to be a bug in SwingLibrary when selecting a row larger than window's visible width. 
# We'll keep this method commented and investigate the causes.
#    def _generateSwingLib(self, argumentString):
#        selected = argumentString.split(", ")
#         Officially we can pass the names directly to SwingLibrary
#         Problem is that doesn't work if the names are themselves numbers
#        params = [ self.widget.getName() ] + map(self.getIndex, selected)
#        swinglib.runKeyword("selectFromList", params)
        
    def getStateText(self, *args):
        texts = [ util.getJListText(self.widget.widget, i) for i in self.widget.getSelectedIndices() ]
        return ", ".join(texts)
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)

class TableSelectEvent(ListSelectEvent):
    recordOnSelect = True
    
    def __init__(self, *args):
        ListSelectEvent.__init__(self, *args)
        self.indexer = TableIndexer.getIndexer(self.widget.widget)
        
    def _generate(self, argumentString):
        # To be used when using multi-selection: selectedCells = argumentString.split(", ")
        params = [ self.widget.getName() ]
        row, column = self.indexer.getViewCellIndices(argumentString)
        # It seems to be a bug in SwingLibrary. Using Column name as argument doesn't work as expected. It throws exceptions
        # for some cell values. 
        swinglib.runKeyword("selectTableCell", params + [row, column])
        
    def getStateText(self, *args):
        text = []
        for row in self.widget.getSelectedRows():
            for col in self.widget.getSelectedColumns():
                text.append(self.indexer.getCellDescription(row, col))
        return ", ".join(text)
    
    def shouldRecord(self, event, *args):
        value =  ListSelectEvent.shouldRecord(self, event, *args) and TableSelectEvent.recordOnSelect
        TableSelectEvent.recordOnSelect = True
        return value

class TableHeaderEvent(SignalEvent):
    def isStateChange(self):
        return True
    
    def _generate(self, argumentString):
        swinglib.runKeyword("clickTableHeader", [self.widget.getTable().getName(), argumentString])

    def outputForScript(self, event, *args):
        colIndex = self.widget.columnAtPoint(event.getPoint())
        name = self.widget.getTable().getColumnName(colIndex)        
        return SignalEvent.outputForScript(self, event, *args) + " " + name
    
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Click"

    def shouldRecord(self, event, *args):
        return event.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and \
            event.getClickCount() == 1 and SignalEvent.shouldRecord(self, event, *args)

    
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


class CellEditEvent(StateChangeEvent):
    def _generate(self, argumentString):
        cellDescription, newValue = argumentString.split("=")
        row, column = TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(cellDescription)
        cellEditor = self.widget.getCellEditor(row, column)
        if self.isTextComponent(cellEditor):
            self.editTextComponent(newValue, row, column)
        elif self.isCheckBox(cellEditor):
            self.editCheckBoxComponent(newValue, row, column)
        else:
            #temporary workaround
            self.editTextComponent(newValue, row, column)

    def editTextComponent(self, newValue, row, column):
        swinglib.runKeyword("typeIntoTableCell", [self.widget.getName(), row, column, newValue ])
        swinglib.runKeyword("selectTableCell", [self.widget.getName(), row, column])
        while not self.ready(newValue, row, column):
            time.sleep(0.1)

    def editCheckBoxComponent(self, newValue, row, column):
        if not newValue == str(self.widget.getValueAt(row, column)):
            swinglib.runKeyword("clickOnTableCell", [self.widget.getName(), row, column, 1, "BUTTON1_MASK" ])

    def isTextComponent(self, cellEditor):
        return self.isCellEditorComponent(cellEditor, swing.text.JTextComponent)

    def isCheckBox(self, cellEditor):
        return self.isCellEditorComponent(cellEditor, swing.JCheckBox)

    def isCellEditorComponent(self, cellEditor, component):
        if isinstance(cellEditor, swing.DefaultCellEditor):
            return isinstance(cellEditor.getComponent(), component)
    
    def ready(self, value, row, column):
        return value == str(self.widget.getValueAt(row, column))
    
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
        currOutput = self.outputForScript(*args)
        return ((currOutput.startswith(stateChangeOutput) and isinstance(stateChangeEvent, CellEditEvent)) or isinstance(stateChangeEvent, CellDoubleClickEvent) or isinstance(stateChangeEvent, TableSelectEvent)) and self.widget.widget is stateChangeEvent.widget.widget

    def getNewValue(self, row, col):
        cellEditor = self.widget.getCellEditor()
        if cellEditor is not None:
            return cellEditor.getCellEditorValue()
        else:
            return self.widget.getValueAt(row, col)
    
    def getStateText(self, row, col, *args):
        value = self.getNewValue(row, col)
        return str(TableIndexer.getIndexer(self.widget.widget).getCellDescription(row, col)) + "=" + str(value)
            
    def shouldRecord(self, row, col, *args):
        result = self.getNewValue(row, col) is not None
        if result:
            TableSelectEvent.recordOnSelect = False 
        return result
    
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Edited" 

    def delayLevel(self):
        return False
        
class TableIndexer():
    allIndexers = {}
    def __init__(self, table):
        self.tableModel = table.getModel()
        self.table = table
        self.logger = logging.getLogger("TableModelIndexer")
        self.primaryKeyColumn, self.rowNames = self.findRowNames()
        self.observeUpdates()
        self.logger.debug("Creating table indexer with rows " + repr(self.rowNames))

    def observeUpdates(self):
        class TableListener(swing.event.TableModelListener):
            def tableChanged(listenerSelf, event):
                if self.primaryKeyColumn is None:
                    self.primaryKeyColumn, self.rowNames = self.findRowNames()
                    self.logger.debug("Rebuilding indexer, row names now " + repr(self.rowNames))
                else:
                    currRowNames = self.getColumn(self.primaryKeyColumn)
                    if set(currRowNames) != set([ "<unnamed>" ]):
                        self.rowNames = currRowNames
                        self.logger.debug("Model changed, row names now " + repr(self.rowNames))
                
        util.runOnEventDispatchThread(self.table.getModel().addTableModelListener, TableListener())

    @classmethod
    def getIndexer(cls, table):
        # Don't just do setdefault, shouldn't create the TableIndexer if it already exists
        if table in cls.allIndexers:
            return cls.allIndexers.get(table)
        else:
            return cls.allIndexers.setdefault(table, cls(table))

    def getColumn(self, col):
        return [ str(self.tableModel.getValueAt(row, col) or "<unnamed>") for row in range(self.tableModel.getRowCount()) ]

    def findRowNames(self):
        for colIndex in range(self.tableModel.getColumnCount()):
            column = self.getColumn(colIndex)
            if len(column) > 1 and len(set(column)) == len(column):
                return colIndex, column
        # No unique columns to use as row names. Use the first row and add numbers
        return None, self.addIndexes(self.getColumn(0))

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
        rowName = self.rowNames[self.table.convertRowIndexToModel(row)]
        if self.tableModel.getColumnCount() == 1:
            return rowName
        else:
            return self.table.getColumnName(col) + " for " + rowName


class Filter:
    eventsFromUser = []
    ignoredWidgets = [swing.text.JTextComponent]
    logger = None
    eventListener = None
    def __init__(self, uiMap):
        Filter.logger = logging.getLogger("usecase record")
        self.uiMap = uiMap

    @classmethod
    def delayLevel(cls):
        # If there are events for other windows, implies we should delay as we're in a dialog
        for event in cls.eventsFromUser:
            cls.logger.debug("Event causing delay " + repr(event)) 
        return len(cls.eventsFromUser)

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

    def shouldAddFilter(self, event):
        return isinstance(event.getSource(), Component) and \
                   self.addToFilter(event) and \
                   not self.hasEventOnWindow(event.getSource()) and \
                   not any((isinstance(event.getSource(), widgetClass) for widgetClass in self.ignoredWidgets)) and \
                   self.uiMap.scriptEngine.checkType(event.getSource())
    
    def handleEvent(self, event):
        if self.shouldAddFilter(event):
            self.logger.debug("Filter for event " + event.toString())
            self.eventsFromUser.append(event)
    
    def addToFilter(self, event):
        for cls in [ MouseEvent, KeyEvent, WindowEvent, ComponentEvent, ActionEvent ]:
            if isinstance(event, cls):
                return getattr(self, "handle" + cls.__name__)(event)
        return True
            
    def handleMouseEvent(self, event):
        return event.getID() == MouseEvent.MOUSE_PRESSED and not isinstance(event.getSource(), swing.JMenu) and \
               not util.hasComplexAncestors(event.getSource())
            
    def handleKeyEvent(self, event):
        # TODO: to be implemented
        return False
        
    def handleWindowEvent(self, event):
        return event.getID() == WindowEvent.WINDOW_CLOSING or self.handleComponentEvent(event)
    
    def handleComponentEvent(self, event):       
        return False #TODO: return event.getID() == ComponentEvent.COMPONENT_RESIZED

    def handleActionEvent(self, event):
        return False
