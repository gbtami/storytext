import storytext.guishared, logging, util, sys, os
from storytext import applicationEvent, applicationEventDelay
from storytext.definitions import UseCaseScriptError

from java.awt import AWTEvent, Toolkit
from java.awt.event import AWTEventListener, KeyListener, MouseAdapter, MouseEvent, KeyEvent, \
     WindowEvent, ActionListener, ItemListener, ItemEvent
from java.lang import System, RuntimeException
from java.io import PrintStream, OutputStream

from javax.swing import DefaultCellEditor, JButton, JCheckBox, JComboBox, JComponent, JDialog, \
    JFrame, JInternalFrame, JMenu, JMenuItem, JSpinner, JTextField, JToggleButton, SwingUtilities
from javax.swing.event import ChangeListener, DocumentListener, TableModelEvent, TableModelListener
from javax.swing.text import JTextComponent

try:
    from org.robotframework.abbot.tester import Robot
except ImportError:
    sys.stderr.write("ERROR: Could not find RobotFramework SwingLibrary jar file. \n" +
                     "Please download it and add it to your CLASSPATH as described at :\n" +
                     "http://www.texttest.org/index.php?page=ui_testing&n=storytext_and_swing\n")
    sys.exit(1)

# Importing writes uninteresting stuff to stdout
out_orig = System.out
class NullOutputStream(OutputStream):
    def write(self, *args):
        pass

System.setOut(PrintStream(NullOutputStream()))
import SwingLibrary
from org.robotframework.org.netbeans.jemmy.operators import ComponentOperator, JMenuItemOperator, JTableOperator
swinglib = SwingLibrary()
System.setOut(out_orig)

# Uncomment for Abbot logs
#import abbot
#abbot.Log.init([ "--debug", "all" ])

def runKeyword(keywordName, *args):
    # Uncomment this code in order to debug SwingLibrary issues
    #f = open("swinglib.storytext", "a")
    #f.write("runKeyword" + repr((keywordName, list(args))) + "\n")
    return swinglib.runKeyword(keywordName, list(args))

def selectWindow(widget):
    w = checkWidget(widget)
    window = SwingUtilities.getWindowAncestor(w)
    if isinstance(window, JFrame):
        runKeyword("selectWindow", window.getTitle())
    elif isinstance(window, JDialog):
        runKeyword("selectDialog", window.getTitle())

def checkWidget(widget):
    if isinstance(widget, JMenuItem):
        return widget.getParent().getInvoker()
    return widget

class WidgetAdapter(storytext.guishared.WidgetAdapter):
    def getChildWidgets(self):
        if isinstance(self.widget, JMenu):
            return self.widget.getPopupMenu().getSubElements()
        elif hasattr(self.widget, "getComponents"): # All Swing widgets have this, but AWT one don't
            return self.widget.getComponents()
        else:
            return []
        
    def getName(self):
        return self.widget.getName() or ""
    
    def getWidgetTitle(self):
        if hasattr(self.widget, "getTitle"):
            return self.widget.getTitle() or ""
        else:
            return ""
            
    def isAutoGenerated(self, name):
        # Don't use autogenerated filechooser names, as they vary depending on theme, which is a pain, and they mostly have sensible labels anyway
        return name == "frame0" or name.startswith("OptionPane") or len(name) == 0 or "FileChooser." in name
    
    def getLabel(self):
        if isinstance(self.widget, (JTextComponent, JComboBox, JSpinner)):
            return util.getTextLabel(self.widget)

        if hasattr(self.widget, "getLabel") and not self.getContextName():
            return self.widget.getLabel() or ""
        else:
            return ""
                
    def getTooltip(self):
        if hasattr(self.widget, "getToolTipText"):
            return self.widget.getToolTipText() or ""
        else:
            return ""
        
    def getContextName(self):
        if SwingUtilities.getAncestorOfClass(JInternalFrame, self.widget):
            return "Internal Frame"
        elif SwingUtilities.getAncestorOfClass(JInternalFrame.JDesktopIcon, self.widget): #@UndefinedVariable
            return "Internal Frame Icon"
        
    def getDialogTitle(self):
        window = SwingUtilities.getWindowAncestor(self.widget)
        return window.getTitle() if window and hasattr(window, "getTitle") and window.getOwner() else ""

    def runKeyword(self, keywordName, *args):
        return runKeyword(keywordName, self.widget.getName(), *args)
                            

storytext.guishared.WidgetAdapter.adapterClass = WidgetAdapter

class SignalEvent(storytext.guishared.GuiEvent):
    def generate(self, *args):
        self.setNameIfNeeded()
        selectWindow(self.widget.widget)
        self._generate(*args)
            
    def connectRecord(self, method):
        class ClickListener(MouseAdapter):
            def mousePressed(listenerSelf, event): #@NoSelf
                storytext.guishared.catchAll(method, event, self)

        util.runOnEventDispatchThread(self.getRecordWidget().addMouseListener, ClickListener())

    def getRecordWidget(self):
        return self.widget.widget
        
    def shouldRecord(self, *args):
        return not util.hasComplexAncestors(self.getRecordWidget()) and PhysicalEventManager.matchPhysicalEvent(self, *args)
    
    def setNameIfNeeded(self):
        mapId = self.widget.getUIMapIdentifier()
        if not mapId.startswith("Name="):
            name = "StoryText map ID: " + mapId + " " + str(id(self))
            self.widget.setName(name)

    def widgetVisible(self):
        return self.widget.isShowing()

    def widgetSensitive(self):
        return self.widget.isEnabled()
    
    def describeWidget(self):
        return "of type " + self.widget.getType()

    
# Just to be able to test recording from keyboard
class KeyPressForTestingEvent(storytext.guishared.GuiEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "KeyPress"
    
    def parseArguments(self, text):
        return text
    
    def generate(self, argument):
        arg = argument.upper()
        if "+" in arg:
            parts = arg.split("+")
            runKeyword("sendKeyboardEvent", "VK_" + parts[1], parts[0] + "_MASK")
        else:
            runKeyword("sendKeyboardEvent", "VK_" + arg)

    def connectRecord(self, method):
        pass

class FrameCloseEvent(SignalEvent):
    def _generate(self, *args):
        if os.getenv("SWINGLIBRARY_WINDOW_CLOSE"):
            self.closeDialogOrWindow()
        else:
            self.simulateCloseWindow()

    #This just works on java 6. See https://github.com/robotframework/SwingLibrary/issues/41
    def closeDialogOrWindow(self):
        keywordName = "closeDialog" if isinstance(self.widget.widget, JDialog) else "closeWindow"
        runKeyword(keywordName, self.widget.getTitle())
    
    # Workaround to make it work on java 7
    def simulateCloseWindow(self):
        self.widget.widget.dispatchEvent(WindowEvent(self.widget.widget, WindowEvent.WINDOW_CLOSING))

    def connectRecord(self, method):               
        class EventListener(AWTEventListener):
            def eventDispatched(listenerSelf, event): #@NoSelf
                storytext.guishared.catchAll(self.handleEvent, event, method)
    
        eventListener = EventListener()
        eventMask = AWTEvent.WINDOW_EVENT_MASK
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, eventListener, eventMask)
        
    def handleEvent(self, event, method):
        if event.getSource() == self.widget.widget:
            if event.getID() == WindowEvent.WINDOW_CLOSING:
                method(event, self)
            elif event.getID() == WindowEvent.WINDOW_CLOSED:
                if isinstance(self.widget.widget, JFrame):
                    storytext.guishared.catchAll(PhysicalEventManager.stopListening)
                    
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Close"


class ClickEvent(SignalEvent):
    def _generate(self, *args):
        self.widget.runKeyword("clickOnComponent")
        
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
    
    def shouldRecord(self, event, *args):
        return event.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and \
               event.getClickCount() == 2 and \
               SignalEvent.shouldRecord(self, event, *args)
        
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, ClickEvent)

    def _generate(self, *args):
        self.widget.runKeyword("clickOnComponent", 2)

class PopupActivateEvent(ClickEvent):
    def _generate(self, *args):
        System.setOut(PrintStream(NullOutputStream()))
        operator = ComponentOperator(self.widget.widget)
        System.setOut(out_orig)
        operator.clickForPopup()
    
    def connectRecord(self, method):               
        if isinstance(self.widget.widget, JComponent) and self.widget.getComponentPopupMenu():
            class EventListener(AWTEventListener):
                def eventDispatched(listenerSelf, event): #@NoSelf
                    storytext.guishared.catchAll(self.handleEvent, event, method)
    
            eventListener = EventListener()
            eventMask = AWTEvent.MOUSE_EVENT_MASK
            util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, eventListener, eventMask)
        else:
            SignalEvent.connectRecord(self, method)
    
    def handleEvent(self, event, method):
        if event.getID() == MouseEvent.MOUSE_PRESSED and event.getSource() == self.widget.widget:
            method(event, self)
            
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "PopupActivate"
    
    def shouldRecord(self, event, *args):
        return event.isPopupTrigger() and SignalEvent.shouldRecord(self, event, *args)

class ButtonClickEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Click"

    def parseArguments(self, argument):
        if argument and argument != self.getButtonIdentifier():
            raise UseCaseScriptError, "could not find internal frame '" + argument + \
                  "', found '" + self.getButtonIdentifier() + "'"
        return argument
        
    def _generate(self, argument):
        # Just doing clickOnComponent as in ClickEvent ought to work, but doesn't, see
        # http://code.google.com/p/robotframework-swinglibrary/issues/detail?id=175
        self.widget.runKeyword("pushButton")
        
    def connectRecord(self, method):
        class RecordListener(ActionListener):
            def actionPerformed(lself, event): #@NoSelf
                storytext.guishared.catchAll(self.tryApplicationEvent, event, method)
                    
        util.runOnEventDispatchThread(self.widget.widget.addActionListener, RecordListener())

    def getButtonIdentifier(self):
        intFrame = SwingUtilities.getAncestorOfClass(JInternalFrame, self.widget.widget)
        if intFrame:
            return intFrame.getTitle()

        icon = SwingUtilities.getAncestorOfClass(JInternalFrame.JDesktopIcon, self.widget.widget) #@UndefinedVariable
        if icon:
            return self.widget.widget.getLabel()

    def outputForScript(self, *args):
        argument = self.getButtonIdentifier()
        text = SignalEvent.outputForScript(self, *args)
        if argument:
            return text + " " + argument
        else:
            return text

    def tryApplicationEvent(self, event, method):
        if isinstance(event.getSource(), JButton) and event.getActionCommand() is not None and \
               event.getActionCommand().startswith("ApplicationEvent"):
            appEventName = event.getActionCommand().replace("ApplicationEvent", "").lstrip()
            applicationEvent(appEventName, delayLevel=PhysicalEventManager.getAppEventDelayLevel())
        else:
            method(event, self)

class InternalFrameDoubleClickEvent(DoubleClickEvent):
    def outputForScript(self, *args):
        return self.name + " " + self.getTitle()

    def getTitle(self):
        return self.widget.getParent().getTitle()

    def parseArguments(self, argument):
        if argument == self.getTitle():
            return argument
        else:
            raise UseCaseScriptError, "could not find internal frame '" + argument + \
                  "', found '" + self.getTitle() + "'"
    
class StateChangeEvent(ClickEvent):
    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateText(*args) ])

    def isStateChange(self, *args):
        return True

class SpinnerEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Edited"

    def connectRecord(self, method):
        class RecordListener(ChangeListener):
            def stateChanged(lself, e): #@NoSelf
                storytext.guishared.catchAll(method, e, self)

        util.runOnEventDispatchThread(self.widget.addChangeListener, RecordListener())

    def shouldRecord(self, *args):
        return SignalEvent.shouldRecord(self, *args)

    def getStateText(self, *args):
        return str(self.widget.getValue())
    
    def parseArguments(self, argumentString):
        return argumentString

    def _generate(self, argumentString):
        kwd = "setSpinnerNumberValue" if isinstance(self.widget.getValue(), int) else "setSpinnerStringValue"
        self.widget.runKeyword(kwd, argumentString)


class TextEditEvent(StateChangeEvent):
    def connectRecord(self, method):
        class TextDocumentListener(DocumentListener):
            def insertUpdate(lself, event): #@NoSelf
                storytext.guishared.catchAll(method, event, self)
                
            changedUpdate = insertUpdate
            removeUpdate = insertUpdate

        util.runOnEventDispatchThread(self.widget.getDocument().addDocumentListener, TextDocumentListener())

    def parseArguments(self, text):
        return text

    def _generate(self, argumentString):
        self.widget.runKeyword("clearTextField")
        self.widget.runKeyword("typeIntoTextField", argumentString)

    def getStateText(self, event, *args):        
        return storytext.guishared.removeMarkup(self.widget.getText())

    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Modify"
    
    def shouldRecord(self, *args):
        # Can get document changes on things that aren't visible
        # Can't be caused by clicking the mouse, assume such must be programmatic changes
        return self.widget.isShowing() and self.widget.isEditable() and SignalEvent.shouldRecord(self, *args)
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        return isinstance(stateChangeEvent, TextEditEvent) and stateChangeEvent.widget.widget is self.widget.widget

class ActivateEvent(SignalEvent):
    def connectRecord(self, method):
        class ActivateEventListener(ActionListener):
            def actionPerformed(lself, event): #@NoSelf
                storytext.guishared.catchAll(method, event, self)
                    
        util.runOnEventDispatchThread(self.widget.widget.addActionListener, ActivateEventListener())
        
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Activate"

    
class TextActivateEvent(ActivateEvent):
    def generate(self, *args):
        self.setNameIfNeeded()
        self.widget.runKeyword("focusToComponent")
        runKeyword("sendKeyboardEvent", "VK_ENTER")

   
class MenuSelectEvent(SignalEvent):
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "Click"

    def _generate(self, *args):
        path = util.getMenuPathString(self.widget)
        if util.belongsMenubar(self.widget):
            runKeyword("selectFromMenuAndWait", path)
        else:    
            self.selectFromPopupMenu()

    def connectRecord(self, method):
        class RecordListener(ActionListener):
            def actionPerformed(lself, event): #@NoSelf
                storytext.guishared.catchAll(method, event, self)

        util.runOnEventDispatchThread(self.widget.widget.addActionListener, RecordListener())
    
    def selectFromPopupMenu(self):
        System.setOut(PrintStream(NullOutputStream()))
        operator = JMenuItemOperator(self.widget.widget)
        operator.push()
        System.setOut(out_orig)
                
    def shouldRecord(self, event, *args):
        return not isinstance(event.getSource(), JMenu) and SignalEvent.shouldRecord(self, event, *args)
    
    def widgetVisible(self):
        return True
    
    def allowsIdenticalCopies(self):
        return True


class TabSelectEvent(ClickEvent):
    def isStateChange(self):
        return True
    
    def parseArguments(self, text):
        return text
                    
    def _generate(self, argumentString):
        try:
            runKeyword("selectTab", argumentString)
        except RuntimeException:
            raise UseCaseScriptError, "Could not find tab named '" + argumentString + "' to select."
    
    def outputForScript(self, event, *args):
        text = self.widget.getTitleAt(self.widget.getSelectedIndex())
        return ' '.join([self.name, text])
     
    def implies(self, *args):
        # State change because it can be implied by TabCloseEvents
        # But don't amalgamate them together, allow several tabs to be selected in sequence
        return False

class TabPopupActivateEvent(PopupActivateEvent):
    def parseArguments(self, title):
        return self.widget.indexOfTab(title)
        
    def _generate(self, index):
        System.setOut(PrintStream(NullOutputStream()))
        rect = self.widget.getBoundsAt(index)
        operator = ComponentOperator(self.widget.widget)
        System.setOut(out_orig)
        operator.clickForPopup(rect.x + rect.width/2, rect.y + rect.height/2)
     
    def outputForScript(self, event, *args):
        index = self.widget.getSelectedIndex()        
        return ' '.join([self.name, self.widget.getTitleAt(index)])

class ListSelectEvent(StateChangeEvent):
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Select" 

    def getJListText(self, index):
        return util.ComponentTextFinder(self.widget.widget, describe=False).getJListText(index)

    def getIndex(self, text):
        for i in range(self.widget.getModel().getSize()):
            if self.getJListText(i) == text:
                return i
        raise UseCaseScriptError, "Could not find item labeled '" + text + "' in list."
    
    def parseArguments(self, argumentString):
        return map(self.getIndex, argumentString.split(", "))
    
    def _generate(self, indices):
        #Officially we can pass the names directly to SwingLibrary
        #Problem is that doesn't work if the names are themselves numbers
        self.widget.runKeyword("selectFromList", *indices)
        
    def getStateText(self, *args):
        texts = [ self.getJListText(i) for i in self.widget.getSelectedIndices() ]
        return ", ".join(texts)
    
    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        currOutput = self.outputForScript(*args)
        return currOutput.startswith(stateChangeOutput)
    
    def getRenderer(self):
        return self.getRecordWidget().getCellRenderer()

class ComboBoxEvent(StateChangeEvent):
    def connectRecord(self, method):
        class ItemSelectListener(ItemListener):
            def itemStateChanged(listenerSelf, event): #@NoSelf
                storytext.guishared.catchAll(self.tryRecordSelection, event, method)
        
        class TextDocumentListener(DocumentListener):
            def insertUpdate(lself, event): #@NoSelf
                storytext.guishared.catchAll(method, None, event, self)
                
            changedUpdate = insertUpdate
            removeUpdate = insertUpdate

        if self.widget.isEditable():
            util.runOnEventDispatchThread(self.widget.getEditor().getEditorComponent().getDocument().addDocumentListener, TextDocumentListener())        
                    
        util.runOnEventDispatchThread(self.widget.widget.addItemListener, ItemSelectListener())

    def tryRecordSelection(self, event, method):
        if event.getStateChange() == ItemEvent.SELECTED:
            method(event.getItem(), self)

    def shouldRecord(self, item, event, *args):
        if item:
            return SignalEvent.shouldRecord(self, item, *args)
        else:
            value = self.widget.getEditor().getItem()
            
            return value and not self.isInComboBox(value) and SignalEvent.shouldRecord(self, None, *args)

    def parseArguments(self, text):
        if not self.widget.isEditable() and not self.isInComboBox(text):
            raise UseCaseScriptError, "Could not find item named '" + text + "' to select."
        return text

    def _generate(self, argumentString):
        self.argumentString = argumentString
        if self.widget.isEditable() and not self.isInComboBox(argumentString):
            self.widget.runKeyword("typeIntoComboBox", argumentString)
        else:
            self.widget.runKeyword("selectFromComboBox", argumentString)
                
    def getJComboBoxText(self, index):
        return util.ComponentTextFinder(self.widget.widget, describe=False).getJComboBoxText(index)
            
    def getStateText(self, *args):
        if self.widget.isEditable():
            texts = [ str(self.widget.getEditor().getItem()) ]
        else:
            texts = [ self.getJComboBoxText(self.widget.getSelectedIndex()) ]
        return ", ".join(texts)
    
    def getIndex(self, text):
        for i in range(self.widget.getModel().getSize()):
            if self.getJComboBoxText(i) == text:
                return i
        raise UseCaseScriptError, "Could not find item labeled '" + text + "' in combo box."
    
    def implies(self, stateChangeOutput, stateChangeEvent, item, *args):
        currOutput = self.outputForScript(item, *args)
        if currOutput == stateChangeOutput:
            return True
        prevString = stateChangeOutput.rsplit(None, 1)[-1]
        return item is None and isinstance(stateChangeEvent, ComboBoxEvent) and not self.isInComboBox(prevString)
            
    def isInComboBox(self, text):
        for i in range(self.widget.getModel().getSize()):
            if self.getJComboBoxText(i) == text:
                return True
        return False

class TableSelectEvent(ListSelectEvent):
    def __init__(self, *args):
        ListSelectEvent.__init__(self, *args)
        self.indexer = TableIndexer.getIndexer(self.widget.widget)
        
    def parseArguments(self, argumentString):
        # To be used when using multi-selection: selectedCells = argumentString.split(", ")
        return self.indexer.getViewCellIndices(argumentString)
    
    def _generate(self, cell):
        # It seems to be a bug in SwingLibrary. Using Column name as argument doesn't work as expected. It throws exceptions
        # for some cell values. 
        self.widget.runKeyword("selectTableCell", *cell)
        
    def getStateText(self, *args):
        text = []
        for row in self.widget.getSelectedRows():
            for col in self.widget.getSelectedColumns():
                text.append(self.indexer.getCellDescription(row, col))
        return ", ".join(text)
    

class CellPopupMenuActivateEvent(PopupActivateEvent):
    def parseArguments(self, argumentString):
        return TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(argumentString)
    
    def _generate(self, argument):
        row, column = argument
        System.setOut(PrintStream(NullOutputStream()))
        operator = JTableOperator(self.widget.widget)
        System.setOut(out_orig)
        operator.callPopupOnCell(row, column)

    def outputForScript(self, event, *args):
        row = self.widget.rowAtPoint(event.getPoint())
        column = self.widget.columnAtPoint(event.getPoint())
        text = TableIndexer.getIndexer(self.widget.widget).getCellDescription(row, column)
        return ' '.join([self.name, text])

class TableHeaderEvent(SignalEvent):
    def isStateChange(self):
        return True
    
    def parseArguments(self, text):
        textFinder = util.ComponentTextFinder(self.widget.widget, describe=False)
        for i in range(self.widget.getColumnCount()):
            if textFinder.getJTableHeaderText(i) == text:
                return i
        raise UseCaseScriptError, "Could not find column named '" + text + "'"
            
    def _generate(self, column):
        self.widget.runKeyword("clickTableHeader", column)

    def outputForScript(self, event, *args):
        colIndex = self.widget.getTableHeader().columnAtPoint(event.getPoint())
        colText = TableIndexer.getIndexer(self.widget.widget).getColumnTextToUse(colIndex)
        return SignalEvent.outputForScript(self, event, *args) + " " + colText

    def getRecordWidget(self):
        return self.widget.getTableHeader()
    
    @classmethod
    def getAssociatedSignal(cls, *args):
        return "ClickHeader"

    def shouldRecord(self, event, *args):
        return event.getModifiers() & MouseEvent.BUTTON1_MASK != 0 and \
            event.getClickCount() == 1 and SignalEvent.shouldRecord(self, event, *args)

    def implies(self, *args):
        return False
    
class CellDoubleClickEvent(DoubleClickEvent):
    def parseArguments(self, argumentString):
        return TableIndexer.getIndexer(self.widget.widget).getViewCellIndices(argumentString)
    
    def _generate(self, cell):
        row, column = cell             
        self.widget.runKeyword("clickOnTableCell", row, column, 2, "BUTTON1_MASK")

    def shouldRecord(self, *args):
        return DoubleClickEvent.shouldRecord(self, *args) and \
               not self.widget.isCellEditable(self.widget.getSelectedRow(), self.widget.getSelectedColumn())
        
    def outputForScript(self, event, *args):
        predefined = DoubleClickEvent.outputForScript(self,event, *args)
        row = self.widget.getSelectedRow()
        col = self.widget.getSelectedColumn()
        desc = TableIndexer.getIndexer(self.widget.widget).getCellDescription(row, col)
        return predefined + " " + desc


class CellEditEvent(SignalEvent):
    def __init__(self, *args):
        SignalEvent.__init__(self, *args)
        self.indexer = TableIndexer.getIndexer(self.widget.widget)
        self.logger = logging.getLogger("storytext replay log")
        
    def parseArguments(self, argumentString):
        if "=" in argumentString:
            cellDescription, newValue = argumentString.split("=")
            row, column = self.indexer.getViewCellIndices(cellDescription)
            return row, column, newValue
        else:
            raise UseCaseScriptError, "Missing '=' sign in argument '" + argumentString + "'"
        
    def _generate(self, args):
        row, column, newValue = args
        cellEditor = self.widget.getCellEditor(row, column)
        if self.isTextComponent(cellEditor):
            self.editTextComponent(newValue, row, column)
        elif self.isCheckBox(cellEditor):
            self.editCheckBoxComponent(newValue, row, column)
        elif self.isComboBox(cellEditor):
            self.editComboBoxComponent(newValue, row, column, cellEditor.getComponent())
        else:
            #temporary workaround
            self.editTextComponent(newValue, row, column)

    def editTextComponent(self, newValue, row, column):
        self.widget.runKeyword("typeIntoTableCell", row, column, newValue)
        
    def editCheckBoxComponent(self, newValue, row, column):
        if not newValue == str(self.widget.getValueAt(row, column)):
            self.widget.runKeyword("clickOnTableCell", row, column, 1, "BUTTON1_MASK")

    def editComboBoxComponent(self, newValue, row, column, combobox):
        if combobox.isEditable():
            self.editTextComponent(newValue, row, column)
        else:
            self.widget.runKeyword("selectTableCell", row, column)
            combobox.setSelectedItem(newValue)

    def isTextComponent(self, cellEditor):
        return self.isCellEditorComponent(cellEditor, JTextComponent)

    def isCheckBox(self, cellEditor):
        return self.isCellEditorComponent(cellEditor, JCheckBox)

    def isComboBox(self, cellEditor):
        return self.isCellEditorComponent(cellEditor, JComboBox)
    
    def isCellEditorComponent(self, cellEditor, component):
        if isinstance(cellEditor, DefaultCellEditor):
            return isinstance(cellEditor.getComponent(), component)
    
    def connectRecord(self, method):
        class TableListener(TableModelListener):
            def tableChanged(listenerSelf, event): #@NoSelf
                storytext.guishared.catchAll(self.tryRecordUpdate, event, method)
                    
        util.runOnEventDispatchThread(self.widget.widget.getModel().addTableModelListener, TableListener())

    def tryRecordUpdate(self, event, method):
        if event.getType() == TableModelEvent.UPDATE:
            row = self.widget.getEditingRow()
            column = self.widget.getEditingColumn()
            if row >= 0 and column >= 0:
                method(row, column, self)

    def implies(self, stateChangeOutput, stateChangeEvent, *args):
        if isinstance(stateChangeEvent, CellEditEvent):
            currOutput = self.outputForScript(*args).rsplit("=", 1)[0]
            prevOutput = stateChangeOutput.rsplit("=", 1)[0]
            return currOutput == prevOutput
        else:
            return isinstance(stateChangeEvent, TableSelectEvent) and \
                   self.widget.widget is stateChangeEvent.widget.widget

    def getNewValue(self, row, col):
        component = self.widget.getEditorComponent()
        if component is not None:
            return self.getValueFromComponent(component)
        else:
            return self.widget.getValueAt(row, col)
    
    def getValueFromComponent(self, component):
        if isinstance(component, JComboBox):
            return component.getSelectedItem()
        elif isinstance(component, JTextField):
            return component.getText()
        elif isinstance(component, JToggleButton):
            return component.isSelected()
        else:
            cellEditor = self.widget.getCellEditor()
            if cellEditor is not None:
                value = cellEditor.getCellEditorValue()
                return value
        
    def getStateText(self, row, col, *args):
        value = self.getNewValue(row, col)
        return str(self.indexer.getCellDescription(row, col, checkSelectionModel=False)) + "=" + str(value)
            
    def shouldRecord(self, row, col, *args):
        return self.getNewValue(row, col) is not None and SignalEvent.shouldRecord(self, row, col, *args)
    
    @classmethod
    def getAssociatedSignal(cls, widget):
        return "Edited" 

    def outputForScript(self, *args):
        return ' '.join([self.name, self.getStateText(*args) ])

    def isStateChange(self, *args):
        return True

        
class TableIndexer(storytext.guishared.TableIndexer):
    def __init__(self, table):
        self.tableModel = table.getModel()
        self.textFinder = util.ComponentTextFinder(table, describe=False)
        self.getColumnText = self.textFinder.getJTableHeaderText
        storytext.guishared.TableIndexer.__init__(self, table)
        self.observeUpdates()

    def observeUpdates(self):
        class TableListener(TableModelListener):
            def tableChanged(listenerSelf, event): #@NoSelf
                storytext.guishared.catchAll(self.updateTableInfo)
                
        util.runOnEventDispatchThread(self.widget.getModel().addTableModelListener, TableListener())

    def updateTableInfo(self):
        if self.primaryKeyColumn is None:
            self.primaryKeyColumn, self.rowNames = self.findRowNames()
            self.logger.debug("Rebuilding indexer, primary key " + str(self.primaryKeyColumn) +
                              ", row names now " + repr(self.rowNames))
        else:
            currRowNames = self.getColumn(self.primaryKeyColumn)
            if set(currRowNames) != set([ "<unnamed>" ]):
                self.rowNames = currRowNames
                self.logger.debug("Model changed, row names now " + repr(self.rowNames))
                
    def getRowCount(self):
        return self.widget.getRowCount()

    def getCellValue(self, row, col):
        return self.textFinder.getJTableText(row, col)
    
    def getCellDescription(self, row, *args, **kw):
        rowModelIndex = self.widget.convertRowIndexToModel(row)
        return storytext.guishared.TableIndexer.getCellDescription(self, rowModelIndex, *args, **kw)
    
    def getViewCellIndices(self, description):
        rowModelIndex, col = storytext.guishared.TableIndexer.getViewCellIndices(self, description)
        return self.widget.convertRowIndexToView(rowModelIndex), col
    
    def useColumnTextInDescription(self, checkSelectionModel=True):
        return self.widget.getColumnCount() > 1 and (not checkSelectionModel or self.widget.getCellSelectionEnabled())


class PhysicalEventManager:
    eventContexts = []
    ignoredWidgets = JTextComponent, JMenu, JFrame
    relevantKeystrokes = []
    logger = None
    eventListener = None
    def __init__(self):
        PhysicalEventManager.logger = logging.getLogger("storytext record")
        self.allEvents = []

    @classmethod
    def matchPhysicalEvent(cls, event, *args):
        if len(cls.eventContexts) == 0:
            cls.logger.debug("No physical event currently active")
            return True
        
        currentContext = cls.eventContexts[-1]
        if currentContext.hasGenerated(event, *args):
            cls.logger.debug("Assuming generated programmatically by " + repr(currentContext.recordedOutput) +
                             "\nevent was " + repr(currentContext.physicalEvent))
            return False
        else:
            currentContext.registerRecordedEvent(event, *args)
            cls.logger.debug("Matched with physical event " + repr(currentContext.physicalEvent))
            return True
            
    def startListening(self):        
        class PhysicalEventListener(AWTEventListener):
            def eventDispatched(listenerSelf, event): #@NoSelf
                storytext.guishared.catchAll(self.handleEvent, event)
        
        self.eventListener = PhysicalEventListener()
        eventMask = AWTEvent.MOUSE_EVENT_MASK | AWTEvent.KEY_EVENT_MASK
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().addAWTEventListener, self.eventListener, eventMask)

    @classmethod
    def stopListening(cls):
        util.runOnEventDispatchThread(Toolkit.getDefaultToolkit().removeAWTEventListener, cls.eventListener)
    
    def handleEvent(self, event):
        if event.getID() == MouseEvent.MOUSE_PRESSED:
            if hasattr(event,"getApplicationEventMessage"):
                self.addApplicationEvent(event)
            else:
                context = PhysicalEventContext(event)
                self.addMouseListener(context)
                if event.getClickCount() == 2:
                    self.searchForAppEventToDelay()
        elif event.getID() == KeyEvent.KEY_PRESSED:
            context = PhysicalEventContext(event)
            self.registerStarted(context, "Key press")
        elif event.getID() == KeyEvent.KEY_RELEASED:
            # Can't assume KEY_RELEASED appears on the same widget as KEY_PRESSED
            context = self.findKeyEventContext(event)
            self.addKeyListener(context, event)

    def findKeyEventContext(self, event):
        for context in self.eventContexts:
            if context.matchesKeyEvent(event):
                return context
            
    def addMouseListener(self, context):
        text = "Mouse click"
        class MouseReleaseListener(MouseAdapter):
            def mouseReleased(lself, event): #@NoSelf
                for currContext in filter(lambda c: c.matchesMouseEvent(event), self.eventContexts):
                    currContext.getWidget().removeMouseListener(lself)
                    self.registerCompleted(currContext, text, event)

        self.registerStarted(context, text)
        context.getWidget().addMouseListener(MouseReleaseListener())

    def addKeyListener(self, context, event):
        class KeyReleaseListener(KeyListener):
            def keyReleased(lself, levent): #@NoSelf
                event.getSource().removeKeyListener(lself)
                self.registerCompleted(context, "Key press", levent)

        self.logger.debug("key press check " + repr(event))
        event.getSource().addKeyListener(KeyReleaseListener())

    def registerStarted(self, context, text):
        self.logger.debug(text + " started " + repr(context.physicalEvent))
        self.eventContexts.append(context)

    def registerCompleted(self, context, text, event):
        self.logger.debug(text + " completed " + repr(event))
        if context in self.eventContexts:
            self.eventContexts.remove(context)
            self.allEvents.append(context)

    @classmethod
    def getAppEventDelayLevel(cls):
        ret = len(filter(lambda e: e.recordedEvent is None, cls.eventContexts))
        if ret:
            cls.logger.debug("Got delay from " + repr(cls.eventContexts))
        return ret
    
    def addApplicationEvent(self, event):
        message = event.getApplicationEventMessage()
        self.allEvents.append(message)
        applicationEvent(message, delayLevel=self.getAppEventDelayLevel())

    def searchForAppEventToDelay(self):
        if len(self.allEvents) >= 2 and isinstance(self.allEvents[-1], (str, unicode)) and \
               isinstance(self.allEvents[-2], PhysicalEventContext):
            prevEvent = self.allEvents[-2].physicalEvent
            if isinstance(prevEvent, MouseEvent) and prevEvent.getClickCount() == 1:
                applicationEventDelay(self.allEvents[-1])
            

class PhysicalEventContext:
    def __init__(self, event):
        self.physicalEvent = event
        self.recordedEvent = None
        self.recordedOutput = None

    def __repr__(self):
        return repr((self.recordedEvent, self.physicalEvent))

    def getWidget(self):
        return self.physicalEvent.getSource()

    def matchesKeyEvent(self, event):
        return isinstance(self.physicalEvent, KeyEvent) and \
               event.getKeyCode() == self.physicalEvent.getKeyCode()

    def matchesMouseEvent(self, event):
        # Handle drag and drop which will set click count to 0
        return isinstance(self.physicalEvent, MouseEvent) and \
               event.getClickCount() in [0, self.physicalEvent.getClickCount()] and \
               event.getModifiers() == self.physicalEvent.getModifiers()

    def registerRecordedEvent(self, event, *args):
        self.recordedEvent = event
        self.recordedOutput = event.outputForScript(*args)
        
    def hasGenerated(self, event, physicalEvent, *args):
        return self.recordedEvent and not event.implies(self.recordedOutput, self.recordedEvent, physicalEvent, *args)
