import sys, os
import itertools
import types
thisPath = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(thisPath,"..")))
sys.path.append(os.path.abspath(os.path.join(thisPath,"../CommonUtils")))
import STFormat.STTools
import STFormat.ConvertXML
import STFormat.Equiv
import cElementTreeUtils as ETUtils
import Tools.GeniaSentenceSplitter
import Tools.GeniaTagger
import Tools.CharniakJohnsonParser
import Tools.StanfordParser
import Tools.BANNER
from Detector import Detector
import InteractionXML.DivideSets
import GeniaChallenge.formatConversion.ProteinNameSplitter as ProteinNameSplitter
import Utils.FindHeads as FindHeads
from Test.Pipeline import log

class Preprocessor(Detector):
    def __init__(self):
        Detector.__init__(self)
        # Settings
        self.debug = False
        self.STATE_PREPROCESS = "PREPROCESS"
        self.namedEntityElementName = "entity"
        self.splitNamedEntitiesAtNewlines = True
        self.nerAfterSplitting = True
        self.requireEntitiesForParsing = False
        self.parseName = "McClosky"
        self._preprocessingSteps = ["CONVERT", "NER-BEFORE-SPLIT", "SPLIT-SENTENCES", "NER-AFTER-SPLIT", "PARSE", "CONVERT-PARSE", "SPLIT-NAMES", "FIND-HEADS", "DIVIDE-SETS"]
        self._intermediateFiles = {}
        self.intermediateFilesAtSource = False
        self.compressIntermediateFiles = False
        for step in self._preprocessingSteps[:-1]:
            self._intermediateFiles[step] = None
        self.setIntermediateFile("CONVERT", "documents.xml")
        self.setIntermediateFile("NER-BEFORE-SPLIT", "ner.xml")
        self.setIntermediateFile("SPLIT-SENTENCES", "sentences.xml")
        self.setIntermediateFile("NER-AFTER-SPLIT", "ner.xml")
        self.setIntermediateFile("PARSE", "parse.xml")
        self.setIntermediateFile("CONVERT-PARSE", "converted-parse.xml")
        self.setIntermediateFile("SPLIT-NAMES", "split-names.xml")
        self.setIntermediateFile("FIND-HEADS", "heads.xml")
        # Tools
        self.sentenceSplitter = Tools.GeniaSentenceSplitter
        self.namedEntityRecognizer = Tools.BANNER
        self.parser = Tools.CharniakJohnsonParser
        self.parseConverter = Tools.StanfordParser
        self.proteinNameSplitter = ProteinNameSplitter
        self.headDetector = FindHeads
    
    def setIntermediateFile(self, step, filename):
        assert step in self._preprocessingSteps, (step, self._preprocessingSteps)
        self._intermediateFiles[step] = filename
    
    def setNoIntermediateFiles(self):
        for key in self._intermediateFiles.keys():
            self._intermediateFiles[key] = None
    
    def getCurrentOutput(self):
        return self.getOutputPath(self.select.currentStep)
    
    def getOutputPath(self, step):
        if self._intermediateFiles[step] != None:
            if self.intermediateFilesAtSource:
                rv = os.path.join(self.source + "-" + self._intermediateFiles[step])
            else:
                rv = os.path.join(self.outDir, self.corpusName + "-" + self._intermediateFiles[step])
            if self.compressIntermediateFiles and not rv.endswith(".gz"):
                rv += ".gz" 
            return rv
        else:
            return None
    
    def process(self, source, corpusName, outDir, sourceDataSetNames=None, fromStep=None, toStep=None, omitSteps=None):
        self.initVariables(source=source, corpusName=corpusName, sourceDataSetNames=sourceDataSetNames, outDir=outDir, xml=source)
        self.enterState(self.STATE_PREPROCESS, self._preprocessingSteps, fromStep, toStep, omitSteps)
        if self.checkStep("CONVERT"):
            if os.path.isdir(source) or source.endswith(".tar.gz") or "," in source:
                self.xml = self.convert(self.source, self.sourceDataSetNames, output=self.getCurrentOutput())
        if type(self.xml) in types.StringTypes:
            print >> sys.stderr, "Processing source as interaction XML"
            self.xml = ETUtils.ETFromObj(self.xml)
        if self.checkStep("NER-BEFORE-SPLIT"):
            if self.nerAfterSplitting:
                print >> sys.stderr, "NER will be done after sentence splitting"
            else:
                self.detectEntities(self.xml, self.namedEntityElementName, processElement="document", output=self.getCurrentOutput(), splitNewlines=self.splitNamedEntitiesAtNewlines)
        if self.checkStep("SPLIT-SENTENCES"):
            self.splitSentences(self.xml, output=self.getCurrentOutput())
        if self.checkStep("NER-AFTER-SPLIT"):
            if not self.nerAfterSplitting:
                print >> sys.stderr, "NER was done before sentence splitting"
            else:
                self.detectEntities(self.xml, self.namedEntityElementName, processElement="sentence", output=self.getCurrentOutput(), splitNewlines=self.splitNamedEntitiesAtNewlines)
        if self.checkStep("PARSE"):
            self.parseCJ(self.xml, output=self.getCurrentOutput(), requireEntities=self.requireEntitiesForParsing)
        if self.checkStep("CONVERT-PARSE"):
            self.stanfordConvert(self.xml, "McClosky", self.getCurrentOutput())
        if self.checkStep("SPLIT-NAMES"):
            self.splitNames(self.xml, "McClosky", "split-McClosky", output=self.getCurrentOutput())
        if self.checkStep("FIND-HEADS"):
            self.findHeads(self.xml, output=self.getCurrentOutput())
        if self.checkStep("DIVIDE-SETS"):
            self.divideSets(self.xml, os.path.join(self.outDir, self.corpusName))
        xml = self.xml # state-specific member variable self.xml will be removed when exiting state
        self.exitState()
        if self.state == None:
            return xml
    
    def convert(self, dataSetDirs, dataSetNames=None, output=None):
        print >> sys.stderr, "Converting ST-format to Interaction XML"
        documents = []
        if type(dataSetDirs) in types.StringTypes:
            dataSetDirs = dataSetDirs.split(",")
        if dataSetNames == None: 
            dataSetNames = []
        elif type(dataSetNames) in types.StringTypes:
            dataSetNames = dataSetNames.split(",")
        for dataSetDir, dataSetName in itertools.izip_longest(dataSetDirs, dataSetNames, fillvalue=None):
            print >> sys.stderr, "Reading", dataSetDir, "set,",
            docs = STFormat.STTools.loadSet(dataSetDir, dataSetName)
            print >> sys.stderr, len(docs), "documents"
            documents.extend(docs)
        print >> sys.stderr, "Resolving equivalences"
        STFormat.Equiv.process(documents)
        return STFormat.ConvertXML.toInteractionXML(documents, self.corpusName, output)
    
    def splitSentences(self, input, output=None):
        print >> sys.stderr, "Splitting document-elements to sentence-elements"
        self.sentenceSplitter.makeSentences(input, output, postProcess=True, debug=self.debug)
    
    def detectEntities(self, input, elementName="entity", processElement="sentence", output=None, splitNewlines=True):
        print >> sys.stderr, "Running named entity recognition"
        self.namedEntityRecognizer.run(input, output=output, elementName=self.namedEntityElementName, processElement=processElement, debug=self.debug, splitNewlines=splitNewlines)
    
    def parseCJ(self, input, parseName="McClosky", requireEntities=False, output=None):
        print >> sys.stderr, "Parsing sentence-elements"
        self.parser.parse(input, output, tokenizationName=None, parseName=parseName, requireEntities=requireEntities, debug=self.debug)
    
    def stanfordConvert(self, input, parseName="McClosky", output=None):
        print >> sys.stderr, "Running Stanford Conversion on parse", parseName
        self.parseConverter.convertXML(parseName, input, output, debug=self.debug)
    
    def splitNames(self, input, parseName, newParseName=None, output=None):
        print >> sys.stderr, "Splitting multiple-named-entity tokens"
        if newParseName == None:
            newParseName = "split-" + parseName
        self.proteinNameSplitter.mainFunc(input, output, parseName, parseName, newParseName, newParseName)
    
    def findHeads(self, input, parseName="split-McClosky", output=None):
        print >> sys.stderr, "Detecting entity syntactic heads"
        xml = self.headDetector.findHeads(input, parseName, tokenization=None, output=output, removeExisting=True)
    
    def divideSets(self, input, outputStem):
        print >> sys.stderr, "Dividing into sets"
        outDir, outputStem = os.path.split(outputStem)
        InteractionXML.DivideSets.processCorpus(input, outDir, outputStem, ".xml", saveCombined=True)

if __name__=="__main__":
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
        print >> sys.stderr, "Found Psyco, using"
    except ImportError:
        print >> sys.stderr, "Psyco not installed"
    from optparse import OptionParser
    optparser = OptionParser()
    optparser.add_option("-i", "--input", default=None, dest="input", help="")
    optparser.add_option("-n", "--inputNames", default=None, dest="inputNames", help="")
    optparser.add_option("-c", "--corpus", default=None, dest="corpus", help="corpus name")
    optparser.add_option("-o", "--output", default=None, dest="output", help="output directory")
    optparser.add_option("-f", "--fromStep", default=None, dest="fromStep", help="")
    optparser.add_option("-t", "--toStep", default=None, dest="toStep", help="")
    optparser.add_option("--omitSteps", default=None, dest="omitSteps", help="")
    optparser.add_option("--noLog", default=False, action="store_true", dest="noLog", help="")
    optparser.add_option("--debug", default=False, action="store_true", dest="debug", help="")
    optparser.add_option("--requireEntities", default=False, action="store_true", dest="requireEntities", help="")
    (options, args) = optparser.parse_args()
    if options.omitSteps != None:
        options.omitSteps = options.omitSteps.split(",")
    
    cwd = os.getcwd()
    options.output = os.path.abspath(options.output)
    if not os.path.exists(options.output): os.makedirs(options.output)
    os.chdir(options.output)
    if not options.noLog:
        log(False, True, os.path.join(options.output, options.corpus + "-log.txt"))
    preprocessor = Preprocessor()
    preprocessor.debug = options.debug
    preprocessor.requireEntitiesForParsing = options.requireEntities
    preprocessor.process(options.input, options.corpus, options.output, options.inputNames, fromStep=options.fromStep, toStep=options.toStep, omitSteps=options.omitSteps)
    os.chdir(cwd)