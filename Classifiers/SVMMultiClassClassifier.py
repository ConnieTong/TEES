__version__ = "$Revision: 1.51 $"

import sys,os
sys.path.append(os.path.dirname(os.path.abspath(__file__))+"/..")
import shutil, tempfile
import subprocess
import Core.ExampleUtils as ExampleUtils
import combine
import copy
import tempfile
import subprocess
import atexit
import gzip
"""
A wrapper for the Joachims SVM Multiclass classifier.
"""
    
import types, copy
from Core.Classifier import Classifier
import Core.Split as Split
from Utils.Timer import Timer
from Utils.Parameters import *
from Utils.ProgressCounter import ProgressCounter
import Utils.Settings as Settings
import Utils.Download as Download
import SVMMultiClassModelUtils
from Utils.Connection.Unix import UnixConnection

def test(progDir):
    cwd = os.getcwd()
    os.chdir(progDir)
    print >> sys.stderr, "Testing svm_multiclass_learn...",
    trainOK = Download.checkReturnCode(os.system("echo | ./svm_multiclass_learn -? > /dev/null"))
    print >> sys.stderr, "Testing svm_multiclass_classify...",
    classifyOK = Download.checkReturnCode(os.system("echo | ./svm_multiclass_classify -? > /dev/null"))
    os.chdir(cwd)
    return trainOK and classifyOK

def install(destDir=None, downloadDir=None, redownload=False, compile=True):
    print >> sys.stderr, "Installing SVM-Multiclass"
    if compile:
        url = Settings.URL["SVM_MULTICLASS_SOURCE"]
    else:
        url = Settings.URL["SVM_MULTICLASS_LINUX"]
    if downloadDir == None:
        downloadDir = os.path.join(Settings.DATAPATH, "tools/download/")
    if destDir == None:
        destDir = Settings.DATAPATH
    destDir += "/tools/SVMMultiClass"
    
    Download.downloadAndExtract(url, destDir, downloadDir, redownload=redownload)
    if compile:
        print >> sys.stderr, "Compiling SVM-Multiclass"
        subprocess.call("cd " + destDir + "; make", shell=True)
    
    test(destDir)

def tempUnzip(filename):
    tempdir = tempfile.mkdtemp() # a place for the file
    dst = os.path.join(tempdir, os.path.basename(filename))
    shutil.copy(filename, dst)
    #print "gunzip -fv " + dst
    #subprocess.call("gunzip -fv " + dst, shell=True)
    subprocess.call("gunzip -f " + dst, shell=True)
    if dst.endswith(".gz"):
        dst = dst[:-3]
    atexit.register(shutil.rmtree, tempdir) # mark for deletion
    return os.path.join(tempdir, dst)

class SVMMultiClassClassifier(Classifier):
    """
    A wrapper for the Joachims SVM Multiclass classifier.
    """

    indent = ""
    #IF LOCAL
    louhiBinDir = "/v/users/jakrbj/svm-multiclass"
    #ENDIF
    def __init__(self):
        self.connection = UnixConnection() # A local connection
        self.parameterGrid = None
        self.step = None
        self._job = None
        
        self.parameters = None
        self.model = None
        self.predictions = None
        #self.parameterFormat = "-%k %v"
        #self.trainDir = "SVM_MULTICLASS_DIR"
        #self.trainCommand = "svm_multiclass_learn %a %m"
        #self.classifyDir = "SVM_MULTICLASS_DIR"
        #self.classifyCommand = "svm_multiclass_classify %m %e %p"
    
    def getStatus(self):
        if self._job == None:
            return "FINISHED"
        status = self.connection.getJobStatus(self._job)
        if status == "FINISHED":
            self._job = None
        return status
    
    def getExampleFile(self, examples, trainPath):
        # If examples are in a list, they will be written to a file for SVM-multiclass
        if examples == None:
            return None
        elif type(examples) == types.ListType:
            ExampleUtils.writeExamples(examples, trainPath)
        else:
            trainPath = examples
        remoteFile = self.connection.upload(trainPath, uncompress=True)
        if remoteFile == examples and remoteFile.endswith(".gz"):
            remoteFile = tempUnzip(remoteFile)
        return remoteFile
    
    def train(self, examples, outDir, parameters, classifyExamples=None):
        assert self.getStatus() == "FINISHED"
        examples = self.getExampleFile(examples, "train.dat")
        classifyExamples = self.getExampleFile(classifyExamples, "classify.dat")
        parameters = splitParameters(parameters)
        svmMulticlassDir = self.connection.getSetting("SVM_MULTICLASS_DIR")
        
        # Return a new classifier instance for following the training process and using the model
        classifier = copy.copy(self)
        classifier.model = None
        classifier.parameters = parameters
        classifier.predictions = None
        # Train
        if not os.path.exists(outDir):
            os.makedirs(outDir)
        trainCommand = svmMulticlassDir + "/svm_multiclass_learn "
        paramKeys = sorted(parameters.keys())
        idStr = ""
        for key in paramKeys:
            trainCommand += "-" + str(key) + " "
            idStr += "-" + str(key)
            if parameters[key] != None:
                trainCommand += str(parameters[key]) + " "
                idStr += "_" + str(parameters[key])
        modelPath = self.connection.getPath(outDir + "/model" + idStr)
        classifier.model = modelPath
        trainCommand += examples + " " + modelPath
        self.connection.addCommand(trainCommand)
        # Classify with the trained model (optional)
        if classifyExamples != None:
            predictionsPath = self.connection.getPath(outDir + "/predictions" + idStr)
            classifier.predictions = predictionsPath
            classifyCommand = svmMulticlassDir + "/svm_multiclass_classify " + classifyExamples + " " + modelPath + " " + predictionsPath
            self.connection.addCommand(classifyCommand)
        # Run the process
        logPath = self.connection.getPath(outDir + "/train_svm_multiclass" + idStr + "-log.txt")
        classifier._job = self.connection.submit(stdout=logPath)
        return classifier
    
    def downloadModel(self, outDir):
        assert self.getStatus() == "FINISHED" and self.model != None
        self.model = self.connection.download(self.model, outDir)
        return self.model
    
    def downloadPredictions(self, outDir):
        assert self.getStatus() == "FINISHED" and self.predictions != None
        self.predictions = self.connection.download(self.predictions, outDir)
        return self.predictions
    
    def classify(self, examples, output, model=None):
        assert self.getStatus() == "FINISHED"
        self.predictions = None
    
    @classmethod
    def trainOld(cls, examples, parameters, outputFile=None): #, timeout=None):
        """
        Train the SVM-multiclass classifier on a set of examples.
        
        @type examples: string (filename) or list (or iterator) of examples
        @param examples: a list or file containing examples in SVM-format
        @type parameters: a dictionary or string
        @param parameters: parameters for the classifier
        @type outputFile: string
        @param outputFile: the name of the model file to be written
        """
        timer = Timer()
        # If parameters are defined as a string, extract them
        if type(parameters) == types.StringType:
            parameters = splitParameters(parameters)
            for k, v in parameters.iteritems():
                assert(len(v)) == 1
                parameters[k] = v[0]
        # If examples are in a list, they will be written to a file for SVM-multiclass
        if type(examples) == types.ListType:
            print >> sys.stderr, "Training SVM-MultiClass on", len(examples), "examples"
            trainPath = self.tempDir+"/train.dat"
            examples = self.filterTrainingSet(examples)
            #if self.negRatio != None:
            #    examples = self.downSampleNegatives(examples, self.negRatio)
            Example.writeExamples(examples, trainPath)
        else:
            print >> sys.stderr, "Training SVM-MultiClass on file", examples
            trainPath = examples
#        if style != None and "no_duplicates" in style:
#            if type(examples) == types.ListType:
#                examples = Example.removeDuplicates(examples)
#            else:
#                print >> sys.stderr, "Warning, duplicates not removed from example file", examples
        
#        if os.environ.has_key("METAWRK"):
#            args = [SVMMultiClassClassifier.louhiBinDir+"/svm_multiclass_learn"]
#        else:
#            args = [Settings.SVMMultiClassDir+"/svm_multiclass_learn"]
        args = [Settings.SVM_MULTICLASS_DIR+"/svm_multiclass_learn"]
            
        cls.__addParametersToSubprocessCall(args, parameters)
        if outputFile == None:
            args += [trainPath, "model"]
            logFile = open("svmmulticlass.log","at")
        else:
            args += [trainPath, outputFile]
            logFile = open(outputFile+".log","wt")
        #if timeout == None:
        #    timeout = -1
        rv = subprocess.call(args, stdout = logFile)
        logFile.close()
        print >> sys.stderr, timer.toString()
        return rv
    
    @classmethod
    def test(cls, examples, modelPath, output=None, parameters=None, forceInternal=False, classIds=None): # , timeout=None):
        """
        Classify examples with a pre-trained model.
        
        @type examples: string (filename) or list (or iterator) of examples
        @param examples: a list or file containing examples in SVM-format
        @type modelPath: string
        @param modelPath: filename of the pre-trained model file
        @type parameters: a dictionary or string
        @param parameters: parameters for the classifier
        @type output: string
        @param output: the name of the predictions file to be written
        @type forceInternal: Boolean
        @param forceInternal: Use python classifier even if SVM Multiclass binary is defined in Settings.py
        """
        if forceInternal or Settings.SVM_MULTICLASS_DIR == None:
            return cls.testInternal(examples, modelPath, output)
        timer = Timer()
        if type(examples) == types.ListType:
            print >> sys.stderr, "Classifying", len(examples), "with SVM-MultiClass model", modelPath
            examples, predictions = self.filterClassificationSet(examples, False)
            testPath = self.tempDir+"/test.dat"
            Example.writeExamples(examples, testPath)
        else:
            print >> sys.stderr, "Classifying file", examples, "with SVM-MultiClass model", modelPath
            testPath = examples
            #examples = Example.readExamples(examples,False)
        if os.environ.has_key("METAWRK"):
            args = [SVMMultiClassClassifier.louhiBinDir+"/svm_multiclass_classify"]
        else:
            args = [Settings.SVM_MULTICLASS_DIR+"/svm_multiclass_classify"]
        if modelPath == None:
            modelPath = "model"
        if modelPath.endswith(".gz"):
            modelPath = tempUnzip(modelPath)
        if testPath.endswith(".gz"):
            testPath = tempUnzip(testPath)
#        if parameters != None:
#            parameters = copy.copy(parameters)
#            if parameters.has_key("c"):
#                del parameters["c"]
#            if parameters.has_key("predefined"):
#                parameters = copy.copy(parameters)
#                modelPath = os.path.join(parameters["predefined"][0],"classifier/model")
#                del parameters["predefined"]
#            self.__addParametersToSubprocessCall(args, parameters)
        if output == None:
            output = "predictions"
            logFile = open("svmmulticlass.log","at")
        else:
            logFile = open(output+".log","wt")
        compressOutput = False
        if output.endswith(".gz"):
            output = output[:-3]
            compressOutput = True
        args += [testPath, modelPath, output]
        #if timeout == None:
        #    timeout = -1
        #print args
        subprocess.call(args, stdout = logFile, stderr = logFile)
        
        predictionsFile = open(output, "rt")
        lines = predictionsFile.readlines()
        predictionsFile.close()
        if compressOutput:
            subprocess.call("gzip -f " + output, shell=True)
        
        predictions = []
        for i in range(len(lines)):
            predictions.append( [int(lines[i].split()[0])] + lines[i].split()[1:] )
            #predictions.append( (examples[i],int(lines[i].split()[0]),"multiclass",lines[i].split()[1:]) )
        print >> sys.stderr, timer.toString()
        return predictions                
        
    @classmethod
    def __addParametersToSubprocessCall(cls, args, parameters):
        for k,v in parameters.iteritems():
            args.append("-"+k)
            args.append(str(v))
    
    @classmethod
    def testInternal(cls, examples, modelPath, output=None, idStem=None):
        try:
            import numpy
            numpy.array([]) # dummy call to survive networkx
            numpyAvailable = True
        except:
            numpyAvailable = False

        if output == None:
            output = "predictions"
        
        outputDetails = False
        if idStem != None: # Output detailed classification
            outputDetails = True
            from Core.IdSet import IdSet
            featureSet = IdSet(filename=idStem+".feature_names")
            classSet = IdSet(filename=idStem+".class_names")
            
        assert os.path.exists(modelPath)
        svs = SVMMultiClassModelUtils.getSupportVectors(modelPath)
        #SVMMultiClassModelUtils.writeModel(svs, modelPath, output+"-test-model")
        if type(examples) == types.StringType: # examples are in a file
            print >> sys.stderr, "Classifying file", examples, "with SVM-MultiClass model (internal classifier)", modelPath        
            examples = Example.readExamples(examples)
        else:
            print >> sys.stderr, "Classifying examples with SVM-MultiClass model (internal classifier)", modelPath
        if numpyAvailable:
            print >> sys.stderr, "Numpy available, using"
        
        numExamples = 0
        for example in examples:
            numExamples += 1
        
        counter = ProgressCounter(numExamples, "Classify examples", step=0.1)
        predFile = open(output, "wt")
        predictions = []
        isFirst = True
        for example in examples:
            strengthVectors = {}
            strengths = {}
            counter.update(1, "Classifying: ")
            highestPrediction = -sys.maxint
            highestNonNegPrediction = -sys.maxint
            predictedClass = None
            highestNonNegClass = None
            predictionStrings = []
            mergedPredictionString = ""
            features = example[2]
            featureIds = sorted(features.keys())
            if numpyAvailable:
                numpyFeatures = numpy.zeros(len(svs[0]))
                for k, v in features.iteritems():
                    try:
                        # SVM-multiclass feature indices start from 1. However, 
                        # support vectors in variable svs are of course zero based
                        # lists. Adding -1 to ids aligns features.
                        numpyFeatures[k-1] = v
                    except:
                        pass
            for svIndex in range(len(svs)):
                sv = svs[svIndex]
                if numpyAvailable:
                    strengthVector = sv * numpyFeatures
                    prediction = numpy.sum(strengthVector)
                    if outputDetails:
                        strengthVectors[svIndex] = strengthVector
                        strengths[svIndex] = prediction
                else:
                    prediction = 0
                    for i in range(len(sv)):
                        if features.has_key(i+1):
                            prediction += features[i+1] * sv[i]
                if prediction > highestPrediction:
                    highestPrediction = prediction
                    predictedClass = svIndex + 1
                if svIndex > 0 and prediction > highestNonNegPrediction:
                    highestNonNegPrediction = prediction
                    highestNonNegClass = svIndex + 1
                predictionString = "%.6f" % prediction # use same precision as SVM-multiclass does
                predictionStrings.append(predictionString)
                mergedPredictionString += " " + predictionString
            predictions.append([predictedClass, predictionStrings])
            if isFirst:
                isFirst = False
            else:
                predFile.write("\n")
            predFile.write(str(predictedClass) + mergedPredictionString)
            if outputDetails:
                if example[1] != 1:
                    predFile.write(example[0] + " " + str(example[3]) + "\n")
                    cls.writeDetails(predFile, strengthVectors[0], classSet.getName(0+1) + " " + str(strengths[0]), featureSet)
                    #if predictedClass != 1:
                    #    cls.writeDetails(predFile, strengthVectors[predictedClass-1], classSet.getName(predictedClass) + " " + str(strengths[predictedClass]), featureSet)
                    cls.writeDetails(predFile, strengthVectors[example[1]-1], classSet.getName(example[1]) + " " + str(strengths[example[1]-1]), featureSet)
                else:
                    predFile.write(example[0] + " " + str(example[3]) + "\n")
                    cls.writeDetails(predFile, strengthVectors[0], classSet.getName(0+1) + " " + str(strengths[0]), featureSet)
                    cls.writeDetails(predFile, strengthVectors[highestNonNegClass-1], classSet.getName(highestNonNegClass) + " " + str(strengths[highestNonNegClass-1]), featureSet)
        predFile.close()
    
    @classmethod
    def writeDetails(cls, predFile, vec, className, featureSet):
        predFile.write(className+"\n")
        tuples = []
        for i in range(len(vec)):
            if float(vec[i]) != 0.0:
                tuples.append( (featureSet.getName(i+1), vec[i], i+1) )
        import operator
        index1 = operator.itemgetter(1)
        tuples.sort(key=index1, reverse=True)
        for t in tuples:
            predFile.write(" " + str(t[2]) + " " + t[0] + " " + str(t[1]) + "\n")
        #for i in range(len(vec)):
        #    if float(vec[i]) != 0.0:
        #        predFile.write(" " + str(i+1) + " " + featureSet.getName(i+1) + " " + str(vec[i+1]) + "\n")

    #IF LOCAL
    def downSampleNegatives(self, examples, ratio):
        positives = []
        negatives = []
        for example in examples:
            if example[1] == 1:
                negatives.append(example)
            else:
                positives.append(example)
        
        targetNumNegatives = ratio * len(positives)
        if targetNumNegatives > len(negatives):
            targetNumNegatives = len(negatives)
        sample = Split.getSample(len(negatives), targetNumNegatives / float(len(negatives)) )
        examples = positives
        for i in range(len(sample)):
            if sample[i] == 0:
                examples.append(negatives[i])
        return examples
    
    @classmethod
    def initTrainAndTestOnLouhi(cls, trainExamples, testExamples, trainParameters, cscConnection, localWorkDir=None, classIds=None):
        if cscConnection.account.find("murska") != -1:
            isMurska = True
        else:
            isMurska = False
        assert( type(trainExamples)==types.StringType ), type(trainExamples)
        assert( type(testExamples)==types.StringType ), type(testExamples)
        trainExampleFileName = os.path.split(trainExamples)[-1]
        testExampleFileName = os.path.split(testExamples)[-1]
        assert(trainExampleFileName != testExampleFileName)
        cscConnection.upload(trainExamples, trainExampleFileName, False, compress=True, uncompress=True)
        cscConnection.upload(testExamples, testExampleFileName, False, compress=True, uncompress=True)
        # use uncompressed file names on the CSC machine
        if trainExampleFileName.endswith(".gz"): trainExampleFileName = trainExampleFileName[:-3]
        if testExampleFileName.endswith(".gz"): testExampleFileName = testExampleFileName[:-3]
        
        idStr = ""
        paramStr = ""
        for key in sorted(trainParameters.keys()):
            idStr += "-" + str(key) + "_" + str(trainParameters[key])
            if key != "classifier":
                paramStr += " -" + str(key) + " " + str(trainParameters[key])
        scriptName = "script"+idStr+".sh"
        if cscConnection.exists(scriptName):
            print >> sys.stderr, "Script already on " + cscConnection.machineName + ", process not queued for", scriptName
            return idStr
        
        # Build script
        scriptFilePath = scriptName
        if localWorkDir != None:
            scriptFilePath = os.path.join(localWorkDir, scriptName)
        scriptFile = open(scriptFilePath, "wt")
        scriptFile.write("#!/bin/bash\ncd " + cscConnection.workDir + "\n")
        if not isMurska: # louhi
            scriptFile.write("aprun -n 1 ")
        #print trainParameters
        if "classifier" in trainParameters and trainParameters["classifier"] == "svmperf":
            scriptFile.write(cls.louhiBinDir + "/svm_perf_learn" + paramStr + " " + cscConnection.workDir + "/" + trainExampleFileName + " " + cscConnection.workDir + "/model" + idStr + "\n")
        else:
            scriptFile.write(cls.louhiBinDir + "/svm_multiclass_learn" + paramStr + " " + cscConnection.workDir + "/" + trainExampleFileName + " " + cscConnection.workDir + "/model" + idStr + "\n")
        if not isMurska: # louhi
            scriptFile.write("aprun -n 1 ")
        if "classifier" in trainParameters and trainParameters["classifier"] == "svmperf":
            scriptFile.write(cls.louhiBinDir + "/svm_perf_classify " + cscConnection.workDir + "/" + testExampleFileName + " " + cscConnection.workDir + "/model" + idStr + " " + cscConnection.workDir + "/predictions" + idStr + "\n")
        else:
            scriptFile.write(cls.louhiBinDir + "/svm_multiclass_classify " + cscConnection.workDir + "/" + testExampleFileName + " " + cscConnection.workDir + "/model" + idStr + " " + cscConnection.workDir + "/predictions" + idStr + "\n")
        scriptFile.close()
        
        cscConnection.upload(scriptFilePath, scriptName, compress=False)
        cscConnection.run("chmod a+x " + cscConnection.workDir + "/" + scriptName)
        cscScriptPath = cscConnection.workDir + "/" + scriptName
        if isMurska:
            runCmd = "bsub -o " + cscScriptPath + "-stdout -e " + cscScriptPath + "-stderr -W 10:0 -M " + str(cscConnection.memory) 
            if cscConnection.cores != 1:
                runCmd += " -n " + str(cscConnection.cores)
            runCmd += " < " + cscScriptPath
            cscConnection.run(runCmd)
        else:
            cscConnection.run("qsub -o " + cscConnection.workDir + "/" + scriptName + "-stdout -e " + cscConnection.workDir + "/" + scriptName + "-stderr " + cscConnection.workDir + "/" + scriptName)
        return idStr
    
    @classmethod
    def getLouhiStatus(cls, idStr, cscConnection, counts, classIds=None):
        stderrStatus = cscConnection.getFileStatus("script" + idStr + ".sh" + "-stderr")
        if stderrStatus == cscConnection.NOT_EXIST:
            counts["QUEUED"] += 1
            return "QUEUED"
        elif stderrStatus == cscConnection.NONZERO:
            counts["FAILED"] += 1
            return "FAILED"
        elif cscConnection.exists("predictions"+idStr):
            counts["FINISHED"] += 1
            return "FINISHED"
        else:
            counts["RUNNING"] += 1
            return "RUNNING"

    @classmethod
    def downloadModel(cls, idStr, cscConnection, localWorkDir=None):
        #if not cls.getLouhiStatus(idStr, cscConnection):
        #    return None
        modelFileName = "model"+idStr
        if localWorkDir != None:
            modelFileName = os.path.join(localWorkDir, modelFileName)
        cscConnection.download("model"+idStr, modelFileName)
        return "model"+idStr
    
    @classmethod
    def getLouhiPredictions(cls, idStr, cscConnection, localWorkDir=None, dummy=None):
        #if not cls.getLouhiStatus(idStr, cscConnection):
        #    return None
        predFileName = "predictions"+idStr
        if localWorkDir != None:
            predFileName = os.path.join(localWorkDir, predFileName)
        cscConnection.download("predictions"+idStr, predFileName, compress=True, uncompress=True)
        if os.path.exists(predFileName):
            return predFileName
        else:
            return None
        
#        predictionsFile = open(predFileName, "rt")
#        lines = predictionsFile.readlines()
#        predictionsFile.close()
#        predictions = []
#        for i in range(len(lines)):
#            predictions.append( [int(lines[i].split()[0])] + lines[i].split()[1:] )
#            #predictions.append( (examples[i],int(lines[i].split()[0]),"multiclass",lines[i].split()[1:]) )
#        return predictions
    #ENDIF
    
if __name__=="__main__":
    # Import Psyco if available
    try:
        import psyco
        psyco.full()
        print >> sys.stderr, "Found Psyco, using"
    except ImportError:
        print >> sys.stderr, "Psyco not installed"

    from optparse import OptionParser
    import os
    from Utils.Parameters import *
    optparser = OptionParser(usage="%prog [options]\n")
    optparser.add_option("-e", "--examples", default=None, dest="examples", help="Example File", metavar="FILE")
    optparser.add_option("-t", "--train", default=None, dest="train", action="store_true", help="train")
    optparser.add_option("--classifyExamples", default=None, dest="classifyExamples", help="Example File", metavar="FILE")
    optparser.add_option("-m", "--model", default=None, dest="model", help="path to model file")
    #optparser.add_option("-w", "--work", default=None, dest="work", help="Working directory for intermediate and debug files")
    optparser.add_option("-o", "--output", default=None, dest="output", help="Output directory or file")
    #optparser.add_option("-c", "--classifier", default="SVMMultiClassClassifier", dest="classifier", help="Classifier Class")
    optparser.add_option("-p", "--parameters", default=None, dest="parameters", help="Parameters for the classifier")
    #optparser.add_option("-d", "--ids", default=None, dest="ids", help="")
    optparser.add_option("--install", default=None, dest="install", help="Install directory (or DEFAULT)")
    optparser.add_option("--installFromSource", default=False, action="store_true", dest="installFromSource", help="")
    (options, args) = optparser.parse_args()
    
    if options.install != None:
        downloadDir = None
        destDir = None
        if options.install != "DEFAULT":
            if "," in options.install:
                destDir, downloadDir = options.install.split(",")
            else:
                destDir = options.install
        install(destDir, downloadDir, False, options.installFromSource)
        sys.exit()
    else:
        classifier = SVMMultiClassClassifier()
        if options.train:
            import time
            trained = classifier.train(options.examples, options.output, options.parameters, options.classifyExamples)
            status = trained.getStatus()
            while status not in ["FINISHED", "FAILED"]:
                print >> sys.stderr, "Training classifier, status =", status
                time.sleep(10)
                status = trained.getStatus()
            print >> sys.stderr, "Training finished, status =", status
        else:
            classifier.classify(options.examples, options.model, options.output)
    # import classifier
    #print >> sys.stderr, "Importing classifier module"
    #exec "from Classifiers." + options.classifier + " import " + options.classifier + " as Classifier"

    # Create classifier object
#    if options.work != None:
#        classifier = Classifier(workDir = options.output)
#    else:
#        classifier = Classifier()
    
#    if options.train:
#        parameters = getArgs(Classifier.train, options.parameters)
#        print >> sys.stderr, "Training on", options.examples, "Parameters:", parameters
#        startTime = time.time()
#        predictions = classifier.train(options.examples, options.output, **parameters)
#        print >> sys.stderr, "(Time spent:", time.time() - startTime, "s)"
#    else: # Classify
#        #parameters = getArgs(Classifier.classify, options.parameters)
#        #print >> sys.stderr, "Classifying", options.examples, "Parameters:", parameters
#        #startTime = time.time()
#        if options.ids != None:
#            predictions = Classifier.testInternal(options.examples, options.model, options.output, options.ids)
#        else:
#            predictions = Classifier.test(options.examples, options.model, options.output, forceInternal=True)
##        print >> sys.stderr, "(Time spent:", time.time() - startTime, "s)"
##        parameters = getArgs(Classifier.classify, options.parameters)
##        print >> sys.stderr, "Classifying", options.examples, "Parameters:", parameters
##        startTime = time.time()
##        predictions = classifier.classify(options.examples, options.output, **parameters)
##        print >> sys.stderr, "(Time spent:", time.time() - startTime, "s)"

