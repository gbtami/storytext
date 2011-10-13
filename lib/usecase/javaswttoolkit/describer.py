
import usecase.guishared, util, types, os, logging
from usecase.definitions import UseCaseScriptError
from usecase.gridformatter import GridFormatter
from org.eclipse import swt
from java.util import Date        
        
        
class Describer(usecase.guishared.Describer):
    styleNames = [ (swt.widgets.CoolItem, []),
                   (swt.widgets.Item    , [ "SEPARATOR", "DROP_DOWN", "CHECK", "CASCADE", "RADIO" ]),
                   (swt.widgets.Button  , [ "CHECK", "RADIO", "TOGGLE", "ARROW", "UP", "DOWN" ]),
                   (swt.widgets.DateTime, [ "DATE", "TIME", "CALENDAR", "SHORT" ]),
                   (swt.widgets.Combo   , [ "READ_ONLY", "SIMPLE" ]), 
                   (swt.widgets.Text    , [ "PASSWORD", "SEARCH", "READ_ONLY" ]) ]
    ignoreWidgets = [ types.NoneType ]
    # DateTime children are an implementation detail
    # Coolbars and Expandbars describe their children directly : they have two parallel children structures    
    ignoreChildren = (swt.widgets.CoolBar, swt.widgets.ExpandBar, swt.widgets.DateTime)
    statelessWidgets = [ swt.widgets.Sash ]
    stateWidgets = [ swt.widgets.Shell, swt.widgets.Button, swt.widgets.Menu, swt.widgets.Link,
                     swt.widgets.CoolBar, swt.widgets.ToolBar, swt.widgets.Label, swt.custom.CLabel,
                     swt.widgets.Combo, swt.widgets.ExpandBar, swt.widgets.Text, swt.widgets.List,
                     swt.widgets.Tree, swt.widgets.DateTime, swt.widgets.TabFolder, swt.widgets.Table, 
                     swt.custom.CTabFolder, swt.widgets.Canvas, swt.browser.Browser, swt.widgets.Composite ]
    childrenMethodName = "getChildren"
    visibleMethodName = "getVisible"
    def __init__(self):
        self.canvasCounter = usecase.guishared.WidgetCounter()
        self.contextMenuCounter = usecase.guishared.WidgetCounter(self.contextMenusEqual)
        self.widgetsAppeared = []
        self.widgetsRepainted = []
        self.widgetsDescribed = set()
        self.clipboardText = None
        usecase.guishared.Describer.__init__(self)

    def setWidgetPainted(self, widget):
        if widget in self.widgetsDescribed or widget in self.windows:
            if widget not in self.widgetsRepainted:
                self.widgetsRepainted.append(widget)
        elif widget not in self.widgetsAppeared:
            self.widgetsAppeared.append(widget)

    def setWidgetShown(self, widget):
        # Menu show events seem a bit spurious, they aren't really shown at this point:
        # ScrollBar shows are not relevant to anything
        if not isinstance(widget, (swt.widgets.Menu, swt.widgets.ScrollBar)) and widget not in self.widgetsAppeared:
            self.widgetsAppeared.append(widget)

    def isCanvas(self, widget):
        # Don't include subclasses which generally have some other way of being handled
        return widget.__class__ is swt.widgets.Canvas

    def addFilters(self, display):
        class ShowListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                self.setWidgetShown(e.widget)

        class PaintListener(swt.widgets.Listener):
            def handleEvent(listenerSelf, e):
                self.setWidgetPainted(e.widget)

        display.addFilter(swt.SWT.Show, ShowListener())
        display.addFilter(swt.SWT.Paint, PaintListener())

    def describeWithUpdates(self, shell):
        if shell in self.windows:
            stateChanges = self.findStateChanges(shell)
            stateChangeWidgets = [ widget for widget, old, new in stateChanges ]
            self.describeAppearedWidgets(stateChangeWidgets)
            self.describeRepaintedWidgets(stateChangeWidgets)
            self.describeStateChanges(stateChanges)
        if shell is not None:
            self.describeClipboardChanges(shell.getDisplay())
            self.describe(shell)
        self.widgetsAppeared = []
        self.widgetsRepainted = []
        
    def shouldCheckForUpdates(self, widget, shell):
        return not isinstance(widget, swt.widgets.Menu) or widget.getShell() == shell

    def parentMarked(self, widget, markedWidgets):
        if widget in markedWidgets:
            return True
        elif widget.getParent():
            return self.parentMarked(widget.getParent(), markedWidgets)
        else:
            return False

    def describeVisibilityChange(self, widget, markedWidgets, header):
        if not widget.isDisposed() and util.isVisible(widget):
            if isinstance(widget, swt.widgets.Shell):
                self.describe(widget)
            else:
                parent = widget.getParent()
                if not self.parentMarked(parent, markedWidgets):
                    markedWidgets.append(parent)
                    self.logger.info(header)
                    self.logger.info(self.getChildrenDescription(parent))
                elif self.logger.isEnabledFor(logging.DEBUG):
                    self.logger.debug("Not describing " + self.getRawData(widget) + " - marked " + \
                                      repr(map(self.getRawData, markedWidgets)))

    def describeAppearedWidgets(self, stateChangeWidgets):
        markedWidgets = self.widgetsAppeared + stateChangeWidgets
        for widget in self.widgetsAppeared:
            self.describeVisibilityChange(widget, markedWidgets, "New widgets have appeared: describing common parent :\n")

    def describeRepaintedWidgets(self, stateChangeWidgets):
        markedWidgets = self.widgetsAppeared + self.widgetsRepainted + stateChangeWidgets
        for widget in self.widgetsRepainted:
            if self.isCanvas(widget):
                # Only worry about repainting for canvas objects right now
                self.describeVisibilityChange(widget, markedWidgets, "Widgets have been repainted: describing common parent :\n")

    def describeClipboardChanges(self, display):
        clipboard = swt.dnd.Clipboard(display)
        textTransfer = swt.dnd.TextTransfer.getInstance()
        if self.clipboardText is None:
            # Initially. For some reason it doesn't let us set empty strings here
            # clearContents seemed the way to go, but seems not to work on Windows
            self.clipboardText = "dummy text for PyUseCase tests"
            clipboard.setContents([ self.clipboardText ], [ textTransfer ])
        else:
            newText = clipboard.getContents(textTransfer) or ""
            if newText != self.clipboardText:
                self.logger.info("Copied following to clipboard :\n" + newText)
                self.clipboardText = newText
        clipboard.dispose()
        
    def getWindowClasses(self):
        return swt.widgets.Shell, swt.widgets.Dialog

    def getTextEntryClass(self):
        return swt.widgets.Text

    def getWindowString(self):
        return "Shell"

    def getShellState(self, shell):
        return shell.getText()

    def getAllItemDescriptions(self, itemBar, indent=0, subItemMethod=None,
                               prefix="", selection=[], columnCount=0):
        descs = []
        for item in itemBar.getItems():
            currPrefix = prefix + " " * indent * 2
            itemDesc = self.getItemDescription(item, currPrefix, item in selection)
            if columnCount:
                row = [ itemDesc ]
                for colIndex in range(1, columnCount):
                    row.append(self.getItemColumnDescription(item, colIndex))
                descs.append(row)
            elif itemDesc:
                descs.append(itemDesc)
            if subItemMethod:
                descs += subItemMethod(item, indent, prefix=prefix, selection=selection, columnCount=columnCount)
        return descs

    def getCascadeMenuDescriptions(self, item, indent, **kw):
        cascadeMenu = item.getMenu()
        if cascadeMenu:
            descs = self.getAllItemDescriptions(cascadeMenu, indent+1, subItemMethod=self.getCascadeMenuDescriptions, **kw)
            if indent == 1:
                self.widgetsWithState[cascadeMenu] = "\n".join(descs)
            return descs
        else:
            return []

    def getSubTreeDescriptions(self, item, indent, **kw):
        if item.getExpanded():
            return self.getAllItemDescriptions(item, indent+1, subItemMethod=self.getSubTreeDescriptions, **kw)
        else:
            return []

    def getExpandItemDescriptions(self, item, indent, *args, **kw):
        if item.getExpanded():
            return [ self.getItemControlDescription(item, indent + 1, *args, **kw) ]
        else:
            return []

    def getCoolItemDescriptions(self, item, *args, **kw):
        itemDesc = self.getItemControlDescription(item, *args, **kw)
        if itemDesc:
            return [ itemDesc ] 
        else:
            return []

    def getItemControlDescription(self, item, indent, **kw):
        control = item.getControl()
        if control:
            descLines = self.getDescription(control).splitlines()
            paddedLines = [ " " * indent * 2 + line for line in descLines ]
            return "\n".join(paddedLines) + "\n"
        else:
            return ""

    def getMenuDescription(self, menu, indent=1):
        return self.getItemBarDescription(menu, indent=indent, subItemMethod=self.getCascadeMenuDescriptions)
    
    def getMenuState(self, menu):
        return self.getMenuDescription(menu, indent=2)
    
    def getMenuBarDescription(self, menubar):
        if menubar:
            return "Menu Bar:\n" + self.getMenuDescription(menubar)
        else:
            return ""

    def getExpandBarDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        return "Expand Bar:\n" + self.getItemBarDescription(widget, indent=1, subItemMethod=self.getExpandItemDescriptions) 

    def getExpandBarState(self, expandbar):
        return expandbar.getChildren(), [ item.getExpanded() for item in expandbar.getItems() ] 

    def getToolBarDescription(self, toolbar, indent=1):
        return "Tool Bar:\n" + self.getItemBarDescription(toolbar, indent=indent)
    
    def getCoolBarDescription(self, coolbar):
        return "Cool Bar:\n" + self.getItemBarDescription(coolbar, indent=1,
                                                          subItemMethod=self.getCoolItemDescriptions)

    def contextMenusEqual(self, menu1, menu2):
        return [ (item.getText(), item.getEnabled()) for item in menu1.getItems() ] == \
               [ (item.getText(), item.getEnabled()) for item in menu2.getItems() ]

    def imagesEqual(self, image1, image2):
        return image1.getImageData().data == image2.getImageData().data

    def getImageDescription(self, image):
        # Seems difficult to get any sensible image information out, there is
        # basically no query API for this in SWT
        return "Image " + self.imageCounter.getId(image)

    def getCanvasDescription(self, widget):
        return "Canvas " + self.canvasCounter.getId(widget)

    def findStyleList(self, item):
        for widgetClass, styleList in self.styleNames:
            if isinstance(item, widgetClass):
                return styleList
        return []

    def getStyleDescriptions(self, item):
        styleList = self.findStyleList(item)
        style = item.getStyle()
        descs = []
        for tryStyle in styleList:
            if style & getattr(swt.SWT, tryStyle) != 0:
                descs.append(tryStyle.lower().replace("_", " ").replace("separator", "---"))
        return descs

    def getItemColumnDescription(self, item, colIndex):
        elements = [ item.getText(colIndex) ]
        if item.getImage(colIndex):
            elements.append(self.getImageDescription(item.getImage(colIndex)))
        return self.combineElements(elements)

    def getPropertyElements(self, item, selected=False):
        elements = []
        if hasattr(item, "getToolTipText") and item.getToolTipText():
            elements.append("Tooltip '" + item.getToolTipText() + "'")
        elements += self.getStyleDescriptions(item)
        if hasattr(item, "getImage") and item.getImage():
            elements.append(self.getImageDescription(item.getImage()))
        if hasattr(item, "getEnabled") and not item.getEnabled():
            elements.append("greyed out")
        if selected:
            elements.append("selected")
        elements.append(self.getContextMenuReference(item))
        return elements

    def getLabelState(self, label):
        if label.getStyle() & swt.SWT.SEPARATOR:
            return "-" * 10
        elements = []
        if label.getText():
            elements.append("'" + label.getText() + "'")
        for fontData in label.getFont().getFontData():
            fontStyle = fontData.getStyle()
            for fontAttr in [ "BOLD", "ITALIC" ]:
                if fontStyle & getattr(swt.SWT, fontAttr):
                    elements.append(fontAttr.lower())
        if label.getImage():
            elements.append(self.getImageDescription(label.getImage()))
        elements.append(self.getContextMenuReference(label))
        return self.combineElements(elements)

    def getLabelDescription(self, label):
        return self.getAndStoreState(label)
    
    getCLabelDescription = getLabelDescription
    getCLabelState = getLabelState

    def getButtonDescription(self, widget):
        desc = "Button"
        if widget.getText():
            desc += " '" + widget.getText() + "'"
        properties = self.getButtonState(widget)
        self.widgetsWithState[widget] = properties
        elements = [ desc ] + properties 
        return self.combineElements(elements)

    def getButtonState(self, widget):
        return self.getPropertyElements(widget, selected=widget.getSelection())

    def getSashDescription(self, widget):
        orientation = "Horizontal"
        if widget.getStyle() & swt.SWT.VERTICAL:
            orientation = "Vertical"
        return "-" * 15 + " " + orientation + " sash " + "-" * 15

    def getLinkDescription(self, widget):
        return self.getAndStoreState(widget)

    def getLinkState(self, widget):
        return "Link '" + widget.getText() + "'"
        
    def getBrowserDescription(self, widget):
        return "Browser browsing '" + (widget.getUrl() or "about:blank") + "'"

    def getUpdatePrefix(self, widget, oldState, state):
        if isinstance(widget, self.getTextEntryClass()):
            return "\nUpdated " + (util.getTextLabel(widget) or "Text") +  " Field\n"
        elif isinstance(widget, swt.widgets.Combo):
            return "\nUpdated " + util.getTextLabel(widget) + " Combo Box\n"
        elif util.getTopControl(widget):
            return "\n"
        elif isinstance(widget, swt.widgets.Menu):
            return "\nUpdated " + widget.getParentItem().getText() + " Menu:\n"
        elif isinstance(widget, (swt.widgets.Label, swt.custom.CLabel)) and len(state) == 0:
            return "\nLabel now empty, previously " + oldState
        else:
            return "\nUpdated "

    def getState(self, widget):
        if widget.isDisposed():
            # Will be caught, and the widget cleaned up
            raise UseCaseScriptError, "Widget is Disposed"
        else:
            return self.getSpecificState(widget)

    def getTextState(self, widget):
        return widget.getText(), self.getPropertyElements(widget)

    def getComboState(self, widget):
        return self.getTextState(widget)

    def getTextDescription(self, widget):
        contents, properties = self.getState(widget)
        self.widgetsWithState[widget] = contents, properties
        header = "=" * 10 + " " + widget.__class__.__name__ + " " + "=" * 10
        fullHeader = self.combineElements([ header ] + properties)
        return fullHeader + "\n" + self.fixLineEndings(contents.rstrip()) + "\n" + "=" * len(header)    

    def getComboDescription(self, widget):
        return self.getTextDescription(widget)

    def getTreeDescription(self, widget):
        return self.getAndStoreState(widget)

    def getTableDescription(self, widget):
        return self.getAndStoreState(widget)

    def getListDescription(self, widget):
        return self.getAndStoreState(widget)

    def getDateTimeDescription(self, widget):
        return self.getAndStoreState(widget)

    def getDateString(self, widget):
        if widget.getStyle() & swt.SWT.TIME:
            widgetDate = Date()
            widgetDate.setHours(widget.getHours())
            widgetDate.setMinutes(widget.getMinutes())
            widgetDate.setSeconds(widget.getSeconds())
            return util.getDateFormat(swt.SWT.TIME).format(widgetDate)
        else:
            widgetDate = Date(widget.getYear() - 1900, widget.getMonth(), widget.getDay())
            return util.getDateFormat(swt.SWT.DATE).format(widgetDate)

    def getDateTimeState(self, widget):
        elements = [ "DateTime" ] + self.getPropertyElements(widget) + [ "showing " + self.getDateString(widget) ]
        return self.combineElements(elements)

    def getListState(self, widget):
        text = self.combineElements([ "List" ] + self.getPropertyElements(widget)) + " :\n"
        selection = widget.getSelection()
        for item in widget.getItems():
            text += "-> " + item
            if item in selection:
                text += " (selected)"
            text += "\n"
        return text

    def getContextMenuReference(self, widget):
        if not isinstance(widget, swt.widgets.MenuItem) and hasattr(widget, "getMenu") and widget.getMenu():
            return "Context Menu " + self.contextMenuCounter.getId(widget.getMenu())
        else:
            return ""

    def getTreeState(self, widget):
        columns = widget.getColumns()
        columnCount = len(columns)
        text = self.combineElements([ "Tree" ] + self.getPropertyElements(widget)) + " :\n"
        rows = self.getAllItemDescriptions(widget, indent=0, subItemMethod=self.getSubTreeDescriptions,
                                           prefix="-> ", selection=widget.getSelection(),
                                           columnCount=columnCount)
        if columnCount > 0:
            rows.insert(0, [ c.getText() for c in columns ])
            text += str(GridFormatter(rows, columnCount))
        else:
            text += "\n".join(rows)
        return text

    def getTableState(self, widget):
        columns = widget.getColumns()
        columnCount = len(columns)
        text = self.combineElements([ "Table" ] + self.getPropertyElements(widget)) + " :\n"
        rows = self.getAllItemDescriptions(widget, indent=0, 
                                           selection=widget.getSelection(),
                                           columnCount=columnCount)
        headerRow = [ c.getText() for c in columns ]
        return text + self.formatTable(headerRow, rows, columnCount)

    def getTabFolderDescription(self, widget):
        state = self.getState(widget)
        self.widgetsWithState[widget] = state
        if state:
            return "TabFolder with tabs " + state
        else:
            return "TabFolder with no tabs"

    def getTabFolderState(self, widget):
        return " , ".join(self.getAllItemDescriptions(widget, selection=widget.getSelection()))

    def getCTabFolderState(self, widget):
        return " , ".join(self.getAllItemDescriptions(widget, selection=[ widget.getSelection() ]))

    getCTabFolderDescription = getTabFolderDescription

    def getCompositeState(self, widget):
        return util.getTopControl(widget)

    def getCompositeDescription(self, widget):
        return self.combineElements([ self.getStateControlDescription(widget), self.getContextMenuReference(widget) ])

    def getStateControlDescription(self, widget):
        stateControl = self.getState(widget)
        if stateControl:
            self.widgetsWithState[widget] = stateControl
            if len(widget.getChildren()) > 1:
                header = "+" * 6 + " Stacked Layout " + "+" * 6
                footer = "+" * len(header)
                return header + "\n" + self.getDescription(stateControl) + "\n" + footer
            else:
                return self.getDescription(stateControl)
        else:
            return ""

    def getVerticalDividePositions(self, children):
        positions = []
        for child in children:
            if isinstance(child, swt.widgets.Sash) and child.getStyle() & swt.SWT.VERTICAL:
                 positions.append(child.getLocation().x)
        return sorted(positions)

    def layoutSortsChildren(self, widget):
        layout = widget.getLayout()
        return layout is not None and isinstance(layout, (swt.layout.GridLayout, swt.layout.FillLayout,
                                                          swt.layout.RowLayout, swt.custom.StackLayout))

    def _getDescription(self, widget):
        self.widgetsDescribed.add(widget)
        desc = usecase.guishared.Describer._getDescription(self, widget)
        if desc and isinstance(widget, (swt.widgets.ExpandBar, swt.widgets.Tree, swt.widgets.List)):
            desc = str(desc) + self.formatContextMenuDescriptions()
        return desc

    def getWindowContentDescription(self, shell):
        desc = ""
        desc = self.addToDescription(desc, self.getMenuBarDescription(shell.getMenuBar()))
        desc = self.addToDescription(desc, self.getChildrenDescription(shell))
        desc += self.formatContextMenuDescriptions()
        return desc
    
    def shouldDescribeChildren(self, widget):
        # Composites with StackLayout use the topControl rather than the children
        return usecase.guishared.Describer.shouldDescribeChildren(self, widget) and not util.getTopControl(widget)
        
    def formatContextMenuDescriptions(self):
        text = ""
        for contextMenu, menuId in self.contextMenuCounter.getWidgetsForDescribe():
            text += "\n\nContext Menu " + str(menuId) + ":\n" + self.getMenuDescription(contextMenu)
        return text

    def getHorizontalSpan(self, widget, *args):
        layout = widget.getLayoutData()
        if hasattr(layout, "horizontalSpan"):
            return layout.horizontalSpan
        else:
            return 1

    def usesGrid(self, widget):
        return isinstance(widget.getLayout(), swt.layout.GridLayout)

    def getLayoutColumns(self, widget, childCount, *args):
        layout = widget.getLayout()
        if hasattr(layout, "numColumns"):
            return layout.numColumns
        elif hasattr(layout, "type"):
            if layout.type == swt.SWT.HORIZONTAL:
                return childCount
        return 1

    def getRawDataLayoutDetails(self, layout, *args):
        return [ str(layout.numColumns) + " columns" ] if hasattr(layout, "numColumns") else []
