
""" Generic module for any kind of Python UI, as distinct from usecase.py which contains 
stuff also applicable even without this """

import usecase, os, sys, logging, subprocess
from ndict import seqdict

# We really need our ConfigParser to be ordered, copied the one from 2.6 into the repository
if sys.version_info[:2] >= (2, 6):
    from ConfigParser import ConfigParser
else:
    from ConfigParser26 import ConfigParser

class GuiEvent(usecase.UserEvent):
    def __init__(self, name, widget, *args):
        usecase.UserEvent.__init__(self, name)
        self.widget = widget


class ScriptEngine(usecase.ScriptEngine):
    defaultMapFile = os.path.join(usecase.ScriptEngine.usecaseHome, "ui_map.conf")
    def __init__(self, enableShortcuts=False, uiMapFiles=[ defaultMapFile ], universalLogging=True, binDir=""):
        self.uiMap = self.createUIMap(uiMapFiles)
        self.binDir = binDir
        usecase.ScriptEngine.__init__(self, enableShortcuts, universalLogging=universalLogging)

    def findEventClassesFor(self, widget):
        eventClasses = []
        currClass = None
        for widgetClass, currEventClasses in self.eventTypes:
            if isinstance(widget, widgetClass):
                if not currClass or issubclass(widgetClass, currClass):
                    eventClasses = currEventClasses
                    currClass = widgetClass
                elif not issubclass(currClass, widgetClass):
                    eventClasses += currEventClasses
        return eventClasses

    def monitorSignal(self, eventName, signalName, widget, argumentParseData=None, autoGenerated=False):
        if self.active():
            stdName = self.standardName(eventName, autoGenerated)
            signalEvent = self._createSignalEvent(stdName, signalName, widget, argumentParseData)
            self._addEventToScripts(signalEvent, autoGenerated)
            return signalEvent

    def _addEventToScripts(self, event, autoGenerated=False):
        if event.name and self.replayerActive():
            self.replayer.addEvent(event)
        if event.name and self.recorderActive():
            event.connectRecord(self.recorder.writeEvent)

    def standardName(self, name, autoGenerated=False):
        if autoGenerated:
            return name
        else:
            return name.strip().lower()

    def getUsecaseNameChooserEnv(self):
        new_env = {}
        for var, value in os.environ.items():
            if var == "PATH":
                new_env[var] = value + ":" + self.binDir
            elif not var.startswith("USECASE_RE"): # Don't transfer our record scripts!
                new_env[var] = value
        return new_env

    def getUsecaseNameChooserCmdArgs(self, recordScript, interface):
        mapFiles = self.uiMap.getMapFileNames()
        return [ "usecase_name_chooser", "-m", ",".join(mapFiles), 
                 "-r", recordScript, "-i", interface ]

    def hasAutoRecordings(self, fileName):
        # Don't start the name chooser process unnecessarily
        for line in open(fileName):
            if line.startswith("Auto."):
                return True
        return False

    def replaceAutoRecordingForUsecase(self, interface):
        recordScript = os.getenv("USECASE_RECORD_SCRIPT")
        if self.uiMap and recordScript and os.path.isfile(recordScript) and self.hasAutoRecordings(recordScript):
            sys.stdout.flush()
            cmdArgs = self.getUsecaseNameChooserCmdArgs(recordScript, interface)
            os.execvpe(cmdArgs[0], cmdArgs, self.getUsecaseNameChooserEnv())

    def replaceAutoRecordingForShortcut(self, script):
        if self.uiMap and self.binDir:
            cmdArgs = self.getUsecaseNameChooserCmdArgs(script.scriptName, "gtk")
            subprocess.call(cmdArgs, env=self.getUsecaseNameChooserEnv())

class WriteParserHandler:
    def __init__(self, fileName):
        self.fileName = fileName
        self.parser = ConfigParser(dict_type=seqdict)
        self.parser.optionxform = str # don't automatically lower-case everything
        self.parser.read([ self.fileName ])
        self.changed = False

    def write(self):
        if self.changed:
            if not os.path.isdir(os.path.dirname(self.fileName)):
                os.makedirs(os.path.dirname(self.fileName))
            self.parser.write(open(self.fileName, "w"))
            self.changed = False

    def add_section(self, *args):
        self.changed = True
        self.parser.add_section(*args)

    def set(self, *args):
        self.changed = True
        self.parser.set(*args)

    def __getattr__(self, name):
        return getattr(self.parser, name)


class UIMapFileHandler:
    def __init__(self, uiMapFiles): 
        self.readFiles(uiMapFiles)

    def readFiles(self, uiMapFiles):
        # See top of file: uses the version from 2.6
        self.writeParsers = map(WriteParserHandler, uiMapFiles)
        if len(self.writeParsers) == 1:
            self.readParser = self.writeParsers[0]
        else:
            self.readParser = ConfigParser(dict_type=seqdict)
            self.readParser.optionxform = str # don't automatically lower-case everything
            self.readParser.read(uiMapFiles)

    def storeInfo(self, sectionName, signature, eventName, addToReadParser):
        if not self.readParser.has_section(sectionName):
            self.writeParsers[-1].add_section(sectionName)
            if addToReadParser:
                self.readParser.add_section(sectionName)
           
        signature = signature.replace("::", "-") # Can't store :: in ConfigParser unfortunately
        if not self.readParser.has_option(sectionName, signature):
            for writeParser in self.writeParsers:
                if writeParser.has_section(sectionName):
                    writeParser.set(sectionName, signature, eventName)
            if addToReadParser:
                self.readParser.set(sectionName, signature, eventName)
            return True
        else:
            return False

    def findWriteParser(self, section):
        for parser in self.writeParsers:
            if parser.has_section(section):
                return parser

    def updateSectionName(self, section, newName):
        writeParser = self.findWriteParser(section)
        if not writeParser.has_section(newName):
            writeParser.add_section(newName)
        for name, value in self.readParser.items(section):
            writeParser.set(newName, name, value)
        writeParser.remove_section(section)
        return newName

    def write(self, *args):
        for parserHandler in self.writeParsers:
            parserHandler.write()

    def __getattr__(self, name):
        return getattr(self.readParser, name)


class UIMap:
    ignoreWidgetTypes = []
    def __init__(self, scriptEngine, uiMapFiles):
        self.fileHandler = UIMapFileHandler(uiMapFiles)
        self.scriptEngine = scriptEngine
        self.windows = []
        self.logger = logging.getLogger("gui map")

    def readFiles(self, uiMapFiles):
        self.fileHandler.readFiles(uiMapFiles)

    def getMapFileNames(self):
        return [ parser.fileName for parser in self.fileHandler.writeParsers ]

    def monitor(self, widget, excludeWidget=None, mapFileOnly=False):
        mapFileOnly |= widget is excludeWidget
        autoInstrumented = self.monitorWidget(widget, mapFileOnly)
        self.monitorChildren(widget, excludeWidget, mapFileOnly)
        return autoInstrumented

    def monitorWidget(self, widget, mapFileOnly=False):
        signaturesInstrumented, autoInstrumented = self.instrumentFromMapFile(widget)
        if not mapFileOnly and self.scriptEngine.recorderActive():
            widgetType = widget.__class__.__name__
            for signature in self.findAutoInstrumentSignatures(widget, signaturesInstrumented):
                autoEventName = "Auto." + widgetType + "." + signature + ".'" + self.getSectionName(widget) + "'"
                signalName, argumentParseData = self.parseSignature(signature)
                self.autoInstrument(autoEventName, signalName, widget, argumentParseData, widgetType)
        return autoInstrumented

    def tryImproveSectionName(self, widget, section):
        if not section.startswith("Name="):
            newName = self.getSectionName(widget)
            if newName != section:
                return self.fileHandler.updateSectionName(section, newName)
        return section

    def instrumentFromMapFile(self, widget):
        widgetType = widget.__class__.__name__
        if widgetType in self.ignoreWidgetTypes:
            return set(), False
        signaturesInstrumented = set()
        autoInstrumented = False
        section = self.findSection(widget, widgetType)
        if section:
            section = self.tryImproveSectionName(widget, section)
            self.logger.debug("Reading map file section " + repr(section) + " for widget of type " + widgetType)
            for signature, eventName in self.fileHandler.items(section):
                if self.tryAutoInstrument(eventName, signature, signaturesInstrumented, widget, widgetType):
                    autoInstrumented = True
        return signaturesInstrumented, autoInstrumented

    def tryAutoInstrument(self, eventName, signature, signaturesInstrumented, widget, widgetType):
        try:
            signalName, argumentParseData = self.parseSignature(signature)
            if self.autoInstrument(eventName, signalName, widget, argumentParseData, widgetType):
                signaturesInstrumented.add(signature)
                return True
        except usecase.UseCaseScriptError, e:
            sys.stderr.write("ERROR in UI map file: " + str(e) + "\n")
        return False

    def findAutoInstrumentSignatures(self, widget, preInstrumented):
        signatures = []
        for eventClass in self.scriptEngine.findEventClassesFor(widget):
            for signature in eventClass.getAssociatedSignatures(widget):
                if signature not in signatures and signature not in preInstrumented:
                    signatures.append(signature)
        return signatures

    def findSection(self, widget, widgetType):
        sectionNames = self.findPossibleSectionNames(widget) + [ "Type=" + widgetType ]
        for sectionName in sectionNames:
            self.logger.debug("Looking up section name " + repr(sectionName))
            if self.fileHandler.has_section(sectionName):
                return sectionName

    def parseSignature(self, signature):
        parts = signature.split(".", 1)
        signalName = parts[0]
        if len(parts) > 1:
            return signalName, parts[1]
        else:
            return signalName, None

    def autoInstrument(self, eventName, signalName, widget, argumentParseData, *args):
        self.logger.debug("Monitor " + eventName + ", " + signalName + ", " + str(widget.__class__) + ", " + str(argumentParseData))
        self.scriptEngine.monitorSignal(eventName, signalName, widget, argumentParseData, autoGenerated=True)
        return True

        

# Use the GTK idle handlers instead of a separate thread for replay execution
class UseCaseReplayer(usecase.UseCaseReplayer):
    def __init__(self, uiMap, universalLogging, recorder):
        self.readingEnabled = False
        self.uiMap = uiMap
        self.idleHandler = None
        self.loggerActive = universalLogging
        self.recorder = recorder
        self.delay = float(os.getenv("USECASE_REPLAY_DELAY", 0.0))
        self.tryAddDescribeHandler()
        usecase.UseCaseReplayer.__init__(self)

    def isMonitoring(self):
        return self.loggerActive or (self.recorder.isActive() and self.uiMap)

    def tryAddDescribeHandler(self):
        if self.idleHandler is None and self.isMonitoring():
            self.idleHandler = self.makeDescribeHandler(self.handleNewWindows)
        else:
            self.idleHandler = None

    def handleNewWindows(self):
        for window in self.findWindowsForMonitoring():
            if self.uiMap and (self.isActive() or self.recorder.isActive()):
                self.uiMap.monitorWindow(window)
            if self.loggerActive:
                self.describeNewWindow(window)
        return self.callHandleAgain()

    def enableReading(self):
        self.readingEnabled = True
        self._disableIdleHandlers()
        self.enableReplayHandler()
    
    def _disableIdleHandlers(self):
        if self.idleHandler is not None:
            self.removeHandler(self.idleHandler)
            self.idleHandler = None
    
    def enableReplayHandler(self):
        self.idleHandler = self.makeReplayHandler(self.describeAndRun)

    def makeReplayHandler(self, method):
        if self.delay:
            milliseconds = int(self.delay * 1000)
            return self.makeTimeoutReplayHandler(method, milliseconds)
        else:
            return self.makeIdleReplayHandler(method)

    def describeAndRun(self):
        self.handleNewWindows()
        if self.readingEnabled:
            self.readingEnabled = self.runNextCommand()
            if not self.readingEnabled:
                self.idleHandler = None
                self.tryAddDescribeHandler()
                if not self.idleHandler and self.uiMap: # pragma: no cover - cannot test with replayer disabled
                    # End of shortcut: reset for next time
                    self.logger.debug("Shortcut terminated: Resetting UI map ready for next shortcut")
                    self.uiMap.windows = [] 
                    self.events = {}
        return self.readingEnabled
